"""Matcher: pure DSA-backed decisions, no storage."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from capability_oriented_dsa import DSAFacade

from conftest import line
from reconciliation_service.models.records import OpenItem
from reconciliation_service.services.matching import Matcher, duplicate_of

T0 = datetime(2026, 11, 2, tzinfo=timezone.utc)


def item(sid: str, amount: str, minutes: int = 0) -> OpenItem:
    return OpenItem(settlement_id=sid, account="ACC-PAYEE-1", amount=Decimal(amount), currency="EUR",
                    settled_at=T0 + timedelta(minutes=minutes))


def test_exact_by_reference_wins_over_older_equal_amount():
    d = Matcher().decide(line("L1", "100.00", reference="S2"), [item("S1", "100.00", 0), item("S2", "100.00", 5)])
    assert (d.match_type, [i.settlement_id for i in d.items]) == ("EXACT", ["S2"])


def test_fifo_takes_the_oldest_equal_amount():
    d = Matcher().decide(line("L1", "100.00"), [item("S1", "100.00", 0), item("S2", "100.00", 5)])
    assert (d.match_type, [i.settlement_id for i in d.items]) == ("FIFO", ["S1"])


def test_subset_finds_the_smallest_combination():
    items = [item("S1", "40.00", 0), item("S2", "60.00", 1), item("S3", "25.00", 2), item("S4", "35.00", 3)]
    d = Matcher().decide(line("L1", "100.00"), items)
    assert d.match_type == "SUBSET"
    assert sorted(i.settlement_id for i in d.items) == ["S1", "S2"]


def test_no_combination_is_unmatched_not_ambiguous():
    d = Matcher().decide(line("L1", "100.00"), [item("S1", "30.00"), item("S2", "50.00")])
    assert d.match_type is None and not d.ambiguous


def test_a_search_stopped_by_its_bound_is_ambiguous():
    items = [item(f"S{i}", "10.00", i) for i in range(6)]          # 3 items needed; 2 states allowed
    d = Matcher(max_nodes=2).decide(line("L1", "30.00"), items)
    assert d.match_type is None and d.ambiguous and "stopped at its bound" in d.reason


def test_nearest_uses_lower_bound_and_orders_by_distance():
    items = [item("S1", "10.00"), item("S2", "98.50"), item("S3", "101.00"), item("S4", "300.00")]
    near = Matcher().nearest(Decimal("100.00"), items, count=2)
    assert [i.settlement_id for i in near] == ["S3", "S2"]


def test_duplicate_cluster_returns_the_earliest_line():
    first = line("L1", "100.00", txn="T-9", day=3).model_dump(mode="json")
    again = line("L2", "100.00", txn="T-9", day=4).model_dump(mode="json")
    other = line("L3", "55.00", day=3).model_dump(mode="json")
    assert duplicate_of(again, [first, other], DSAFacade()) == "L1"
    assert duplicate_of(other, [first], DSAFacade()) is None
