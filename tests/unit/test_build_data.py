import array
import json
import os

import pytest

from scripts import build_data

from .conftest import COLUMNS, LEVELS, ROWS, write_csv, write_export


@pytest.fixture
def meta(fixture_build):
    with open(os.path.join(fixture_build, "labels.json"), encoding="utf-8") as f:
        return json.load(f)


def column(fixture_build, table, name):
    values = array.array("i")
    with open(os.path.join(fixture_build, f"{table}.{name}.i32"), "rb") as f:
        values.frombytes(f.read())
    return values.tolist()


def build_with(tmp_path, **parts):
    """Builds an export with parts replaced (write_export's arguments)"""
    export = tmp_path / "export"
    export.mkdir()
    write_export(str(export), **parts)
    return build_data.build(str(export), str(tmp_path))


def replaced(table, row, position, value):
    """The table's rows, with one field changed"""
    rows = [list(r) for r in ROWS[table]]
    rows[row][position] = value
    return {table: rows}


def test_labels(meta):
    assert meta["source"]["version"] == "0.0.0"
    assert meta["byteorder"] in ("little", "big")
    tables = meta["tables"]
    assert {n: t["rows"] for n, t in tables.items()} == {
        "officer": 7,
        "applicant": 3,
        "agency_practice": 3,
    }
    assert tables["officer"]["weight"] == "officer_count"
    assert tables["agency_practice"]["weight"] is None
    by_name = {c["name"]: c for c in tables["officer"]["columns"]}
    assert by_name["officer_race"]["labels"] == ["White", "Asian", "Other"]
    assert by_name["agency_id"]["labels"] == ["NJLEA0001", "NJLEA0002"]
    assert "labels" not in by_name["year"]
    assert "labels" not in by_name["promoted"]


def test_codes(fixture_build):
    assert column(fixture_build, "officer", "year")[:4] == [2021, 2021, 2021, 2022]
    # Position in the sorted IDs, in the row order of the export
    assert column(fixture_build, "officer", "agency_id")[:2] == [2, 1]
    # Position in the levels; 0 for null
    assert column(fixture_build, "officer", "officer_race")[:3] == [1, 2, 0]
    # 0 null, 1 false, 2 true
    assert column(fixture_build, "officer", "promoted")[2:5] == [0, 2, 1]
    assert column(fixture_build, "officer", "officer_count") == [3, 1, 2, 4, 5, 6, 7]


def test_every_column_has_a_file(fixture_build):
    files = set(os.listdir(fixture_build))
    expected = {"labels.json"} | {
        f"{table}.{name}.i32" for table, cols in COLUMNS.items() for name, _ in cols
    }
    assert files == expected


def test_a_rebuild_removes_stale_columns(tmp_path):
    out = build_with(tmp_path)
    stale = os.path.join(out, "officer.old.i32")
    with open(stale, "wb"):
        pass
    build_data.build(str(tmp_path / "export"), str(tmp_path))
    assert not os.path.exists(stale)


@pytest.mark.parametrize(
    "parts,message",
    [
        ({"rows": replaced("officer", 0, 2, "Martian")}, "not a level"),
        ({"rows": replaced("officer", 0, 4, "yes")}, "not a logical"),
        ({"rows": replaced("officer", 0, 5, "x")}, "officer.officer_count"),
        ({"rows": replaced("officer", 0, 5, "0")}, "must be positive"),
        ({"rows": replaced("officer", 0, 5, "")}, "must be positive"),
        ({"rows": replaced("officer", 0, 0, "")}, "null year"),
        ({"rows": replaced("officer", 0, 1, "")}, "null agency_id"),
        ({"rows": replaced("officer", 0, 1, "A0001")}, "bad agency_id"),
        ({"rows": {"officer": ROWS["officer"] + ROWS["officer"][:1]}}, "duplicate"),
        ({"rows": {"officer": []}}, "no rows"),
        (
            {"rows": {"officer": [ROWS["officer"][0][:-1]] + ROWS["officer"][1:]}},
            "fields",
        ),
        (
            {"rows": {"agency_practice": ROWS["agency_practice"][:1] * 2}},
            "agency_practice: duplicate",
        ),
        (
            {"levels": {k: v for k, v in LEVELS.items() if k[0] != "applicant"}},
            "applicant.outcome: no levels",
        ),
    ],
)
def test_bad_exports_fail_the_build(tmp_path, parts, message):
    with pytest.raises(build_data.BuildError, match=message):
        build_with(tmp_path, **parts)


def test_practice_key_is_year_and_agency_only(tmp_path):
    """Two rows that differ only in an answer are still duplicates"""
    rows = [["2022", "NJLEA0001", "TRUE", ""], ["2022", "NJLEA0001", "FALSE", ""]]
    with pytest.raises(build_data.BuildError, match="duplicate"):
        build_with(tmp_path, rows={"agency_practice": rows})


def test_header_must_match_columns(tmp_path):
    export = tmp_path / "export"
    export.mkdir()
    write_export(str(export))
    write_csv(
        str(export / "applicant.csv.gz"),
        ["year", "agency_id", "result", "applicant_count"],
        [["2022", "NJLEA0001", "Pending", "2"]],
    )
    with pytest.raises(build_data.BuildError, match="doesn't match columns.csv"):
        build_data.build(str(export), str(tmp_path))


def test_a_missing_table_fails_the_build(tmp_path):
    columns = {k: v for k, v in COLUMNS.items() if k != "applicant"}
    export = tmp_path / "export"
    export.mkdir()
    write_export(str(export))
    write_csv(
        str(export / "columns.csv"),
        ["table", "position", "column", "type"],
        [
            [table, i, c, t]
            for table, cols in columns.items()
            for i, (c, t) in enumerate(cols, 1)
        ],
    )
    with pytest.raises(build_data.BuildError, match="applicant is not in columns.csv"):
        build_data.build(str(export), str(tmp_path))
