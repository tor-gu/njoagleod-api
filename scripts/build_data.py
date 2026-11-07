"""
Build the Lambda's data from the exported tables (make data).

Usage: python scripts/build_data.py [data dir] [repo root]

Reads data/ as written by scripts/export_data.R (<table>.csv.gz, columns.csv,
levels.csv, SOURCE) and writes diversity/data/ under the repo root. Only the
standard library is used.

Every column is one file of int32s, <table>.<column>.i32, so a request loads only
the columns it uses and the cold start doesn't parse the tables:

  integer     the value (year, and the count columns)
  logical     1 FALSE, 2 TRUE
  factor      position in the column's levels, from 1
  character   position in the column's sorted distinct values, from 1 (agency_id)

0 means null, and codes sort in the API's order: declared levels, FALSE before
TRUE, with null handled by the reader. labels.json has what's needed to read them:

  {"byteorder": ..., "source": {...},
   "tables": {<table>: {"rows": n, "weight": <count column or null>,
                        "columns": [{"name": ..., "type": ..., "labels": [...]}]}}}

(labels only for factor and character columns.)
"""

import array
import csv
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict

OUT = os.path.join("diversity", "data")

# Table -> its count column (None: a table of one row per key)
TABLES = {
    "officer": "officer_count",
    "applicant": "applicant_count",
    "agency_practice": None,
}
PRACTICE_KEY = ["year", "agency_id"]

AGENCY_ID = re.compile(r"^NJLEA[0-9]{4}$")
LOGICALS = {"": 0, "FALSE": 1, "TRUE": 2}


class BuildError(Exception):
    pass


def read_csv(path):
    """Header and rows of a CSV file (gzipped if .gz), as lists of strings"""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        return header, list(reader)


def read_source(path):
    with open(path, encoding="utf-8") as f:
        return dict(line.rstrip("\n").split("=", 1) for line in f if "=" in line)


def encode_integer(name, values):
    try:
        return [int(v) if v != "" else 0 for v in values], None
    except ValueError as e:
        raise BuildError(f"{name}: {e}") from None


def encode_logical(name, values):
    try:
        return [LOGICALS[v] for v in values], None
    except KeyError as e:
        raise BuildError(f"{name}: {e.args[0]!r} is not a logical") from None


def encode_factor(name, values, levels):
    codes = {level: i for i, level in enumerate(levels, 1)}
    codes[""] = 0
    try:
        return [codes[v] for v in values], levels
    except KeyError as e:
        raise BuildError(f"{name}: {e.args[0]!r} is not a level ({levels})") from None


def encode_character(name, values):
    labels = sorted(set(values) - {""})
    return encode_factor(name, values, labels)


def encode_column(name, type_, values, levels):
    """The column's int32 codes, and its labels (None if it has none)"""
    if type_ == "integer":
        return encode_integer(name, values)
    if type_ == "logical":
        return encode_logical(name, values)
    if type_ == "factor":
        if not levels:
            raise BuildError(f"{name}: no levels in levels.csv")
        return encode_factor(name, values, levels)
    if type_ == "character":
        return encode_character(name, values)
    raise BuildError(f"{name}: unknown column type {type_!r}")


def read_table(data_dir, table, types, levels):
    """{"columns": [{name, type, labels, codes}], "rows": n}, as read from the export"""
    names = [c for c, _ in types]
    header, rows = read_csv(os.path.join(data_dir, f"{table}.csv.gz"))
    if header != names:
        raise BuildError(f"{table}: header {header} doesn't match columns.csv {names}")
    for i, row in enumerate(rows):
        if len(row) != len(names):
            raise BuildError(f"{table} row {i + 1}: {len(row)} fields")
    columns = []
    for j, (name, type_) in enumerate(types):
        codes, labels = encode_column(
            f"{table}.{name}", type_, [r[j] for r in rows], levels.get((table, name))
        )
        columns.append({"name": name, "type": type_, "labels": labels, "codes": codes})
    return {"columns": columns, "rows": len(rows)}


def read_export(data_dir):
    """{table: read_table()} and SOURCE"""
    _, rows = read_csv(os.path.join(data_dir, "columns.csv"))
    types = defaultdict(list)
    for table, _, column, type_ in sorted(rows, key=lambda r: (r[0], int(r[1]))):
        types[table].append((column, type_))
    _, rows = read_csv(os.path.join(data_dir, "levels.csv"))
    levels = defaultdict(list)
    for table, column, _, level in sorted(rows, key=lambda r: (r[0], r[1], int(r[2]))):
        levels[(table, column)].append(level)
    tables = {}
    for table in TABLES:
        if table not in types:
            raise BuildError(f"{table} is not in columns.csv")
        tables[table] = read_table(data_dir, table, types[table], levels)
    return tables, read_source(os.path.join(data_dir, "SOURCE"))


def check_table(name, table, weight):
    """The build fails on data the routes rely on not having"""
    if table["rows"] == 0:
        raise BuildError(f"{name}: no rows")
    columns = {c["name"]: c for c in table["columns"]}
    for required in ("year", "agency_id"):
        if required not in columns:
            raise BuildError(f"{name}: no {required} column")
        if 0 in columns[required]["codes"]:
            raise BuildError(f"{name}: null {required}")
    for agency_id in columns["agency_id"]["labels"]:
        if not AGENCY_ID.match(agency_id):
            raise BuildError(f"{name}: bad agency_id {agency_id!r}")
    if weight is not None:
        if weight not in columns:
            raise BuildError(f"{name}: no {weight} column")
        if min(columns[weight]["codes"]) < 1:
            raise BuildError(f"{name}: {weight} must be positive")
        key = [c for c in columns if c != weight]
    else:
        key = PRACTICE_KEY
    keys = zip(*(columns[c]["codes"] for c in key))
    duplicates = [k for k, n in Counter(keys).items() if n > 1]
    if duplicates:
        raise BuildError(f"{name}: duplicate keys {duplicates[:5]}")


def write_i32(path, values):
    with open(path, "wb") as f:
        array.array("i", values).tofile(f)


def build(data_dir, root):
    tables, source = read_export(data_dir)
    for name, weight in TABLES.items():
        check_table(name, tables[name], weight)
    out_dir = os.path.join(root, OUT)
    os.makedirs(out_dir, exist_ok=True)
    for entry in os.listdir(out_dir):
        if entry.endswith(".i32") or entry == "labels.json":
            os.remove(os.path.join(out_dir, entry))
    meta = {}
    for name, table in tables.items():
        columns = []
        for column in table["columns"]:
            write_i32(
                os.path.join(out_dir, f"{name}.{column['name']}.i32"), column["codes"]
            )
            entry = {"name": column["name"], "type": column["type"]}
            if column["labels"] is not None:
                entry["labels"] = column["labels"]
            columns.append(entry)
        meta[name] = {
            "rows": table["rows"],
            "weight": TABLES[name],
            "columns": columns,
        }
    with open(os.path.join(out_dir, "labels.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"byteorder": sys.byteorder, "source": source, "tables": meta},
            f,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return out_dir


def main(argv):
    data_dir = argv[1] if len(argv) > 1 else "data"
    root = argv[2] if len(argv) > 2 else "."
    try:
        out_dir = build(data_dir, root)
    except BuildError as e:
        sys.exit(f"build_data: {e}")
    size = sum(os.path.getsize(os.path.join(out_dir, f)) for f in os.listdir(out_dir))
    print(f"Wrote {out_dir} ({size:,} bytes)")


if __name__ == "__main__":
    main(sys.argv)
