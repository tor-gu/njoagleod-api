"""template.yaml, the spec and the handler agree on the routes"""

import os
import re

import yaml

from diversity.app.diversity_api import ROUTES
from scripts import apigateway_spec

REPO = os.path.join(os.path.dirname(__file__), "..", "..")
SPEC = "officer-diversity-openapi.yaml"


class CfnLoader(yaml.SafeLoader):
    """Reads CloudFormation's short-form tags (!Ref, !Sub, ...) as plain values"""


CfnLoader.add_multi_constructor(
    "!",
    lambda loader, suffix, node: (
        loader.construct_scalar(node)
        if isinstance(node, yaml.ScalarNode)
        else loader.construct_sequence(node)
    ),
)


def load(name, loader=yaml.SafeLoader):
    with open(os.path.join(REPO, name), encoding="utf-8") as f:
        return yaml.load(f, Loader=loader)


def functions(template):
    return {
        name: resource["Properties"]
        for name, resource in template["Resources"].items()
        if resource["Type"] == "AWS::Serverless::Function"
    }


def test_routes_events_and_spec_paths_are_the_same():
    template_functions = functions(load("template.yaml", CfnLoader))
    assert list(template_functions) == ["DiversityFunction"]
    events = template_functions["DiversityFunction"]["Events"].values()
    template_paths = {event["Properties"]["Path"] for event in events}
    spec_paths = set(load(SPEC)["paths"])
    assert template_paths == spec_paths
    assert spec_paths == set(ROUTES)
    assert len(ROUTES) == 6


def test_events_are_gets_on_the_api():
    props = functions(load("template.yaml", CfnLoader))["DiversityFunction"]
    for event in props["Events"].values():
        assert event["Type"] == "Api"
        assert event["Properties"]["Method"] == "GET"
        assert event["Properties"]["RestApiId"] == "OfficerDiversityApi"


def test_spec_integrations_call_the_function():
    for path, item in load(SPEC)["paths"].items():
        uri = item["get"]["x-amazon-apigateway-integration"]["uri"]["Fn::Sub"]
        assert re.search(r"\$\{(\w+)\.Arn\}", uri)[1] == "DiversityFunction", path


def test_handler_exists():
    props = functions(load("template.yaml", CfnLoader))["DiversityFunction"]
    module, handler = props["Handler"].rsplit(".", 1)
    path = os.path.join(REPO, props["CodeUri"], *module.split(".")) + ".py"
    with open(path, encoding="utf-8") as f:
        assert re.search(rf"^{handler} = ", f.read(), re.M), f"{handler} not in {path}"


def has_example_keys(node):
    """The spec's prose can say "for example", so this looks at the keys"""
    if isinstance(node, dict):
        return any(
            k in apigateway_spec.EXAMPLE_KEYS or has_example_keys(v)
            for k, v in node.items()
        )
    if isinstance(node, list):
        return any(has_example_keys(v) for v in node)
    return False


def test_has_example_keys():
    assert has_example_keys({"a": [{"example": 1}]})
    assert not has_example_keys({"a": "for example"})


def test_apigateway_spec_has_no_examples_or_nulls():
    spec = apigateway_spec.without_examples(load(SPEC))
    assert apigateway_spec.null_paths(spec) == []
    assert not has_example_keys(spec)
    # The integrations API Gateway needs are still there
    text = yaml.safe_dump(spec)
    assert text.count("x-amazon-apigateway-integration") == 6


def test_null_paths():
    assert apigateway_spec.null_paths({"a": [1, {"b": None}], "c": None}) == [
        "/a/1/b",
        "/c",
    ]


def test_counts_routes_have_their_own_throttle():
    settings = load("template.yaml", CfnLoader)["Resources"]["OfficerDiversityApi"][
        "Properties"
    ]["MethodSettings"]
    throttled = {s["ResourcePath"].replace("~1", "/")[1:] for s in settings[1:]}
    assert throttled == {r for r in ROUTES if "/counts/" in r}
