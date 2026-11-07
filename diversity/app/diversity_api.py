"""Lambda handler: routes /nj/officer_diversity/* events and builds the torguapi replies"""

import traceback
from dataclasses import dataclass
from http import HTTPStatus

from torguapi import torguapi_http_error, torguapi_make_links_and_meta, torguapi_result

from . import diversity_lib as lib
from .params import (
    PAGE_PARAMS,
    InvalidRequest,
    NotFound,
    check_allowed,
    page_parameters,
    parse_agency_id,
    parse_level,
    parse_logical,
    parse_year,
    path_parameters,
    query_parameters,
)

ROOT = "/nj/officer_diversity"


@dataclass
class Reply:
    """
    What a route returns.

    records: list of dicts
    aux: for torguapi_make_links_and_meta; without page_number, the links
        have only "self" and there is no meta (single-record replies)
    query_params: the checked query parameters to carry in the links
    """

    records: list
    aux: dict
    query_params: dict | None = None


def make_handler(routes):
    """
    Returns a Lambda handler for routes, a dict of API Gateway resource
    (e.g. "/nj/officer_diversity/officers") -> function(path, query) returning a
    Reply. path and query are the event's parameters as dicts.
    """

    def handler(event, context):
        resource = event.get("resource")
        route = routes.get(resource)
        if route is None:
            return torguapi_http_error(HTTPStatus.NOT_FOUND, f"No route for {resource}")
        path = path_parameters(event)
        query = query_parameters(event)
        try:
            reply = route(path, query)
            url_path = resource.format(**path)
            links, meta = torguapi_make_links_and_meta(
                reply.aux, url_path.lstrip("/"), reply.query_params
            )
            return torguapi_result(reply.records, links, meta)
        except InvalidRequest as e:
            return torguapi_http_error(HTTPStatus.BAD_REQUEST, str(e))
        except NotFound as e:
            return torguapi_http_error(HTTPStatus.NOT_FOUND, str(e))
        except Exception:
            traceback.print_exc()
            return torguapi_http_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error"
            )

    return handler


def parse_value(table, column, value):
    """A query value for one of the table's key columns, checked for its type"""
    meta = table.by_name[column]
    if column == "agency_id":
        return parse_agency_id(column, value)
    if meta["type"] == "integer":
        return parse_year(column, value)
    if meta["type"] == "logical":
        return parse_logical(column, value)
    return parse_level(column, value, meta["labels"])


def parse_filters(table, query):
    """
    Checks the query's filters, which are the table's key columns.

    Returns:
        tuple of (column, code), as Table.selection() takes it
        dict of the filters as given, for the links

    Raises:
        NotFound for a valid value that no row can have (a year or agency_id
        not in the table)
    """
    filters = []
    link_params = {}
    for column in table.keys:
        if column in query:
            code = table.code(column, parse_value(table, column, query[column]))
            if code is None:
                raise NotFound("No matching records")
            filters.append((column, code))
            link_params[column] = query[column]
    return tuple(filters), link_params


def rows_route(name):
    """All of a table's rows, with its key columns as filters"""

    def route(path, query):
        table = lib.get_data().tables[name]
        check_allowed(query, table.keys + PAGE_PARAMS)
        filters, link_params = parse_filters(table, query)
        records, aux = lib.get_rows(table, filters, page_parameters(query))
        return Reply(records, aux, link_params)

    return route


def counts_route(name):
    """A count table's totals, grouped by the by columns"""

    def route(path, query):
        table = lib.get_data().tables[name]
        check_allowed(query, ["by"] + table.keys + PAGE_PARAMS)
        dimensions = lib.parse_by(table, query.get("by"))
        filters, link_params = parse_filters(table, query)
        records, aux = lib.get_counts(
            table, dimensions, filters, page_parameters(query)
        )
        return Reply(records, aux, {**link_params, "by": query["by"]})

    return route


def agency_practice(path, query):
    """One agency-year of agency_practice"""
    table = lib.get_data().tables["agency_practice"]
    check_allowed(query, [])
    year = parse_year("year", path["year"])
    agency_id = parse_agency_id("agency_id", path["agency_id"])
    not_found = NotFound(f"Agency {agency_id} not found in {year}")
    code = table.code("agency_id", agency_id)
    if code is None:
        raise not_found
    record = lib.get_row(table, (("year", year), ("agency_id", code)))
    if record is None:
        raise not_found
    return Reply([record], {})


ROUTES = {
    f"{ROOT}/officers": rows_route("officer"),
    f"{ROOT}/applicants": rows_route("applicant"),
    f"{ROOT}/counts/officers": counts_route("officer"),
    f"{ROOT}/counts/applicants": counts_route("applicant"),
    f"{ROOT}/agency_practices": rows_route("agency_practice"),
    f"{ROOT}/agency_practices/{{year}}/{{agency_id}}": agency_practice,
}

diversity_handler = make_handler(ROUTES)
