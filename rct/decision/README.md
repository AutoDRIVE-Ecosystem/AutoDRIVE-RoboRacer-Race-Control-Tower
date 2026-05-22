# Backend Decision Packages

Decision packages are server-side analysis modules. Each package has:

- a stable id in `PACKAGE_IDS` in `engine.py`
- Python analysis logic in `{id}.py`
- a Jinja2 HTML template fragment in `templates/{id}.html`
- a Matplotlib SVG plot rendered through the decision plot REST API

Frontend code should call the REST APIs and render returned HTML. It should not own penalty analysis logic.

## File Layout

For a decision package with id `example_rule`, add:

- `rct/decision/example_rule.py`
- `rct/decision/templates/example_rule.html`

Then add `example_rule` to `PACKAGE_IDS` in `rct/decision/engine.py`.

The package id must be a valid Python module name because the engine imports it with `import_module`.

## Python Module Contract

Each `{id}.py` module must expose:

```python
from typing import Any

from .common import DecisionAnalysis, DecisionPackage

PACKAGE = DecisionPackage("example_rule", "Example rule")


def analyze(samples: list[dict[str, Any]]) -> DecisionAnalysis:
    ...
```

`samples` are normalized A/B telemetry rows from the accident MCAP summary. Each sample has:

```python
{
    "time": -0.42,
    "vehicles": {
        1: {"x": 1.0, "y": 2.0, "velocity": {"x": 0.1, "y": 0.0}, "calculated_speed": 0.1},
        2: {"x": 1.4, "y": 2.1, "velocity": {"x": 0.0, "y": 0.0}, "calculated_speed": 0.0},
    },
}
```

Return `DecisionAnalysis` with:

- `opinion`: short human-readable steward hint
- `confidence`: `0.0` to `1.0`
- `penalty_vehicle_id`: `1`, `2`, or `None`
- `metrics`: small JSON-like dictionary shown in the template
- `series`: chart rows for Matplotlib; include a `time` field and numeric fields to plot

Use helpers from `common.py` for repeated telemetry math, but keep rule-specific scoring and wording inside the package module.

## HTML Template Contract

`templates/{id}.html` is rendered by Jinja2 with:

- `package`
- `analysis`
- `image_url`

Most packages can include the shared fragment:

```jinja2
{% include "analysis.html" %}
```

For custom presentation, keep CSS inside the template. Do not add frontend JS/CSS files for decision rules.

## REST Flow

The frontend calls:

- `GET /monitor/REST/{version}/accident-logs/{filename}/decision-analyses/{id}/html`
- `GET /monitor/REST/{version}/accident-logs/{filename}/decision-analyses/{id}/plot.svg`
- `POST /monitor/REST/{version}/accident-logs/{filename}/decision-record`

The decision record is saved next to the MCAP as `{same-name}.json` and includes selected package ids, steward memo, final decision, penalty, and RCT git revision when available.

`fault_vehicle_id` and `penalty` are separate:

- single-vehicle collisions are auto-recorded with `fault_vehicle_id` set and `penalty` set to `null`
- steward decisions set `fault_vehicle_id` to the selected fault vehicle and record the applied late-start delay in `penalty`

Example:

```json
{
  "fault_vehicle_id": 2,
  "penalty": {
    "type": "late_start_delay",
    "vehicle_id": 2,
    "delay_seconds": 2.0,
    "label": "2s late start delay"
  }
}
```
