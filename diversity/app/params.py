"""Request parameters: errors, paging and the filter values"""

import re

from torguapi import TorguapiInvalidRequest, torguapi_get_page_parameters


class InvalidRequest(Exception):
    """A bad request (400)"""

    pass


class NotFound(Exception):
    """Nothing matches the request (404)"""

    pass


PAGE_PARAMS = ["page_number", "page_size"]

AGENCY_ID_PATTERN = re.compile(r"^NJLEA[0-9]{4}$")

MAX_YEAR_DIGITS = 9
LOGICALS = {"true": True, "false": False}


def query_parameters(event):
    """The event's query parameters as a dict (never None)"""
    return event.get("queryStringParameters") or {}


def path_parameters(event):
    """The event's path parameters as a dict (never None)"""
    return event.get("pathParameters") or {}


def check_allowed(query, allowed):
    """InvalidRequest for any query parameter not in allowed"""
    unknown = sorted(set(query) - set(allowed))
    if unknown:
        raise InvalidRequest(f"Unknown query parameter {unknown[0]}")


def page_parameters(query):
    """page_number (default 1) and page_size (default 100) as ints"""
    try:
        params = torguapi_get_page_parameters(query)
    except TorguapiInvalidRequest as e:
        raise InvalidRequest(str(e))
    params.setdefault("page_number", 1)
    if params["page_number"] < 1:
        raise InvalidRequest(f"Invalid page_number {query.get('page_number')}")
    return params


def is_short_int(value):
    """value is ASCII digits, few enough for int()"""
    return value.isascii() and value.isdigit() and len(value) <= MAX_YEAR_DIGITS


def parse_year(name, value):
    """A year: not a number is a 400; a year with no data is a 404 when it's looked up"""
    if not is_short_int(value):
        raise InvalidRequest(f"Invalid {name} {value}")
    return int(value)


def parse_agency_id(name, value):
    if not AGENCY_ID_PATTERN.fullmatch(value):
        raise InvalidRequest(f"Invalid {name} {value} (expected NJLEA and 4 digits)")
    return value


def parse_level(name, value, levels):
    if value not in levels:
        raise InvalidRequest(
            f"Invalid {name} {value} (expected one of {', '.join(levels)})"
        )
    return value


def parse_logical(name, value):
    if value not in LOGICALS:
        raise InvalidRequest(f"Invalid {name} {value} (expected true or false)")
    return LOGICALS[value]
