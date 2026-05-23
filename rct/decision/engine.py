# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .common import DecisionRecord

DECISION_RECORD_SCHEMA_VERSION = "0.1"
DECISION_IO_VERSION = "0.1"


def decision_record_path(mcap_path: Path) -> Path:
    return mcap_path.with_suffix(".json")


def load_decision_record(mcap_path: Path) -> dict[str, Any] | None:
    path = decision_record_path(mcap_path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_decision_record(
    mcap_path: Path,
    *,
    fault_vehicle_id: int | None = None,
    penalty: dict[str, Any] | None = None,
    penalty_vehicle_id: int | None = None,
    no_decision: bool = False,
    decision_package_ids: list[str] | None = None,
    decision_results: dict[str, Any] | None = None,
    memo: str = "",
    schema_version: str = DECISION_RECORD_SCHEMA_VERSION,
    decision_io_version: str = DECISION_IO_VERSION,
) -> dict[str, Any]:
    record = DecisionRecord(
        filename=mcap_path.name,
        created_at=datetime.now(timezone.utc).isoformat(),
        schema_version=schema_version,
        decision_io_version=decision_io_version,
        fault_vehicle_id=fault_vehicle_id,
        penalty=penalty,
        penalty_vehicle_id=penalty_vehicle_id,
        no_decision=no_decision,
        decision_package_ids=decision_package_ids or [],
        decision_results=decision_results or {},
        memo=memo,
    )
    payload = {
        "filename": record.filename,
        "created_at": record.created_at,
        "schema_version": record.schema_version,
        "decision_io_version": record.decision_io_version,
        "fault_vehicle_id": record.fault_vehicle_id,
        "penalty": record.penalty,
        "penalty_vehicle_id": record.penalty_vehicle_id,
        "no_decision": record.no_decision,
        "decision_package_ids": record.decision_package_ids,
        "decision_results": record.decision_results,
        "memo": record.memo,
    }
    decision_record_path(mcap_path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload
