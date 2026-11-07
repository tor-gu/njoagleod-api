"""
Write the copy of the OpenAPI spec that template.yaml gives API Gateway.

Usage: python scripts/apigateway_spec.py [spec] [out]
       (defaults: officer-diversity-openapi.yaml, apigateway-openapi.yaml)

AWS::Include puts the whole spec into the CloudFormation template, and
CloudFormation rejects null values anywhere in a template. The spec's examples
show real nulls, so this copy drops every example and examples (API Gateway
doesn't use them) and fails if any null is left.
"""

import sys

import yaml

EXAMPLE_KEYS = {"example", "examples"}


def without_examples(node):
    """node with every example/examples key removed, recursively"""
    if isinstance(node, dict):
        return {
            k: without_examples(v) for k, v in node.items() if k not in EXAMPLE_KEYS
        }
    if isinstance(node, list):
        return [without_examples(v) for v in node]
    return node


def null_paths(node, path=""):
    """The paths of all None values in node"""
    if node is None:
        return [path or "/"]
    if isinstance(node, dict):
        return [p for k, v in node.items() for p in null_paths(v, f"{path}/{k}")]
    if isinstance(node, list):
        return [p for i, v in enumerate(node) for p in null_paths(v, f"{path}/{i}")]
    return []


def main(argv):
    src = argv[1] if len(argv) > 1 else "officer-diversity-openapi.yaml"
    out = argv[2] if len(argv) > 2 else "apigateway-openapi.yaml"
    with open(src, encoding="utf-8") as f:
        spec = without_examples(yaml.safe_load(f))
    nulls = null_paths(spec)
    if nulls:
        sys.exit(
            f"apigateway_spec: null values (not allowed in templates): {nulls[:10]}"
        )
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Generated from {src} by scripts/apigateway_spec.py; do not edit\n")
        yaml.safe_dump(spec, f, sort_keys=False, allow_unicode=True)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main(sys.argv)
