# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import Any

from .common import DecisionAnalysis, DecisionPackage, collision_count, distance, empty_analysis, vehicle_label


PACKAGE = DecisionPackage("single_vehicle_collision", "Single vehicle collision")


def analyze(samples: list[dict[str, Any]]) -> DecisionAnalysis:
    if len(samples) < 2:
        return empty_analysis(PACKAGE, "Opinion: Waiting for enough A/B telemetry history.")

    collision_changes = collision_count_changes(samples)
    last_distance = distance(samples[-1]["vehicles"][1], samples[-1]["vehicles"][2])
    min_recent_distance = min(
        distance(sample["vehicles"][1], sample["vehicles"][2])
        for sample in samples[-min(len(samples), 20):]
    )

    changed_vehicle_ids = sorted({change["vehicle_id"] for change in collision_changes})
    fault_vehicle_id = changed_vehicle_ids[0] if len(changed_vehicle_ids) == 1 else None
    if fault_vehicle_id is not None and min_recent_distance > 2.0:
        confidence = 0.92
        decision = "Single vehicle collision likely"
        detail = f"only Vehicle {vehicle_label(fault_vehicle_id)} collision count increased while A-B distance stayed {min_recent_distance:.2f}m or more"
    elif fault_vehicle_id is not None:
        confidence = 0.62
        decision = "Single vehicle collision possible"
        detail = f"only Vehicle {vehicle_label(fault_vehicle_id)} collision count increased, but A-B distance became close"
    elif len(changed_vehicle_ids) >= 2:
        confidence = 0.08
        decision = "Single vehicle collision unlikely"
        detail = "both vehicles recorded collision count increases"
    else:
        confidence = 0.0
        decision = "Single vehicle collision not detected"
        detail = "no collision count increase is visible in this analysis window"

    opinion = f"Opinion: {decision}; {'fault Vehicle ' + vehicle_label(fault_vehicle_id) if fault_vehicle_id else 'no single-vehicle fault'}. Confidence {confidence * 100:.0f}%. {detail}."
    metrics = {
        "collision_change_count": len(collision_changes),
        "changed_vehicles": ",".join(vehicle_label(vehicle_id) for vehicle_id in changed_vehicle_ids) or "none",
        "min_recent_ab_distance_m": round(min_recent_distance, 3),
        "final_ab_distance_m": round(last_distance, 3),
    }
    return DecisionAnalysis(PACKAGE, opinion, confidence, fault_vehicle_id, metrics, single_collision_series(samples))


def collision_count_changes(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous: dict[int, int] = {}
    changes: list[dict[str, Any]] = []
    for sample in samples:
        for vehicle_id in (1, 2):
            count = collision_count(sample, vehicle_id)
            if count is None:
                continue
            old_count = previous.get(vehicle_id)
            if old_count is not None and count > old_count:
                changes.append({"time": sample["time"], "vehicle_id": vehicle_id, "from": old_count, "to": count})
            previous[vehicle_id] = count
    return changes


def single_collision_series(samples: list[dict[str, Any]]) -> list[dict[str, float | None]]:
    previous: dict[int, int] = {}
    rows: list[dict[str, float | None]] = []
    for sample in samples:
        row: dict[str, float | None] = {
            "time": sample["time"],
            "ab_distance": distance(sample["vehicles"][1], sample["vehicles"][2]),
        }
        for vehicle_id, label in ((1, "a_collision_delta"), (2, "b_collision_delta")):
            count = collision_count(sample, vehicle_id)
            old_count = previous.get(vehicle_id)
            row[label] = float(max(0, count - old_count)) if count is not None and old_count is not None else 0.0
            if count is not None:
                previous[vehicle_id] = count
        rows.append(row)
    return rows
