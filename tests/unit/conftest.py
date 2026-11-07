import csv
import gzip
import json
import os

import pytest

from diversity.app import diversity_lib
from diversity.app.diversity_api import diversity_handler
from scripts import build_data

ROOT = "/nj/officer_diversity"

# A small export in R's row order, which is deliberately neither by agency nor by
# level. Levels aren't alphabetical, and every table has nulls ("").
COLUMNS = {
    "officer": [
        ("year", "integer"),
        ("agency_id", "character"),
        ("officer_race", "factor"),
        ("officer_gender", "factor"),
        ("promoted", "logical"),
        ("officer_count", "integer"),
    ],
    "applicant": [
        ("year", "integer"),
        ("agency_id", "character"),
        ("outcome", "factor"),
        ("applicant_count", "integer"),
    ],
    "agency_practice": [
        ("year", "integer"),
        ("agency_id", "character"),
        ("hiring_civil_service", "logical"),
        ("hire_method_waiver", "logical"),
    ],
}
ROWS = {
    "officer": [
        ["2021", "NJLEA0002", "White", "Male", "", "3"],
        ["2021", "NJLEA0001", "Asian", "Female", "", "1"],
        ["2021", "NJLEA0001", "", "Male", "", "2"],
        ["2022", "NJLEA0001", "White", "Male", "TRUE", "4"],
        ["2022", "NJLEA0001", "White", "Male", "FALSE", "5"],
        ["2022", "NJLEA0002", "Asian", "", "FALSE", "6"],
        ["2022", "NJLEA0002", "White", "Female", "TRUE", "7"],
    ],
    "applicant": [
        ["2022", "NJLEA0001", "Pending", "2"],
        ["2022", "NJLEA0001", "", "1"],
        ["2023", "NJLEA0002", "Not Appointed", "3"],
    ],
    "agency_practice": [
        ["2022", "NJLEA0001", "TRUE", "FALSE"],
        ["2022", "NJLEA0002", "FALSE", ""],
        ["2023", "NJLEA0001", "TRUE", "TRUE"],
    ],
}
LEVELS = {
    ("officer", "officer_race"): ["White", "Asian", "Other"],
    ("officer", "officer_gender"): ["Male", "Female", "X or Non-Binary"],
    ("applicant", "outcome"): ["Appointed to Agency", "Not Appointed", "Pending"],
}


def write_csv(path, header, rows):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def write_export(data_dir, rows=None, columns=None, levels=None):
    """Writes an export like scripts/export_data.R's, with parts replaced if given"""
    rows = {**ROWS, **(rows or {})}
    columns = {**COLUMNS, **(columns or {})}
    levels = levels if levels is not None else LEVELS
    for table, table_rows in rows.items():
        write_csv(
            os.path.join(data_dir, f"{table}.csv.gz"),
            [c for c, _ in columns[table]],
            table_rows,
        )
    write_csv(
        os.path.join(data_dir, "columns.csv"),
        ["table", "position", "column", "type"],
        [
            [table, i, c, t]
            for table, cols in columns.items()
            for i, (c, t) in enumerate(cols, 1)
        ],
    )
    write_csv(
        os.path.join(data_dir, "levels.csv"),
        ["table", "column", "position", "level"],
        [
            [table, column, i, level]
            for (table, column), values in levels.items()
            for i, level in enumerate(values, 1)
        ],
    )
    with open(os.path.join(data_dir, "SOURCE"), "w", encoding="utf-8") as f:
        f.write("package=njoagleod\nversion=0.0.0\n")


@pytest.fixture(scope="session")
def fixture_build(tmp_path_factory):
    """The directory of the data built from the fixture export, once per session"""
    export = str(tmp_path_factory.mktemp("export"))
    write_export(export)
    return build_data.build(export, str(tmp_path_factory.mktemp("build")))


@pytest.fixture(autouse=True)
def fixture_data(monkeypatch, fixture_build):
    """Points the function at the fixture build, reloaded for each test"""
    monkeypatch.setenv("DATA_DIR", fixture_build)
    monkeypatch.setenv("API_ROOT", "https://api.example.com")
    monkeypatch.setattr(diversity_lib, "_data", None)


def call(resource, path=None, query=None):
    """Calls the handler with a GET event; returns (status code, body)"""
    event = {
        "resource": ROOT + resource,
        "httpMethod": "GET",
        "pathParameters": path,
        "queryStringParameters": query,
    }
    reply = diversity_handler(event, None)
    assert reply["headers"]["Content-Type"] == "application/vnd.api+json"
    return int(reply["statusCode"]), json.loads(reply["body"])
