# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from io import BytesIO
import json
from pathlib import Path
import subprocess
from typing import Any

from .common import DecisionAnalysis, DecisionPackage, DecisionRecord, samples_from_frames


PACKAGE_IDS = (
    "rear_end_collision",
    "single_vehicle_collision",
    "unsafe_lateral_movement",
    "late_braking_divebomb",
    "squeeze_at_corner_exit",
    "unsafe_rejoin",
    "shared_racing_incident",
)


def _load_package(package_id: str):
    if package_id not in PACKAGE_IDS:
        return None
    return import_module(f"{__package__}.{package_id}")


def list_decision_packages() -> list[DecisionPackage]:
    packages = []
    for package_id in PACKAGE_IDS:
        module = _load_package(package_id)
        if module is not None:
            packages.append(module.PACKAGE)
    return packages


def get_decision_package(package_id: str) -> DecisionPackage | None:
    module = _load_package(package_id)
    return module.PACKAGE if module is not None else None


def analyze_decision(package_id: str, summary: dict[str, Any]) -> DecisionAnalysis:
    module = _load_package(package_id)
    if module is None:
        raise KeyError(package_id)
    frames = summary.get("frames") if isinstance(summary, dict) else []
    samples = samples_from_frames(frames if isinstance(frames, list) else [])
    return module.analyze(samples)


def render_decision_html(package_id: str, summary: dict[str, Any], image_url: str) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    package = get_decision_package(package_id)
    if package is None:
        raise KeyError(package_id)
    analysis = analyze_decision(package_id, summary)
    env = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
        autoescape=select_autoescape(("html",)),
    )
    template = env.get_template(f"{package.id}.html")
    return template.render(package=package, analysis=analysis, image_url=image_url)


def render_decision_plot_svg(package_id: str, summary: dict[str, Any]) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    analysis = analyze_decision(package_id, summary)
    figure = Figure(figsize=(7.2, 2.8), dpi=120)
    axis = figure.subplots()
    rows = analysis.series
    if rows:
        times = [float(row.get("time", 0.0) or 0.0) for row in rows]
        keys = [key for key in rows[0] if key != "time"]
        for key in keys:
            values = [row.get(key) for row in rows]
            if any(value is not None for value in values):
                axis.plot(times, values, label=key.replace("_", " "))
        axis.axvline(0.0, color="#6c757d", linewidth=0.8, linestyle="--")
        axis.set_xlabel("time to collision (s)")
        axis.grid(True, color="#dee2e6", linewidth=0.7)
        axis.legend(loc="best", fontsize=7)
    else:
        axis.text(0.5, 0.5, "No chart data", ha="center", va="center", transform=axis.transAxes)
        axis.set_axis_off()
    axis.set_title(analysis.package.label, fontsize=10)
    output = BytesIO()
    figure.tight_layout()
    figure.savefig(output, format="svg")
    return output.getvalue()


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
    memo: str = "",
    git_revision: str | None = None,
) -> dict[str, Any]:
    record = DecisionRecord(
        filename=mcap_path.name,
        created_at=datetime.now(timezone.utc).isoformat(),
        fault_vehicle_id=fault_vehicle_id,
        penalty=penalty,
        penalty_vehicle_id=penalty_vehicle_id,
        no_decision=no_decision,
        decision_package_ids=decision_package_ids or [],
        memo=memo,
        rct_git_revision=git_revision,
    )
    payload = {
        "filename": record.filename,
        "created_at": record.created_at,
        "fault_vehicle_id": record.fault_vehicle_id,
        "penalty": record.penalty,
        "penalty_vehicle_id": record.penalty_vehicle_id,
        "no_decision": record.no_decision,
        "decision_package_ids": record.decision_package_ids,
        "memo": record.memo,
        "rct_git_revision": record.rct_git_revision,
    }
    decision_record_path(mcap_path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def current_git_revision(cwd: Path | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd or Path.cwd()),
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision or None
