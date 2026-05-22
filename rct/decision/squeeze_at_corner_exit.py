# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import Any

from .common import DecisionAnalysis, DecisionPackage, analyze_generic_primary, generic_series_for_mode


PACKAGE = DecisionPackage("squeeze_at_corner_exit", "Squeeze at corner exit")


def analyze(samples: list[dict[str, Any]]) -> DecisionAnalysis:
    return analyze_generic_primary(PACKAGE, samples, "squeeze", "Squeeze at corner exit", "squeeze score", generic_series_for_mode("squeeze"))
