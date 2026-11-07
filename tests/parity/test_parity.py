"""
The API against R, on the full data (make data).

data/<table>.csv.gz is R's table, and tests/parity/expected/counts_<table>.csv.gz
is R's dplyr::count() for a set of groupings (both written by
scripts/export_data.R). The handler must reproduce each one through its paged
replies: the same rows, order and values. Logicals are TRUE/FALSE and NA is an
empty field.
"""

import csv
import gzip
import json
import os
from collections import defaultdict

import pytest

from diversity.app.diversity_api import diversity_handler

REPO = os.path.join(os.path.dirname(__file__), "..", "..")
DATA = os.path.join(REPO, "data")
EXPECTED = os.path.join(os.path.dirname(__file__), "expected")
ROOT = "/nj/officer_diversity"
PAGE_SIZE = "5000"

ROUTES = {
    "officer": "officers",
    "applicant": "applicants",
    "agency_practice": "agency_practices",
}
WEIGHTS = {"officer": "officer_count", "applicant": "applicant_count"}


def read_rows(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def expected_counts(table):
    """R's counts by grouping: {"year,officer_race": [row, ...]}"""
    groups = defaultdict(list)
    for row in read_rows(os.path.join(EXPECTED, f"counts_{table}.csv.gz")):
        groups[row.pop("by")].append(row)
    return dict(groups)


TABLES = {t: read_rows(os.path.join(DATA, f"{t}.csv.gz")) for t in ROUTES}
COUNTS = {t: expected_counts(t) for t in WEIGHTS}


def as_csv(value):
    """A value of the reply as R's write.csv wrote it"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def all_pages(route, query=None):
    """Every record of the route, following its next links"""
    records = []
    page_number = 1
    while True:
        reply = diversity_handler(
            {
                "resource": f"{ROOT}/{route}",
                "pathParameters": None,
                "queryStringParameters": {
                    **(query or {}),
                    "page_number": str(page_number),
                    "page_size": PAGE_SIZE,
                },
            },
            None,
        )
        body = json.loads(reply["body"])
        assert reply["statusCode"] == 200, body
        records += body["data"]
        if "next" not in body["links"]:
            assert body["meta"]["record_count"] == len(records)
            assert body["meta"]["page_count"] == page_number
            return records
        page_number += 1


@pytest.mark.parametrize("table", ROUTES)
def test_table(table):
    expected = TABLES[table]
    records = all_pages(ROUTES[table])
    assert len(records) == len(expected)
    assert list(records[0]) == list(expected[0])
    columns = list(expected[0])
    assert [[as_csv(r[c]) for c in columns] for r in records] == [
        [r[c] for c in columns] for r in expected
    ]


@pytest.mark.parametrize(
    "table,by",
    [(table, by) for table, groups in COUNTS.items() for by in groups],
)
def test_counts(table, by):
    columns = by.split(",") + ["count"]
    records = all_pages(f"counts/{ROUTES[table]}", {"by": by})
    assert [[as_csv(r[c]) for c in columns] for r in records] == [
        [r[c] for c in columns] for r in COUNTS[table][by]
    ]


@pytest.mark.parametrize("table", WEIGHTS)
def test_every_grouping_adds_up_to_the_table(table):
    total = sum(int(r[WEIGHTS[table]]) for r in TABLES[table])
    for by, rows in COUNTS[table].items():
        assert sum(int(r["count"]) for r in rows) == total, by


@pytest.mark.parametrize(
    "table,groupings",
    [("officer", 10 + 9 + 1), ("applicant", 8 + 7 + 1)],
)
def test_expected_files_cover_every_grouping(table, groupings):
    """So that a truncated or stale file can't pass by testing less: each column, year
    with each other column, and the four-column grouping"""
    assert len(COUNTS[table]) == groupings
    keys = [c for c in TABLES[table][0] if c != WEIGHTS[table]]
    assert set(keys) <= set(COUNTS[table])
