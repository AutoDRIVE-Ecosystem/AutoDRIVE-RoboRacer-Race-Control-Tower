# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class DecisionPackage:
    id: str
    label: str


@dataclass
class DecisionAnalysis:
    package: DecisionPackage
    opinion: str
    confidence: float
    penalty_vehicle_id: int | None
    metrics: dict[str, Any]
    series: list[dict[str, float | None]]


@dataclass
class DecisionRecord:
    filename: str
    created_at: str
    fault_vehicle_id: int | None
    penalty: dict[str, Any] | None
    penalty_vehicle_id: int | None
    no_decision: bool
    decision_package_ids: list[str]
    memo: str
    rct_git_revision: str | None


def samples_from_frames(frames: list[Any]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        vehicle_a = point_from_frame(frame, 1)
        vehicle_b = point_from_frame(frame, 2)
        if vehicle_a is None or vehicle_b is None:
            continue
        time_value = numeric(frame.get("time_to_accident_seconds"))
        samples.append({
            "time": time_value if time_value is not None else float(len(samples)),
            "vehicles": {1: vehicle_a, 2: vehicle_b},
        })
    for index, sample in enumerate(samples):
        for vehicle_id in (1, 2):
            point = sample["vehicles"][vehicle_id]
            velocity = velocity_at(samples, index, vehicle_id)
            point["velocity"] = velocity
            point["calculated_speed"] = point["speed"] if point["speed"] is not None else vector_length(velocity)
            if point["heading_yaw"] is None and velocity and vector_length(velocity) > 0.05:
                point["heading_yaw"] = atan2(velocity["y"], velocity["x"])
    return samples


def point_from_frame(frame: dict[str, Any], vehicle_id: int) -> dict[str, Any] | None:
    vehicles = frame.get("vehicles")
    telemetry = vehicles.get(str(vehicle_id)) if isinstance(vehicles, dict) else None
    ips = telemetry.get("ips") if isinstance(telemetry, dict) else None
    if not isinstance(ips, dict):
        return None
    x = numeric(ips.get("x"))
    y = numeric(ips.get("y"))
    if x is None or y is None:
        return None
    linear_velocity = telemetry.get("linear_velocity")
    return {
        "x": x,
        "y": y,
        "speed": numeric(telemetry.get("speed")),
        "collision_count": numeric(telemetry.get("collision_count")),
        "heading_yaw": numeric(telemetry.get("heading_yaw")),
        "linear_velocity": linear_velocity if isinstance(linear_velocity, dict) else None,
    }


def collision_count(sample: dict[str, Any], vehicle_id: int) -> int | None:
    value = sample["vehicles"][vehicle_id].get("collision_count")
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def velocity_at(samples: list[dict[str, Any]], index: int, vehicle_id: int) -> dict[str, float] | None:
    point = samples[index]["vehicles"][vehicle_id]
    linear_velocity = point.get("linear_velocity")
    if isinstance(linear_velocity, dict):
        x = numeric(linear_velocity.get("x"))
        y = numeric(linear_velocity.get("y"))
        if x is not None and y is not None:
            return {"x": x, "y": y}
    for cursor in range(index - 1, -1, -1):
        previous = samples[cursor]["vehicles"][vehicle_id]
        dt = samples[index]["time"] - samples[cursor]["time"]
        if dt > 0.001:
            return {"x": (point["x"] - previous["x"]) / dt, "y": (point["y"] - previous["y"]) / dt}
    return None


def numeric(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def vector_length(vector: dict[str, float] | None) -> float:
    if not vector:
        return 0.0
    return (vector["x"] ** 2 + vector["y"] ** 2) ** 0.5


def atan2(y: float, x: float) -> float:
    import math

    return math.atan2(y, x)


def distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    return ((right["x"] - left["x"]) ** 2 + (right["y"] - left["y"]) ** 2) ** 0.5


def basis(vehicle: dict[str, Any], target: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    import math

    heading = vehicle.get("heading_yaw")
    velocity = vehicle.get("velocity")
    if heading is None and velocity and vector_length(velocity) > 0.05:
        heading = math.atan2(velocity["y"], velocity["x"])
    if heading is None:
        heading = math.atan2(vehicle["y"] - target["y"], vehicle["x"] - target["x"])
    forward = {"x": math.cos(heading), "y": math.sin(heading)}
    return forward, {"x": -forward["y"], "y": forward["x"]}


def basis_from_samples(samples: list[dict[str, Any]], index: int, vehicle_id: int, other_id: int) -> tuple[dict[str, float], dict[str, float]]:
    import math

    vehicle = samples[index]["vehicles"][vehicle_id]
    other = samples[index]["vehicles"][other_id]
    for cursor in range(max(0, index - 40), index):
        previous = samples[cursor]["vehicles"][vehicle_id]
        dx = vehicle["x"] - previous["x"]
        dy = vehicle["y"] - previous["y"]
        length = (dx * dx + dy * dy) ** 0.5
        if 0.05 <= length <= 4.0:
            forward = {"x": dx / length, "y": dy / length}
            return forward, {"x": -forward["y"], "y": forward["x"]}
    return basis(vehicle, other)


def sample_has_position_jump(samples: list[dict[str, Any]], index: int) -> bool:
    if index <= 0:
        return False
    previous = samples[index - 1]
    current = samples[index]
    dt = current["time"] - previous["time"]
    for vehicle_id in (1, 2):
        jump = distance(previous["vehicles"][vehicle_id], current["vehicles"][vehicle_id])
        if jump > 0.75 and (dt <= 0.05 or jump > 2.0):
            return True
    return False


def recent_samples(samples: list[dict[str, Any]], seconds: float) -> list[dict[str, Any]]:
    if not samples:
        return []
    last_time = samples[-1]["time"]
    selected = [sample for sample in samples if sample["time"] >= last_time - seconds]
    return selected if len(selected) >= 2 else samples[-min(len(samples), 12):]


def clip_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def empty_analysis(package: DecisionPackage, opinion: str) -> DecisionAnalysis:
    return DecisionAnalysis(package, opinion, 0.0, None, {}, [])


def rear_end_candidate(samples: list[dict[str, Any]], attacker_id: int, target_id: int) -> dict[str, Any] | None:
    if len(samples) < 2:
        return None
    window = recent_samples(samples, 0.75)
    start_index = len(samples) - len(window)
    candidates = [
        rear_end_candidate_at(samples, index, attacker_id, target_id)
        for index in range(start_index, len(samples))
        if not sample_has_position_jump(samples, index)
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item["score"], -item["distance"], item["time"]))


def rear_end_candidate_at(samples: list[dict[str, Any]], index: int, attacker_id: int, target_id: int) -> dict[str, Any] | None:
    sample = samples[index]
    attacker = sample["vehicles"][attacker_id]
    target = sample["vehicles"][target_id]
    forward, right = basis_from_samples(samples, index, target_id, attacker_id)
    dx = target["x"] - attacker["x"]
    dy = target["y"] - attacker["y"]
    longitudinal = dx * forward["x"] + dy * forward["y"]
    lateral = abs(dx * right["x"] + dy * right["y"])
    final_distance = distance(attacker, target)
    av = attacker.get("velocity")
    tv = target.get("velocity")
    if av and tv:
        closing = (av["x"] - tv["x"]) * forward["x"] + (av["y"] - tv["y"]) * forward["y"]
    else:
        closing = float(attacker.get("calculated_speed") or 0.0) - float(target.get("calculated_speed") or 0.0)
    first_index = max(0, index - 40)
    first = samples[first_index]
    approach = distance(first["vehicles"][attacker_id], first["vehicles"][target_id]) - final_distance
    score = 0.34 * clip_score(longitudinal / 0.6)
    score += 0.2 * clip_score(1.0 - (lateral / 1.2))
    score += 0.25 if closing > 0.2 else (0.12 if closing > 0.05 else 0.0)
    score += 0.14 if approach > 0.25 else (0.07 if approach > 0.05 else 0.0)
    score += 0.07 if final_distance <= 2.0 else 0.0
    return {
        "vehicle_id": attacker_id,
        "other_id": target_id,
        "score": clip_score(score),
        "closing": closing,
        "lateral_gap": lateral,
        "distance": final_distance,
        "approach": approach,
        "longitudinal_gap": longitudinal,
        "time": sample["time"],
    }


def lateral_candidate(samples: list[dict[str, Any]], vehicle_id: int, other_id: int) -> dict[str, Any] | None:
    if len(samples) < 2:
        return None
    window = recent_samples(samples, 0.75)
    start_index = len(samples) - len(window)
    candidates = [
        lateral_candidate_at(samples, index, vehicle_id, other_id)
        for index in range(start_index, len(samples))
        if not sample_has_position_jump(samples, index)
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item["score"], -item["distance"], item["time"]))


def lateral_candidate_at(samples: list[dict[str, Any]], index: int, vehicle_id: int, other_id: int) -> dict[str, Any] | None:
    sample = samples[index]
    vehicle = sample["vehicles"][vehicle_id]
    other = sample["vehicles"][other_id]
    _forward, right = basis_from_samples(samples, index, vehicle_id, other_id)
    lateral = (other["x"] - vehicle["x"]) * right["x"] + (other["y"] - vehicle["y"]) * right["y"]
    lateral_gap = abs(lateral)
    velocity = vehicle.get("velocity") or {"x": 0.0, "y": 0.0}
    toward = 0.0 if lateral == 0 else (velocity["x"] * right["x"] + velocity["y"] * right["y"]) * (1 if lateral > 0 else -1)
    first_index = max(0, index - 40)
    first = samples[first_index]
    first_vehicle = first["vehicles"][vehicle_id]
    first_other = first["vehicles"][other_id]
    _ff, first_right = basis_from_samples(samples, first_index, vehicle_id, other_id)
    first_gap = abs((first_other["x"] - first_vehicle["x"]) * first_right["x"] + (first_other["y"] - first_vehicle["y"]) * first_right["y"])
    gap_closed = first_gap - lateral_gap
    final_distance = distance(vehicle, other)
    score = 0.0
    score += 0.34 if toward > 0.25 else (0.16 if toward > 0.08 else 0.0)
    score += 0.28 if gap_closed > 0.5 else (0.12 if gap_closed > 0.15 else 0.0)
    score += 0.22 if lateral_gap < 1.0 else (0.12 if lateral_gap < 1.6 else 0.0)
    score += 0.16 if final_distance < 2.0 else 0.0
    return {
        "vehicle_id": vehicle_id,
        "other_id": other_id,
        "score": clip_score(score),
        "lateral_gap": lateral_gap,
        "toward": toward,
        "gap_closed": gap_closed,
        "distance": final_distance,
        "time": sample["time"],
    }


def generic_candidate(samples: list[dict[str, Any]], vehicle_id: int, other_id: int, *, mode: str) -> dict[str, Any] | None:
    rear = rear_end_candidate(samples, vehicle_id, other_id)
    lateral = lateral_candidate(samples, vehicle_id, other_id)
    if not rear or not lateral:
        return None
    accel = acceleration(samples, vehicle_id)
    if mode == "late":
        score = clip_score(rear["score"] * 0.75 + (0.18 if rear["closing"] > 0.35 else 0.0) + (0.1 if rear["approach"] > 0.7 else 0.0))
    elif mode == "squeeze":
        score = clip_score(lateral["score"] * 0.75 + (0.16 if accel > 0.1 else 0.0) + (0.1 if lateral["gap_closed"] > 0.45 else 0.0))
    elif mode == "rejoin":
        score = clip_score(lateral["score"] * 0.65 + (0.2 if lateral["gap_closed"] > 0.7 else 0.0) + (0.12 if lateral["distance"] < 2.2 else 0.0))
    else:
        score = clip_score((rear["score"] + lateral["score"]) / 2)
    return {"vehicle_id": vehicle_id, "other_id": other_id, "score": score, "rear": rear, "lateral": lateral, "accel": accel}


def analyze_generic_primary(package: DecisionPackage, samples: list[dict[str, Any]], mode: str, label: str, score_label: str, series_builder: Callable[[list[dict[str, Any]]], list[dict[str, float | None]]]) -> DecisionAnalysis:
    if len(samples) < 3:
        return empty_analysis(package, "Opinion: Waiting for enough A/B position history.")
    candidates = sorted([item for item in (generic_candidate(samples, 1, 2, mode=mode), generic_candidate(samples, 2, 1, mode=mode)) if item], key=lambda item: item["score"], reverse=True)
    best = candidates[0]
    vehicle = vehicle_label(best["vehicle_id"])
    other = vehicle_label(best["other_id"])
    penalty = best["vehicle_id"] if best["score"] >= 0.5 else None
    decision = f"{label} likely" if best["score"] >= 0.7 else (f"{label} possible" if best["score"] >= 0.5 else f"{label} unlikely")
    opinion = f"Opinion: {decision}; {'primary penalty Vehicle ' + vehicle if best['score'] >= 0.7 else ('possible penalty Vehicle ' + vehicle if penalty else 'no clear penalty')}. Confidence {best['score'] * 100:.0f}%. Vehicle {vehicle} pressure toward Vehicle {other}; {score_label} {best['score'] * 100:.0f}%."
    metrics = {f"vehicle_{item['vehicle_id']}_score": round(item["score"], 3) for item in candidates}
    metrics["distance_m"] = round(best["lateral"]["distance"], 3)
    metrics["lateral_gap_m"] = round(best["lateral"]["lateral_gap"], 3)
    return DecisionAnalysis(package, opinion, best["score"], penalty, metrics, series_builder(samples))


def acceleration(samples: list[dict[str, Any]], vehicle_id: int) -> float:
    if len(samples) < 2:
        return 0.0
    last = samples[-1]
    previous = samples[-2]
    dt = last["time"] - previous["time"]
    if dt <= 0.001:
        return 0.0
    return (float(last["vehicles"][vehicle_id].get("calculated_speed") or 0.0) - float(previous["vehicles"][vehicle_id].get("calculated_speed") or 0.0)) / dt


def metrics_from_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {f"vehicle_{item['vehicle_id']}_score": round(item["score"], 3) for item in candidates}
    if candidates:
        best = candidates[0]
        for key in ("closing", "longitudinal_gap", "lateral_gap", "distance", "approach", "toward", "gap_closed"):
            if key in best:
                metrics[key] = round(float(best[key]), 3)
    return metrics


def rear_end_series(samples: list[dict[str, Any]]) -> list[dict[str, float | None]]:
    rows = []
    for index, sample in enumerate(samples):
        partial = samples[: index + 1]
        a = rear_end_candidate(partial, 1, 2)
        b = rear_end_candidate(partial, 2, 1)
        rows.append({"time": sample["time"], "distance": distance(sample["vehicles"][1], sample["vehicles"][2]), "a_closing": a["closing"] if a else None, "b_closing": b["closing"] if b else None})
    return rows


def lateral_series(samples: list[dict[str, Any]]) -> list[dict[str, float | None]]:
    rows = []
    for index, sample in enumerate(samples):
        partial = samples[: index + 1]
        a = lateral_candidate(partial, 1, 2)
        b = lateral_candidate(partial, 2, 1)
        rows.append({"time": sample["time"], "distance": distance(sample["vehicles"][1], sample["vehicles"][2]), "a_toward": a["toward"] if a else None, "b_toward": b["toward"] if b else None, "lateral_gap": a["lateral_gap"] if a else None})
    return rows


def generic_series(samples: list[dict[str, Any]]) -> list[dict[str, float | None]]:
    return generic_series_for_mode("shared")(samples)


def generic_series_for_mode(mode: str) -> Callable[[list[dict[str, Any]]], list[dict[str, float | None]]]:
    def build(samples: list[dict[str, Any]]) -> list[dict[str, float | None]]:
        rows = []
        for index, sample in enumerate(samples):
            partial = samples[: index + 1]
            a = generic_candidate(partial, 1, 2, mode=mode) if len(partial) >= 2 else None
            b = generic_candidate(partial, 2, 1, mode=mode) if len(partial) >= 2 else None
            rows.append({
                "time": sample["time"],
                "distance": distance(sample["vehicles"][1], sample["vehicles"][2]),
                "a_score": a["score"] * 100 if a else None,
                "b_score": b["score"] * 100 if b else None,
            })
        return rows

    return build


def shared_series(samples: list[dict[str, Any]]) -> list[dict[str, float | None]]:
    rows = generic_series(samples)
    for row in rows:
        a = row.get("a_score")
        b = row.get("b_score")
        row["shared_score"] = max(0.0, ((float(a or 0.0) + float(b or 0.0)) / 2) - abs(float(a or 0.0) - float(b or 0.0)) * 0.65)
    return rows


def vehicle_label(vehicle_id: int) -> str:
    return {1: "A", 2: "B"}.get(vehicle_id, str(vehicle_id))
