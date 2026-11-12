"""Consumer-side contract tests: what this service reads and accepts matches the schemas."""
import json
from pathlib import Path

import jsonschema
import pytest

from conftest import FakeFeed, line
from reconciliation_service.models.records import BankLine

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


def validator(relative: str) -> jsonschema.Draft202012Validator:
    schema = json.loads((CONTRACTS / relative).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def test_the_events_the_tests_feed_in_are_valid_settlement_events():
    feed = FakeFeed()
    feed.completed("S1", "100.00")
    errors = [e.message for e in validator("vendor/settlement-event.v1.schema.json").iter_errors(feed.events[0])]
    assert errors == []


@pytest.mark.parametrize("example", sorted((CONTRACTS / "statements" / "examples").glob("*.json")))
def test_statement_examples_are_valid_and_parse(example):
    lines = json.loads(example.read_text(encoding="utf-8"))
    v = validator("statements/bank-statement-line.v1.schema.json")
    for raw in lines:
        assert [e.message for e in v.iter_errors(raw)] == []
        assert BankLine.model_validate(raw).line_id == raw["line_id"]


def test_what_the_service_serialises_satisfies_the_statement_contract():
    raw = line("L1", "247.50").model_dump(mode="json")
    assert [e.message for e in validator("statements/bank-statement-line.v1.schema.json").iter_errors(raw)] == []
