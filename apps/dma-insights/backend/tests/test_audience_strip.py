"""Tests for audience_strip — the server-side D5/D6 / internal-field redactor."""
from __future__ import annotations

from app.services.audience_strip import strip_internal


def test_internal_view_is_passthrough() -> None:
    obj = {
        "name": "Farm Credit East",
        "context": {"timeline": []},
        "health": {"alerts": [], "data_gaps": []},
        "scores": {"P1": 3.2},
    }
    out = strip_internal(obj, "internal")
    assert out == obj


def test_customer_view_strips_top_level_internal_keys() -> None:
    obj = {
        "name": "Farm Credit East",
        "context": {"timeline": []},
        "health": {"alerts": []},
        "alerts": [{"id": "A1"}],
        "scores": {"P1": 3.2},
        "data_gaps": [],
    }
    out = strip_internal(obj, "customer")
    assert "context" not in out
    assert "health" not in out
    assert "alerts" not in out
    assert "data_gaps" not in out
    assert out["name"] == "Farm Credit East"
    assert out["scores"] == {"P1": 3.2}


def test_customer_view_strips_nested_keys() -> None:
    obj = {
        "subcap": {
            "id": "P1C1.1.1",
            "score": 3.5,
            "rationale_internal": "internal note",
            "drive_url": "https://drive.google.com/x",
            "analyst_note": "..."
        }
    }
    out = strip_internal(obj, "customer")
    assert out["subcap"]["id"] == "P1C1.1.1"
    assert out["subcap"]["score"] == 3.5
    assert "rationale_internal" not in out["subcap"]
    assert "drive_url" not in out["subcap"]
    assert "analyst_note" not in out["subcap"]


def test_customer_view_traverses_lists() -> None:
    obj = {
        "subcaps": [
            {"id": "P1C1.1.1", "drive_url": "x"},
            {"id": "P1C1.1.2", "drive_url": "y"},
        ]
    }
    out = strip_internal(obj, "customer")
    assert [s["id"] for s in out["subcaps"]] == ["P1C1.1.1", "P1C1.1.2"]
    for s in out["subcaps"]:
        assert "drive_url" not in s


def test_customer_view_handles_primitives_and_none() -> None:
    assert strip_internal(None, "customer") is None
    assert strip_internal(42, "customer") == 42
    assert strip_internal("text", "customer") == "text"
    assert strip_internal([], "customer") == []
