# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import Any

from .common import DecisionAnalysis, DecisionPackage, empty_analysis, lateral_candidate, lateral_series, metrics_from_candidates, vehicle_label


PACKAGE = DecisionPackage("unsafe_lateral_movement", "Unsafe lateral movement")


def analyze(samples: list[dict[str, Any]]) -> DecisionAnalysis:
    if len(samples) < 2:
        return empty_analysis(PACKAGE, "Opinion: Waiting for enough A/B position history.")
    candidates = sorted([item for item in (lateral_candidate(samples, 1, 2), lateral_candidate(samples, 2, 1)) if item], key=lambda item: item["score"], reverse=True)
    best = candidates[0]
    label = vehicle_label(best["vehicle_id"])
    other = vehicle_label(best["other_id"])
    penalty = best["vehicle_id"] if best["score"] >= 0.5 else None
    decision = "Unsafe lateral movement likely" if best["score"] >= 0.7 else ("Unsafe lateral movement possible" if best["score"] >= 0.5 else "Unsafe lateral movement unlikely")
    opinion = f"Opinion: {decision}; {'primary penalty Vehicle ' + label if best['score'] >= 0.7 else ('possible penalty Vehicle ' + label if penalty else 'no clear penalty')}. Confidence {best['score'] * 100:.0f}%. Vehicle {label} moved laterally toward Vehicle {other} at {best['toward']:.2f}m/s."
    return DecisionAnalysis(PACKAGE, opinion, best["score"], penalty, metrics_from_candidates(candidates), lateral_series(samples))
