"""
The OpenAPI spec against the full data (make data).

Each example's request is turned into an API Gateway event and passed to the
handler; the reply must equal the example: data, links and meta. After a data
refresh, the failures show the new values to copy into the spec. The spec's
enums and parameters must also be the data's.
"""

import json
import re
from urllib.parse import parse_qsl, urlsplit

import pytest

from diversity.app import diversity_lib
from diversity.app.diversity_api import diversity_handler
from tests.spec_examples import load_examples, load_spec

API_ROOT = "https://api.tor-gu.com"
ROOT = "/nj/officer_diversity"

# Route -> the table whose key columns are its filters
FILTERED_ROUTES = {
    f"{ROOT}/officers": "officer",
    f"{ROOT}/applicants": "applicant",
    f"{ROOT}/counts/officers": "officer",
    f"{ROOT}/counts/applicants": "applicant",
    f"{ROOT}/agency_practices": "agency_practice",
}


def event_for(resource, url):
    """The API Gateway event for a GET of url, served by resource"""
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == API_ROOT
    pattern = (
        "^" + re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>[^/]+)", re.escape(resource)) + "$"
    )
    match = re.match(pattern, parts.path)
    assert match, f"{parts.path} doesn't match {resource}"
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    return {
        "resource": resource,
        "path": parts.path,
        "httpMethod": "GET",
        "pathParameters": match.groupdict() or None,
        "queryStringParameters": query or None,
    }


@pytest.mark.parametrize("resource,url,example", load_examples())
def test_spec_example(monkeypatch, resource, url, example):
    monkeypatch.setenv("API_ROOT", API_ROOT)
    reply = diversity_handler(event_for(resource, url), None)
    body = json.loads(reply["body"])
    assert reply["statusCode"] == 200, body
    expected = {k: example[k] for k in ("data", "links", "meta") if k in example}
    actual = {k: body[k] for k in ("data", "links", "meta") if k in body}
    assert actual == expected, "actual reply:\n" + json.dumps(actual, indent=1)


def test_every_path_has_an_example():
    examples = {case.values[0] for case in load_examples()}
    assert examples == set(load_spec()["paths"])


def labels(table, column):
    return diversity_lib.get_data().tables[table].by_name[column]["labels"]


@pytest.mark.parametrize(
    "schema,table,column",
    [
        ("race", "officer", "officer_race"),
        ("race", "applicant", "applicant_race"),
        ("ageRange", "officer", "officer_age_range"),
        ("ageRange", "applicant", "applicant_age_range"),
        ("gender", "officer", "officer_gender"),
        ("gender", "applicant", "applicant_gender"),
        ("rank", "officer", "old_rank"),
        ("rank", "officer", "new_rank"),
        ("applicantType", "applicant", "applicant_type"),
        ("outcome", "applicant", "outcome"),
        ("noAppointmentReason", "applicant", "no_appointment_reason"),
    ],
)
def test_spec_enums_are_the_datas_levels(schema, table, column):
    enum = load_spec()["components"]["schemas"][schema]["enum"]
    assert enum == labels(table, column)


def resolve(spec, parameter):
    name = parameter["$ref"].rsplit("/", 1)[1]
    return spec["components"]["parameters"][name]


@pytest.mark.parametrize("route,table", FILTERED_ROUTES.items())
def test_spec_parameters_are_the_tables_filters(route, table):
    spec = load_spec()
    names = {resolve(spec, p)["name"] for p in spec["paths"][route]["parameters"]}
    expected = set(diversity_lib.get_data().tables[table].keys)
    expected |= {"page_number", "page_size"}
    if "/counts/" in route:
        expected.add("by")
    assert names == expected


@pytest.mark.parametrize(
    "parameter,table", [("byOfficers", "officer"), ("byApplicants", "applicant")]
)
def test_spec_by_lists_the_tables_columns(parameter, table):
    description = load_spec()["components"]["parameters"][parameter]["description"]
    listed = re.findall(r"`(\w+)`", description)
    assert listed == diversity_lib.get_data().tables[table].keys


@pytest.mark.parametrize(
    "schema,table",
    [
        ("officer", "officer"),
        ("applicant", "applicant"),
        ("agencyPractice", "agency_practice"),
    ],
)
def test_spec_record_schemas_have_the_tables_columns(schema, table):
    properties = load_spec()["components"]["schemas"][schema]["properties"]
    assert list(properties) == diversity_lib.get_data().tables[table].names
