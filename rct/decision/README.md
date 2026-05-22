# Decision Packages

Decision packages are now frontend-side JavaScript modules. RCT serves MCAP-derived summary JSON and stores the human steward's final decision record; the browser owns rule analysis and Plotly rendering.

## Frontend Contract

Decision logic lives under `frontend/decision/`:

- `common.js`: shared telemetry normalization and scoring helpers
- `packs.js`: decision pack registry and per-pack `analyze()` functions

Each pack has a stable id matching the `sw_analysis` keys in RCT state. `window.RCTDecisionPacks.analyze(id, summary)` returns:

- `input_version`: currently `0.1`
- `output_version`: currently `0.1`
- `opinion`: short human-readable steward hint
- `confidence`: `0.0` to `1.0`
- `penalty_vehicle_id`: `1`, `2`, or `null`
- `metrics`: small JSON-like dictionary
- `series`: Plotly chart rows with a `time` field and numeric fields

Vehicle A series use green and Vehicle B series use orange. Shared/distance/other pack-specific lines use package-neutral colors in the frontend renderer.

## Server Contract

RCT keeps only MCAP and decision-record REST responsibilities:

- `GET /monitor/REST/{version}/accident-logs`
- `GET /monitor/REST/{version}/accident-logs/{filename}/summary`
- `GET /monitor/REST/{version}/accident-logs/ros2-mcap`
- `POST /monitor/REST/{version}/accident-logs/{filename}/decision-record`
- `DELETE /monitor/REST/{version}/accident-logs`

Server-side HTML/SVG decision analysis endpoints are intentionally not used.

## Record Compatibility

Saved decision records use `schemas/decision-record-0.1.schema.json`. Compatibility is checked with manual versions rather than git revision:

- decision record `schema_version`: `0.1`
- decision module input/output version: `0.1`

If a future frontend changes decision module inputs or outputs incompatibly, bump the decision I/O version and preserve old-record display behavior explicitly.
