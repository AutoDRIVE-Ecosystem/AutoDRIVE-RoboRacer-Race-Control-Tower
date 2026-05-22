# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import Any

from .common import DecisionAnalysis, DecisionPackage, analyze_generic_primary, generic_series_for_mode


PACKAGE = DecisionPackage("unsafe_rejoin", "Unsafe rejoin")


def analyze(samples: list[dict[str, Any]]) -> DecisionAnalysis:
    analysis = analyze_generic_primary(PACKAGE, samples, "rejoin", "Unsafe rejoin", "rejoin score", generic_series_for_mode("rejoin"))
    if analysis.series:
        analysis.opinion += " Track-boundary data is not available, so this is rejoin-like motion only."
    return analysis
