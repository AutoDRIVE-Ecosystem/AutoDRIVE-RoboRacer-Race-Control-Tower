# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import Any

from .common import DecisionAnalysis, DecisionPackage, empty_analysis, metrics_from_candidates, rear_end_candidate, rear_end_series, vehicle_label


PACKAGE = DecisionPackage("rear_end_collision", "Rear-end collision")


def analyze(samples: list[dict[str, Any]]) -> DecisionAnalysis:
    if len(samples) < 2:
        return empty_analysis(PACKAGE, "Opinion: Waiting for enough A/B position history.")
    candidates = sorted(
        [item for item in (rear_end_candidate(samples, 1, 2), rear_end_candidate(samples, 2, 1)) if item],
        key=lambda item: item["score"],
        reverse=True,
    )
    best = candidates[0]
    label = vehicle_label(best["vehicle_id"])
    other = vehicle_label(best["other_id"])
    decision = "Rear-end unlikely"
    penalty = None
    if best["score"] >= 0.7:
        decision = "Rear-end likely"
        penalty = best["vehicle_id"]
    elif best["score"] >= 0.5:
        decision = "Rear-end possible"
        penalty = best["vehicle_id"]
    opinion = f"Opinion: {decision}; {'primary penalty Vehicle ' + label if penalty and best['score'] >= 0.7 else ('possible penalty Vehicle ' + label if penalty else 'no clear penalty')}. Confidence {best['score'] * 100:.0f}%. Vehicle {label} was behind Vehicle {other}; closing {best['closing']:.2f}m/s."
    return DecisionAnalysis(PACKAGE, opinion, best["score"], penalty, metrics_from_candidates(candidates), rear_end_series(samples))
