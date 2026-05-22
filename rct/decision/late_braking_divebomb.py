# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import Any

from .common import DecisionAnalysis, DecisionPackage, analyze_generic_primary, generic_series_for_mode


PACKAGE = DecisionPackage("late_braking_divebomb", "Late braking/divebomb")


def analyze(samples: list[dict[str, Any]]) -> DecisionAnalysis:
    return analyze_generic_primary(PACKAGE, samples, "late", "Late braking/divebomb", "dive score", generic_series_for_mode("late"))
