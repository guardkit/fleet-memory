"""Test to validate assumption verification records in TASK-MEM-013.

Verifies that all low-confidence assumptions have been updated with
verified values from their respective measurement tasks.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def test_no_low_confidence_assumptions_remain():
    """AC-006: Verify no assumptions with confidence='low' remain."""
    yaml_path = Path("features/storage-substrate/storage-substrate_assumptions.yaml")
    assert yaml_path.exists(), f"Assumptions file not found: {yaml_path}"

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    low_confidence = [a for a in data["assumptions"] if a.get("confidence") == "low"]

    assert len(low_confidence) == 0, (
        f"Found {len(low_confidence)} assumption(s) with confidence='low': "
        f"{[a['id'] for a in low_confidence]}"
    )


def test_assum_004_verified():
    """AC-001: ASSUM-004 has verified_value for pool overflow behavior."""
    yaml_path = Path("features/storage-substrate/storage-substrate_assumptions.yaml")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    assum_004 = next((a for a in data["assumptions"] if a["id"] == "ASSUM-004"), None)

    assert assum_004 is not None, "ASSUM-004 not found"
    assert assum_004["confidence"] == "verified", (
        f"ASSUM-004 confidence should be 'verified', got: {assum_004['confidence']}"
    )
    assert "verified_value" in assum_004, "ASSUM-004 missing verified_value field"
    assert "verified_by_task" in assum_004, "ASSUM-004 missing verified_by_task field"
    assert assum_004["verified_by_task"] == "TASK-MEM-010", (
        f"Expected TASK-MEM-010, got: {assum_004['verified_by_task']}"
    )
    assert "queue" in assum_004["verified_value"].lower(), (
        "verified_value should describe queue behavior"
    )


def test_assum_006_verified():
    """AC-002: ASSUM-006 has verified_value for connect-timeout behavior."""
    yaml_path = Path("features/storage-substrate/storage-substrate_assumptions.yaml")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    assum_006 = next((a for a in data["assumptions"] if a["id"] == "ASSUM-006"), None)

    assert assum_006 is not None, "ASSUM-006 not found"
    assert assum_006["confidence"] == "verified", (
        f"ASSUM-006 confidence should be 'verified', got: {assum_006['confidence']}"
    )
    assert "verified_value" in assum_006, "ASSUM-006 missing verified_value field"
    assert "verified_by_task" in assum_006, "ASSUM-006 missing verified_by_task field"
    assert assum_006["verified_by_task"] == "TASK-MEM-006", (
        f"Expected TASK-MEM-006, got: {assum_006['verified_by_task']}"
    )
    assert "pg_connect_timeout_s" in assum_006["verified_value"], (
        "verified_value should describe pg_connect_timeout_s behavior"
    )


def test_assum_008_verified():
    """AC-003: ASSUM-008 has verified_value for httpx read-timeout behavior."""
    yaml_path = Path("features/storage-substrate/storage-substrate_assumptions.yaml")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    assum_008 = next((a for a in data["assumptions"] if a["id"] == "ASSUM-008"), None)

    assert assum_008 is not None, "ASSUM-008 not found"
    assert assum_008["confidence"] == "verified", (
        f"ASSUM-008 confidence should be 'verified', got: {assum_008['confidence']}"
    )
    assert "verified_value" in assum_008, "ASSUM-008 missing verified_value field"
    assert "verified_by_task" in assum_008, "ASSUM-008 missing verified_by_task field"
    assert assum_008["verified_by_task"] == "TASK-MEM-003", (
        f"Expected TASK-MEM-003, got: {assum_008['verified_by_task']}"
    )
    assert "httpx" in assum_008["verified_value"].lower(), (
        "verified_value should describe httpx timeout behavior"
    )


def test_assum_002_verified():
    """AC-007: ASSUM-002 has verified_value for default search limit."""
    yaml_path = Path("features/storage-substrate/storage-substrate_assumptions.yaml")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    assum_002 = next((a for a in data["assumptions"] if a["id"] == "ASSUM-002"), None)

    assert assum_002 is not None, "ASSUM-002 not found"
    assert assum_002["confidence"] == "verified", (
        f"ASSUM-002 confidence should be 'verified', got: {assum_002['confidence']}"
    )
    assert "verified_value" in assum_002, "ASSUM-002 missing verified_value field"
    assert "verified_by_task" in assum_002, "ASSUM-002 missing verified_by_task field"
    assert assum_002["verified_by_task"] == "TASK-MEM-011", (
        f"Expected TASK-MEM-011, got: {assum_002['verified_by_task']}"
    )
    assert "10" in assum_002["verified_value"], (
        "verified_value should mention the default limit of 10"
    )


def test_all_verified_assumptions_have_required_fields():
    """AC-004: All verified assumptions have required verification fields."""
    yaml_path = Path("features/storage-substrate/storage-substrate_assumptions.yaml")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    verified_assumptions = [a for a in data["assumptions"] if a.get("confidence") == "verified"]

    assert len(verified_assumptions) == 4, (
        f"Expected 4 verified assumptions, found: {len(verified_assumptions)}"
    )

    for assumption in verified_assumptions:
        assert "verified_value" in assumption, f"{assumption['id']} missing verified_value field"
        assert "verified_by_task" in assumption, (
            f"{assumption['id']} missing verified_by_task field"
        )
        assert assumption["confidence"] == "verified", (
            f"{assumption['id']} confidence should be 'verified', got: {assumption['confidence']}"
        )
