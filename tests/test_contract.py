import json
from pathlib import Path

from jsonschema import Draft202012Validator
from openapi_spec_validator import validate
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


SPEC = json.loads((Path(__file__).parents[1] / "openapi.json").read_text())


def test_openapi_is_valid():
    validate(SPEC)


def test_observed_fixture_shapes(membership_json, loan_json):
    registry = Registry().with_resource(
        "urn:agron", Resource.from_contents(SPEC, default_specification=DRAFT202012)
    )
    cases = {
        "LoginRequest": {"userid": membership_json["idNo"]},
        "Memberships": [membership_json],
        "LoanGroups": [
            {"listName": "history", "list": []},
            {"listName": "loans", "list": [loan_json]},
        ],
        "History": [loan_json],
        "RenewalRequest": [loan_json["copyNo"]],
    }
    for name, example in cases.items():
        Draft202012Validator(
            {"$ref": f"urn:agron#/components/schemas/{name}"}, registry=registry
        ).validate(example)
