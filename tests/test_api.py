"""Unit tests for the FastAPI backend's pure conversion logic - _convert_tree()
translates er.graph.models.HierarchyNode into the frontend-facing TreeNode
shape. No live OpenSearch/DuckDB needed; the search/detail endpoints themselves
are exercised manually (see docs/phases.md Phase 13) since they need live data."""

from er.api.app import _convert_tree
from er.graph.models import HierarchyNode


def test_convert_tree_root_has_no_direction():
    node = HierarchyNode(lei="LEI_A", name="Acme")
    tree = _convert_tree(node, None)
    assert tree.entity_id == "LEI_A"
    assert tree.direction is None
    assert tree.children == []


def test_convert_tree_tags_upward_and_downward_children():
    node = HierarchyNode(
        lei="LEI_A",
        name="Acme",
        upward=[HierarchyNode(lei="LEI_P", name="Parent Co", label="Direct parent")],
        downward=[HierarchyNode(lei="LEI_C", name="Fund I", label="Funds managed")],
    )
    tree = _convert_tree(node, None)
    directions = {c.entity_id: c.direction for c in tree.children}
    assert directions == {"LEI_P": "upward", "LEI_C": "downward"}


def test_convert_tree_recurses_into_grandchildren():
    grandchild = HierarchyNode(lei="LEI_GP", name="Grandparent")
    node = HierarchyNode(
        lei="LEI_A",
        name="Acme",
        upward=[HierarchyNode(lei="LEI_P", name="Parent Co", upward=[grandchild])],
    )
    tree = _convert_tree(node, None)
    parent = tree.children[0]
    assert parent.children[0].entity_id == "LEI_GP"
    assert parent.children[0].direction == "upward"
