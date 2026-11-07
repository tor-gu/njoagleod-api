import json
import os
import shutil
import sys

import pytest

from diversity.app import diversity_lib

from .conftest import call

PRACTICE = "/agency_practices/{year}/{agency_id}"


def officer(year, agency, race, gender, promoted, count):
    return {
        "year": year,
        "agency_id": agency,
        "officer_race": race,
        "officer_gender": gender,
        "promoted": promoted,
        "officer_count": count,
    }


# Rows


def test_officers_are_rows_in_r_order_with_typed_values():
    status, body = call("/officers")
    assert status == 200
    assert body["data"] == [
        officer(2021, "NJLEA0002", "White", "Male", None, 3),
        officer(2021, "NJLEA0001", "Asian", "Female", None, 1),
        officer(2021, "NJLEA0001", None, "Male", None, 2),
        officer(2022, "NJLEA0001", "White", "Male", True, 4),
        officer(2022, "NJLEA0001", "White", "Male", False, 5),
        officer(2022, "NJLEA0002", "Asian", None, False, 6),
        officer(2022, "NJLEA0002", "White", "Female", True, 7),
    ]
    assert body["meta"] == {"record_count": 7, "page_count": 1}
    assert (
        body["links"]["self"]
        == "https://api.example.com/nj/officer_diversity/officers?page_number=1&page_size=100"
    )


def test_applicants():
    status, body = call("/applicants", query={"outcome": "Pending"})
    assert status == 200
    assert body["data"] == [
        {
            "year": 2022,
            "agency_id": "NJLEA0001",
            "outcome": "Pending",
            "applicant_count": 2,
        }
    ]


@pytest.mark.parametrize(
    "query,counts",
    [
        ({"year": "2021"}, [3, 1, 2]),
        ({"agency_id": "NJLEA0002"}, [3, 6, 7]),
        ({"officer_race": "Asian"}, [1, 6]),
        ({"officer_gender": "Male"}, [3, 2, 4, 5]),
        ({"promoted": "true"}, [4, 7]),
        ({"promoted": "false"}, [5, 6]),
        ({"year": "2022", "officer_race": "White", "promoted": "true"}, [4, 7]),
        ({"agency_id": "NJLEA0001", "officer_gender": "Male", "year": "2021"}, [2]),
    ],
)
def test_filters_are_anded_and_never_select_null(query, counts):
    status, body = call("/officers", query=query)
    assert status == 200
    assert [r["officer_count"] for r in body["data"]] == counts


def test_filters_are_in_the_links():
    query = {"year": "2022", "promoted": "true", "page_size": "1"}
    status, body = call("/officers", query=query)
    assert status == 200
    base = (
        "https://api.example.com/nj/officer_diversity/officers?promoted=true&year=2022"
    )
    assert body["links"] == {
        "self": f"{base}&page_number=1&page_size=1",
        "next": f"{base}&page_number=2&page_size=1",
    }


def test_paging():
    status, body = call("/officers", query={"page_size": "3", "page_number": "2"})
    assert status == 200
    assert [r["officer_count"] for r in body["data"]] == [4, 5, 6]
    assert body["meta"] == {"record_count": 7, "page_count": 3}
    assert set(body["links"]) == {"self", "previous", "next"}
    status, body = call("/officers", query={"page_size": "3", "page_number": "3"})
    assert [r["officer_count"] for r in body["data"]] == [7]
    assert set(body["links"]) == {"self", "previous"}


# Counts


def totals(body, *columns):
    return [(*(r[c] for c in columns), r["count"]) for r in body["data"]]


@pytest.mark.parametrize(
    "by,column,expected",
    [
        # Summed weights, not rows
        ("year", "year", [(2021, 6), (2022, 22)]),
        # Sorted IDs, whatever the row order
        ("agency_id", "agency_id", [("NJLEA0001", 12), ("NJLEA0002", 16)]),
        # Level order, not alphabetical; null last; unused levels left out
        ("officer_race", "officer_race", [("White", 19), ("Asian", 7), (None, 2)]),
        (
            "officer_gender",
            "officer_gender",
            [("Male", 14), ("Female", 8), (None, 6)],
        ),
        # false, true, null
        ("promoted", "promoted", [(False, 11), (True, 11), (None, 6)]),
    ],
)
def test_counts_by_one_column(by, column, expected):
    status, body = call("/counts/officers", query={"by": by})
    assert status == 200
    assert totals(body, column) == expected


