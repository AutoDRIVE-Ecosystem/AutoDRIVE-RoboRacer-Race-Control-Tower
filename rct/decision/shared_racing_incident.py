# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import Any

from .common import DecisionAnalysis, DecisionPackage, clip_score, empty_analysis, generic_candidate, shared_series


PACKAGE = DecisionPackage("shared_racing_incident", "Shared racing incident")


def analyze(samples: list[dict[str, Any]]) -> DecisionAnalysis:
    if len(samples) < 2:
        return empty_analysis(PACKAGE, "Opinion: Waiting for enough A/B position history.")
    a = generic_candidate(samples, 1, 2, mode="shared")
    b = generic_candidate(samples, 2, 1, mode="shared")
    if not a or not b:
        return empty_analysis(PACKAGE, "Opinion: Shared racing incident cannot be evaluated from this log.")
    average = (a["score"] + b["score"]) / 2
    delta = abs(a["score"] - b["score"])
    shared = clip_score(average - delta * 0.65)
    decision = "Shared racing incident likely" if shared >= 0.62 else ("Shared racing incident possible" if shared >= 0.42 else "Shared racing incident unlikely")
    opinion = f"Opinion: {decision}; {'shared/no primary penalty recommended' if shared >= 0.42 else 'one-sided responsibility remains possible'}. Confidence {shared * 100:.0f}%. A contribution {a['score'] * 100:.0f}%, B contribution {b['score'] * 100:.0f}%."
    metrics = {"a_contribution": round(a["score"], 3), "b_contribution": round(b["score"], 3), "shared_score": round(shared, 3)}
    return DecisionAnalysis(PACKAGE, opinion, shared, None, metrics, shared_series(samples))
