"""The example replies in the OpenAPI spec, as pytest parameters"""

import os

import pytest
import yaml

REPO = os.path.join(os.path.dirname(__file__), "..")
SPEC = os.path.join(REPO, "officer-diversity-openapi.yaml")


def load_spec():
    with open(SPEC, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_examples():
    """
    pytest.param(resource, url, example) for every 200 example. url is what to
    request: the example's x-request when it has one (a defaulted year, whose
    links.self is the explicit-year URL), else its links.self.
    """
    cases = []
    for path, item in load_spec()["paths"].items():
        content = item["get"]["responses"]["200"]["content"]["application/vnd.api+json"]
        if "examples" in content:
            examples = content["examples"]
        else:
            examples = {"example": {"value": content["example"]}}
        for name, example in examples.items():
            value = example["value"]
            url = example.get("x-request", value["links"]["self"])
            cases.append(pytest.param(path, url, value, id=f"{path} {name}"))
    return cases
