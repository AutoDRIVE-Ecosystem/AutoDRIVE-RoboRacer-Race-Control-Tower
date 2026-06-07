# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DecisionRecord:
    filename: str
    created_at: str
    schema_version: str
    decision_io_version: str
    fault_vehicle_id: int | None
    penalty: dict[str, Any] | None
    penalty_vehicle_id: int | None
    no_decision: bool
    decision_package_ids: list[str]
    decision_results: dict[str, Any]
    evaluation: dict[str, bool]
    memo: str