def test_counts_records_have_only_the_by_columns_and_count():
    status, body = call("/counts/officers", query={"by": "year,promoted"})
    assert status == 200
    assert set(body["data"][0]) == {"year", "promoted", "count"}


def test_counts_order_by_the_columns_as_given():
    status, body = call("/counts/officers", query={"by": "promoted,year"})
    assert status == 200
    assert totals(body, "promoted", "year") == [
        (False, 2022, 11),
        (True, 2022, 11),
        (None, 2021, 6),
    ]


def test_counts_with_filters():
    query = {"by": "officer_gender", "year": "2022"}
    status, body = call("/counts/officers", query=query)
    assert status == 200
    assert totals(body, "officer_gender") == [("Male", 9), ("Female", 7), (None, 6)]
    # A filter on a by column
    query = {"by": "officer_race", "officer_race": "Asian"}
    status, body = call("/counts/officers", query=query)
    assert totals(body, "officer_race") == [("Asian", 7)]


def test_counts_with_four_columns():
    by = "year,agency_id,officer_race,officer_gender"
    status, body = call("/counts/officers", query={"by": by, "year": "2022"})
    assert status == 200
    assert totals(body, *by.split(",")) == [
        (2022, "NJLEA0001", "White", "Male", 9),
        (2022, "NJLEA0002", "White", "Female", 7),
        (2022, "NJLEA0002", "Asian", None, 6),
    ]


def test_counts_links_carry_by_and_filters():
    query = {"by": "year,promoted", "agency_id": "NJLEA0001", "page_size": "1"}
    status, body = call("/counts/officers", query=query)
    assert status == 200
    assert (
        body["links"]["next"]
        == "https://api.example.com/nj/officer_diversity/counts/officers"
        "?agency_id=NJLEA0001&by=year%2Cpromoted&page_number=2&page_size=1"
    )


def test_counts_paging_is_over_groups():
    status, body = call(
        "/counts/officers",
        query={"by": "officer_race", "page_size": "2", "page_number": "2"},
    )
    assert status == 200
    assert totals(body, "officer_race") == [(None, 2)]
    assert body["meta"] == {"record_count": 3, "page_count": 2}


def test_applicant_counts():
    status, body = call("/counts/applicants", query={"by": "outcome"})
    assert status == 200
    assert totals(body, "outcome") == [("Not Appointed", 3), ("Pending", 2), (None, 1)]


# Practices


def test_agency_practices():
    status, body = call("/agency_practices", query={"year": "2022"})
    assert status == 200
    assert body["data"] == [
        {
            "year": 2022,
            "agency_id": "NJLEA0001",
            "hiring_civil_service": True,
            "hire_method_waiver": False,
        },
        {
            "year": 2022,
            "agency_id": "NJLEA0002",
            "hiring_civil_service": False,
            "hire_method_waiver": None,
        },
    ]


def test_agency_practices_answers_are_filters():
    query = {"hiring_civil_service": "true"}
    status, body = call("/agency_practices", query=query)
    assert status == 200
    assert body["meta"]["record_count"] == 2


def test_one_agency_practice():
    path = {"year": "2023", "agency_id": "NJLEA0001"}
    status, body = call(PRACTICE, path=path)
    assert status == 200
    assert body["data"] == [
        {
            "year": 2023,
            "agency_id": "NJLEA0001",
            "hiring_civil_service": True,
            "hire_method_waiver": True,
        }
    ]
    assert body["links"] == {
        "self": "https://api.example.com/nj/officer_diversity/agency_practices/2023/NJLEA0001"
    }
    assert "meta" not in body


# Errors


