"""
The tables, from the int32 columns in diversity/data (see scripts/build_data.py).

Columns are loaded on first use and kept while the function is warm. A request
selects row indexes or sums the count column, with no SQLite or pandas (as in
njoaguof-api's counts), and only the page it returns is made into dicts. Results
are cached by their validated parameters, since the data never changes while warm.
"""

import array
import json
import os
import sys
from collections import defaultdict
from functools import lru_cache

from .params import InvalidRequest, NotFound

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

MAX_DIMENSIONS = 4
CACHE_SIZE = 256
LOGICAL_LABELS = (None, False, True)
LOGICAL_CODES = {False: 1, True: 2}


class Table:
    """A table's columns: {name, type, labels (factor and character only)}"""

    def __init__(self, name, meta, data_dir):
        self.name = name
        self.data_dir = data_dir
        self.rows = meta["rows"]
        self.weight = meta["weight"]
        self.columns = meta["columns"]
        self.by_name = {c["name"]: c for c in self.columns}
        self.names = [c["name"] for c in self.columns]
        self.keys = [n for n in self.names if n != self.weight]
        self._values = {}
        # Per-instance caches, so a new Table starts empty
        self.selection = lru_cache(CACHE_SIZE)(self._selection)
        self.totals = lru_cache(CACHE_SIZE)(self._totals)

    def values(self, column):
        """A column's codes as a list (indexing a list is faster than an array)"""
        if column not in self._values:
            codes = array.array("i")
            path = os.path.join(self.data_dir, f"{self.name}.{column}.i32")
            with open(path, "rb") as f:
                codes.frombytes(f.read())
            self._values[column] = codes.tolist()
        return self._values[column]

    def code(self, column, value):
        """The code of a checked filter value, or None when no row can have it"""
        meta = self.by_name[column]
        if meta["type"] == "integer":
            return value
        if meta["type"] == "logical":
            return LOGICAL_CODES[value]
        try:
            return meta["labels"].index(value) + 1
        except ValueError:
            return None

    def decoder(self, column):
        """Function from a column's code to its API value"""
        meta = self.by_name[column]
        if meta["type"] == "integer":
            return lambda v: v if v != 0 else None
        if meta["type"] == "logical":
            return LOGICAL_LABELS.__getitem__
        return ([None] + meta["labels"]).__getitem__

    def _selection(self, filters):
        """Row indexes where the filters, a tuple of (column, code), hold, in R's order"""
        rows = range(self.rows)
        for column, code in filters:
            values = self.values(column)
            rows = [i for i in rows if values[i] == code]
        return rows

    def _totals(self, dimensions, filters):
        """
        ((codes, total), ...) of the weight column per combination of the
        dimensions' codes, in code order with null last. Filters as selection().
        """
        columns = [self.values(d) for d in dimensions]
        weights = self.values(self.weight)
        if filters:
            rows = self.selection(filters)
            columns = [map(c.__getitem__, rows) for c in columns]
            weights = map(weights.__getitem__, rows)
        totals = defaultdict(int)
        for key, weight in zip(zip(*columns), weights):
            totals[key] += weight
        return tuple(
            sorted(totals.items(), key=lambda kv: [(v == 0, v) for v in kv[0]])
        )


class DiversityData:
    def __init__(self, data_dir):
        with open(os.path.join(data_dir, "labels.json"), encoding="utf-8") as f:
            meta = json.load(f)
        if meta["byteorder"] != sys.byteorder:
            raise RuntimeError(f"data is {meta['byteorder']}-endian")
        self.source = meta["source"]
        self.tables = {
            name: Table(name, table, data_dir) for name, table in meta["tables"].items()
        }


# Loaded on first use and kept while the function is warm
_data = None


def get_data():
    global _data
    if _data is None:
        _data = DiversityData(os.environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    return _data


def parse_by(table, by):
    """The by parameter as a tuple of the table's key columns"""
    if by is None:
        raise InvalidRequest("by is required")
    dimensions = tuple(by.split(","))
    if len(dimensions) > MAX_DIMENSIONS:
        raise InvalidRequest(f"by needs 1 to {MAX_DIMENSIONS} columns")
    if len(set(dimensions)) != len(dimensions):
        raise InvalidRequest(f"Repeated column in by={by}")
    for d in dimensions:
        if d not in table.keys:
            raise InvalidRequest(f"Unknown column {d} in by")
    return dimensions


def paged(rows, page, convert):
    """
    One page of rows.

    Returns:
        list of records, aux dict for torguapi_make_links_and_meta

    Raises:
        NotFound when there are no rows, or the page is past the last one
    """
    record_count = len(rows)
    page_number, page_size = page["page_number"], page["page_size"]
    if record_count == 0:
        raise NotFound("No matching records")
    page_count = (record_count - 1) // page_size + 1
    if page_number > page_count:
        raise NotFound(f"Page number {page_number} not found")
    start = (page_number - 1) * page_size
    records = [convert(r) for r in rows[start : start + page_size]]
    aux = {
        "page_number": page_number,
        "page_size": page_size,
        "record_count": record_count,
    }
    return records, aux


def row_converter(table):
    """Function from a row index to its record"""
    columns = [(n, table.values(n), table.decoder(n)) for n in table.names]
    return lambda i: {n: decode(values[i]) for n, values, decode in columns}


def get_rows(table, filters, page):
    """One page of the rows where the filters hold"""
    return paged(table.selection(filters), page, row_converter(table))


def get_row(table, filters):
    """The one row where the filters (the table's key) hold, or None"""
    rows = table.selection(filters)
    if not rows:
        return None
    return row_converter(table)(rows[0])


def get_counts(table, dimensions, filters, page):
    """One page of {<dimension>: value, ..., "count": total}"""
    decoders = [table.decoder(d) for d in dimensions]

    def convert(item):
        key, total = item
        record = {d: f(v) for d, f, v in zip(dimensions, decoders, key)}
        record["count"] = total
        return record

    return paged(table.totals(dimensions, filters), page, convert)
