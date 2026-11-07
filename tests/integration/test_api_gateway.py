"""
The deployed API, through API Gateway (not CloudFront).

Needs AWS_SAM_STACK_NAME, the stack to test, and credentials that allow
cloudformation:DescribeStacks on it. Every example in the spec is requested
from the stack's URL and must return the example's data and meta (links name
the environment's API root, so they aren't compared).
"""

import os
from urllib.parse import urlsplit

import boto3
import pytest
import requests

from tests.spec_examples import load_examples


@pytest.fixture(scope="module")
def api_url():
    stack_name = os.environ.get("AWS_SAM_STACK_NAME")
    if not stack_name:
        pytest.fail("Set AWS_SAM_STACK_NAME to the stack to test")
    stack = boto3.client("cloudformation").describe_stacks(StackName=stack_name)[
        "Stacks"
    ][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
    # e.g. https://abc.execute-api.us-east-1.amazonaws.com/Prod/nj/officer_diversity/
    return outputs["OfficerDiversityApiUrl"]


def stack_url(api_url, example_url):
    """example_url (on api.tor-gu.com) on the stack's API Gateway stage"""
    parts = urlsplit(example_url)
    stage_root = api_url[: api_url.index("/nj/officer_diversity/")]
    return stage_root + parts.path + (f"?{parts.query}" if parts.query else "")


@pytest.mark.parametrize("resource,url,example", load_examples())
def test_spec_example(api_url, resource, url, example):
    response = requests.get(stack_url(api_url, url), timeout=30)
    assert response.status_code == 200, response.text
    assert response.headers["Content-Type"] == "application/vnd.api+json"
    body = response.json()
    assert body["data"] == example["data"]
    assert body.get("meta") == example.get("meta")


@pytest.mark.parametrize(
    "path,status",
    [
        ("officers", 200),
        ("officers?year=2025&agency_id=NJLEA0199", 200),
        ("officers?year=1999", 404),
        ("officers?year=abc", 400),
        ("officers?colour=red", 400),
        ("officers?page_number=99999", 404),
        ("officers?page_size=0", 400),
        ("officers?officer_gender=male", 400),
        ("officers?promoted=TRUE", 400),
        ("officers?agency_id=bad", 400),
        ("officers?agency_id=NJLEA9999", 404),
        ("applicants?outcome=Pending", 200),
        ("applicants?officer_race=Asian", 400),
        ("counts/officers", 400),
        ("counts/officers?by=year", 200),
        ("counts/officers?by=year,agency_id,officer_race,officer_gender", 200),
        ("counts/officers?by=year,agency_id,officer_race,officer_gender,promoted", 400),
        ("counts/officers?by=colour", 400),
        ("counts/applicants?by=outcome", 200),
        ("agency_practices?year=2025", 200),
        ("agency_practices?year=2021", 404),
        ("agency_practices/2025/NJLEA0199", 200),
        ("agency_practices/2021/NJLEA0199", 404),
        ("agency_practices/abc/NJLEA0199", 400),
        ("agency_practices/2025/bad", 400),
    ],
)
def test_status(api_url, path, status):
    response = requests.get(api_url + path, timeout=30)
    assert response.status_code == status, response.text
    if status != 200:
        assert response.json()["errors"][0]["status"] == str(status)


def test_paging(api_url):
    """One record a page: as many pages as records, and a next link from the first"""
    body = requests.get(
        api_url + "counts/officers?by=year&page_size=1", timeout=30
    ).json()
    assert body["meta"]["page_count"] == body["meta"]["record_count"]
    assert "next" in body["links"]
    assert "previous" not in body["links"]