@pytest.mark.parametrize(
    "resource,query,message",
    [
        ("/officers", {"colour": "red"}, "Unknown query parameter colour"),
        ("/officers", {"by": "year"}, "Unknown query parameter by"),
        ("/officers", {"officer_count": "1"}, "Unknown query parameter officer_count"),
        ("/applicants", {"officer_race": "Asian"}, "Unknown query parameter"),
        ("/officers", {"year": "abc"}, "Invalid year abc"),
        ("/officers", {"year": "2" * 5000}, "Invalid year"),
        ("/officers", {"agency_id": "bad"}, "expected NJLEA"),
        ("/officers", {"officer_race": "white"}, "expected one of White, Asian, Other"),
        ("/officers", {"promoted": "TRUE"}, "expected true or false"),
        ("/officers", {"page_size": "0"}, "Invalid page_size"),
        ("/officers", {"page_number": "0"}, "Invalid page_number"),
        ("/counts/officers", {}, "by is required"),
        ("/counts/officers", {"by": ""}, "Unknown column"),
        ("/counts/officers", {"by": "year,"}, "Unknown column"),
        ("/counts/officers", {"by": "colour"}, "Unknown column colour"),
        ("/counts/officers", {"by": "officer_count"}, "Unknown column officer_count"),
        ("/counts/officers", {"by": "year,year"}, "Repeated column"),
        (
            "/counts/officers",
            {"by": "year,agency_id,officer_race,officer_gender,promoted"},
            "by needs 1 to 4",
        ),
        ("/counts/applicants", {"by": "officer_race"}, "Unknown column officer_race"),
        ("/counts/officers", {"by": "year", "year": "abc"}, "Invalid year"),
        ("/agency_practices", {"hiring_civil_service": "1"}, "expected true or false"),
    ],
)
def test_bad_requests(resource, query, message):
    status, body = call(resource, query=query)
    assert status == 400
    assert body["errors"][0]["status"] == "400"
    assert message in body["errors"][0]["detail"]


@pytest.mark.parametrize(
    "resource,query",
    [
        ("/officers", {"year": "1999"}),
        ("/officers", {"agency_id": "NJLEA9999"}),
        # Valid values, but no row has both
        ("/officers", {"year": "2021", "promoted": "true"}),
        # A level no row has
        ("/officers", {"officer_race": "Other"}),
        ("/officers", {"page_number": "2"}),
        ("/counts/officers", {"by": "year", "year": "1999"}),
        ("/counts/officers", {"by": "year", "agency_id": "NJLEA9999"}),
        ("/counts/officers", {"by": "year", "page_number": "2"}),
        ("/agency_practices", {"year": "2021"}),
    ],
)
def test_not_found(resource, query):
    status, body = call(resource, query=query)
    assert status == 404
    assert body["errors"][0]["status"] == "404"


@pytest.mark.parametrize(
    "path,query,status",
    [
        ({"year": "abc", "agency_id": "NJLEA0001"}, None, 400),
        ({"year": "2" * 5000, "agency_id": "NJLEA0001"}, None, 400),
        ({"year": "2022", "agency_id": "bad"}, None, 400),
        ({"year": "2022", "agency_id": "NJLEA0001"}, {"page_size": "1"}, 400),
        ({"year": "1999", "agency_id": "NJLEA0001"}, None, 404),
        ({"year": "2022", "agency_id": "NJLEA9999"}, None, 404),
        # In the table, but not in that year
        ({"year": "2023", "agency_id": "NJLEA0002"}, None, 404),
    ],
)
def test_one_agency_practice_errors(path, query, status):
    actual, body = call(PRACTICE, path=path, query=query)
    assert actual == status
    assert body["errors"][0]["status"] == str(status)


def test_unknown_route():
    status, body = call("/nope")
    assert status == 404
    assert "No route" in body["errors"][0]["detail"]


def test_unexpected_errors_are_500s_without_detail(monkeypatch):
    def fail():
        raise RuntimeError("secret detail")

    monkeypatch.setattr(diversity_lib, "get_data", fail)
    status, body = call("/officers")
    assert status == 500
    assert body["errors"][0]["detail"] == "Internal server error"


# Data loading


def test_a_request_loads_only_the_columns_it_uses():
    assert call("/counts/officers", query={"by": "year", "promoted": "true"})[0] == 200
    tables = diversity_lib.get_data().tables
    assert set(tables["officer"]._values) == {"year", "promoted", "officer_count"}
    assert tables["applicant"]._values == {}
    assert tables["agency_practice"]._values == {}


def test_repeated_requests_give_the_same_reply():
    query = {"by": "officer_race", "year": "2022"}
    assert call("/counts/officers", query=query) == call(
        "/counts/officers", query=query
    )
    query = {"promoted": "true"}
    assert call("/officers", query=query) == call("/officers", query=query)


def test_wrong_byte_order_is_refused(tmp_path, fixture_build, monkeypatch):
    data_dir = tmp_path / "data"
    shutil.copytree(fixture_build, data_dir)
    with open(os.path.join(fixture_build, "labels.json"), encoding="utf-8") as f:
        meta = json.load(f)
    meta["byteorder"] = "big" if sys.byteorder == "little" else "little"
    (data_dir / "labels.json").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    status, _ = call("/officers")
    assert status == 500
