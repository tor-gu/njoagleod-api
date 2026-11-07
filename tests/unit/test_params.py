import pytest

from diversity.app.params import (
    InvalidRequest,
    check_allowed,
    page_parameters,
    parse_agency_id,
    parse_level,
    parse_logical,
    parse_year,
    path_parameters,
    query_parameters,
)


def test_event_parameters_are_never_none():
    event = {"queryStringParameters": None, "pathParameters": None}
    assert query_parameters(event) == {}
    assert path_parameters(event) == {}
    assert query_parameters({}) == {}
    assert path_parameters({}) == {}


def test_check_allowed():
    check_allowed({"year": "2021"}, ["year"])
    check_allowed({}, [])
    with pytest.raises(InvalidRequest, match="Unknown query parameter colour"):
        check_allowed({"year": "2021", "colour": "red"}, ["year"])


def test_page_parameters():
    assert page_parameters({}) == {"page_number": 1, "page_size": 100}
    assert page_parameters({"page_number": "3", "page_size": "7"}) == {
        "page_number": 3,
        "page_size": 7,
    }


@pytest.mark.parametrize(
    "query",
    [
        {"page_number": "0"},
        {"page_number": "x"},
        {"page_number": "-1"},
        {"page_number": "²"},
        {"page_number": "9" * 5000},
        {"page_size": "0"},
        {"page_size": "x"},
        {"page_size": "²"},
        {"page_size": "9" * 5000},
    ],
)
def test_page_parameters_invalid(query):
    with pytest.raises(InvalidRequest):
        page_parameters(query)


def test_parse_year():
    assert parse_year("year", "2024") == 2024
    assert parse_year("year", "1999") == 1999


@pytest.mark.parametrize(
    "value", ["", "x", "20.5", "-1", "²", "٢٠٢٤", "2" * 10, "2" * 5000]
)
def test_parse_year_invalid(value):
    with pytest.raises(InvalidRequest):
        parse_year("year", value)


def test_parse_agency_id():
    assert parse_agency_id("agency_id", "NJLEA0001") == "NJLEA0001"


@pytest.mark.parametrize(
    "value", ["", "NJLEA1", "njlea0001", "NJLEA00011", "NJLEA0001\n", "A0001"]
)
def test_parse_agency_id_invalid(value):
    with pytest.raises(InvalidRequest, match="expected NJLEA"):
        parse_agency_id("agency_id", value)


def test_parse_level():
    assert parse_level("outcome", "Pending", ["Pending", "Other"]) == "Pending"
    with pytest.raises(InvalidRequest, match="expected one of Pending, Other"):
        parse_level("outcome", "pending", ["Pending", "Other"])


def test_parse_logical():
    assert parse_logical("promoted", "true") is True
    assert parse_logical("promoted", "false") is False


@pytest.mark.parametrize("value", ["", "TRUE", "True", "1", "yes"])
def test_parse_logical_invalid(value):
    with pytest.raises(InvalidRequest, match="expected true or false"):
        parse_logical("promoted", value)
