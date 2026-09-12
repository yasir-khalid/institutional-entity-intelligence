"""Smoke tests for er.cli.entity_render - confirms it stays a pure presentation
layer (no live services, no argparse) and doesn't flood the terminal with a
row per relationship/identifier when an entity has many of either."""

import io

from rich.console import Console

from er.cli.entity_render import render
from er.entity.models import EntityIdentifier, EntityProfile
from er.graph.models import HierarchyResult, RelationshipEdge


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, width=100), buf


def test_render_minimal_profile_does_not_crash():
    console, buf = _console()
    profile = EntityProfile(entity_id="LEI_A", canonical_name="Acme Capital LLC")
    render(console, profile)
    output = buf.getvalue()
    assert "Acme Capital LLC" in output
    assert "not a resolved 13F filer" in output


def test_render_collapses_high_cardinality_identifiers():
    console, buf = _console()
    identifiers = [
        EntityIdentifier(identifier_type="ISIN", identifier_value=f"US{i:010d}", confidence="SOURCE", source="gleif")
        for i in range(20)
    ]
    profile = EntityProfile(entity_id="LEI_A", canonical_name="Acme Capital LLC", identifiers=identifiers)
    render(console, profile)
    output = buf.getvalue()
    assert "20 values" in output
    assert "US0000000019" not in output  # not every value dumped


def test_render_collapses_high_fanout_relationships():
    console, buf = _console()
    downward = [
        RelationshipEdge(lei=f"LEI_F{i}", name=f"Fund {i}", relationship_type="IS_FUND-MANAGED_BY", status="ACTIVE", label="Funds managed")
        for i in range(40)
    ]
    profile = EntityProfile(
        entity_id="LEI_A",
        canonical_name="Acme Capital LLC",
        hierarchy=HierarchyResult(lei="LEI_A", name="Acme Capital LLC", downward=downward),
    )
    render(console, profile)
    output = buf.getvalue()
    assert "40 entities" in output
    assert "er.cli.hierarchy --lei LEI_A" in output
    assert "Fund 39" not in output
