# Decision Packs

Decision packs run in the browser. RCT does not render decision HTML/SVG and does not run per-pack Python analysis for the steward UI.

The current flow is:

1. RCT records an accident MCAP.
2. The frontend asks RCT for `GET /monitor/REST/latest/accident-logs/{filename}/summary`.
3. RCT returns MCAP-derived JSON replay/analysis data.
4. `frontend/decision/packs.js` runs the selected JavaScript decision packs.
5. Plotly renders each pack's chart in the browser.
6. The human steward chooses the final decision.
7. RCT saves the decision record JSON.

Download and Foxglove use separate MCAP endpoints. The replay/decision summary is not the source used for ROS2 MCAP export.

## Files

- `frontend/decision/common.js`
  Shared telemetry normalization, geometry helpers, scoring helpers, and Plotly row builders.

- `frontend/decision/packs.js`
  Decision pack registry. Add new frontend decision packs here.

- `frontend/index.html`
  Steward UI, Plotly rendering, final-decision submission, saved-record compatibility checks.

- `schemas/decision-record-0.1.schema.json`
  Saved final-decision JSON schema.

- `rct/server.py`
  MCAP listing, summary generation, ROS2 MCAP download/Foxglove endpoints, and decision-record save endpoint.

The Python package under `rct/decision/` remains for shared record helpers and legacy/server-side analysis code. New steward-facing packs should be JavaScript unless there is a deliberate architecture change.

## Summary Input

Decision packs receive the `summary` object returned by:

```text
GET /monitor/REST/latest/accident-logs/{filename}/summary
```

Important top-level fields:

- `filename`: accident MCAP filename.
- `time`: filename timestamp without the `autodrive ` prefix.
- `size_bytes`: MCAP size.
- `duration_seconds`: replay duration.
- `complete`: whether the MCAP footer was readable.
- `metadata`: accident metadata from `/rct/accident/metadata`.
- `decision_record`: saved final decision, or `null`.
- `frames`: replay/analysis samples.

Each frame contains:

```json
{
  "index": 123,
  "log_time_ns": 1234567890,
  "wall_time_ns": 1234567890,
  "time_offset_seconds": 0.79,
  "time_to_accident_seconds": -4.20,
  "vehicles": {
    "1": {
      "ips": { "x": 0.84, "y": 1.94, "z": 0.05 },
      "speed": 1.2,
      "heading_yaw": 0.1,
      "collision_count": 0,
      "lidar_scan": {
        "ranges": [1.01, 1.02],
        "angle_min": -2.35619,
        "angle_increment": 0.017453292,
        "sample_step": 4
      }
    }
  }
}
```

Decision pack scoring normally uses `common.samplesFromFrames(summary.frames)`, which extracts A/B positions, velocity, speed, heading, and collision counts. LIDAR is currently for replay visualization, not pack scoring.

## LIDAR In Summary

The accident MCAP can contain full LIDAR range arrays. The `/summary` endpoint downsamples LIDAR for browser replay payload size.

The limit is controlled in `rct/server.py`:

```python
LIDAR_REPLAY_MAX_RANGES = 270
```

When an input scan has more ranges than this limit, RCT sends `ranges[::sample_step]` and multiplies `angle_increment` by `sample_step`. This preserves the scan's approximate field of view while keeping the JSON response smaller.

This downsampling affects only `/summary`.

It does not affect:

- `GET /monitor/REST/latest/accident-logs/{filename}`
- `GET /monitor/REST/latest/accident-logs/{filename}/ros2.mcap`
- `GET /monitor/REST/latest/accident-logs/ros2-mcap?path=...`

Those endpoints convert from the original accident MCAP to ROS2 MCAP and keep the source LIDAR data.

## Pack Contract

Each pack has a stable id matching the `sw_analysis` settings keys. The browser calls:

```js
window.RCTDecisionPacks.analyze(id, summary)
```

The returned object must include:

```js
{
  id: "rear_end_collision",
  input_version: "0.1",
  output_version: "0.1",
  opinion: "Opinion: ...",
  confidence: 0.75,
  penalty_vehicle_id: 1,
  metrics: {
    distance: 0.713
  },
  series: [
    { time: -0.5, distance: 0.8, a_speed: 1.4, b_speed: 1.0 }
  ]
}
```

Field rules:

- `id`: stable decision pack id.
- `input_version`: decision input contract version. Current value is `0.1`.
- `output_version`: decision output contract version. Current value is `0.1`.
- `opinion`: short steward-facing hint.
- `confidence`: number from `0.0` to `1.0`.
- `penalty_vehicle_id`: `1`, `2`, or `null`.
- `metrics`: small JSON object rendered below the chart.
- `series`: Plotly row data. Each row must have `time`; all other numeric fields become chart traces.

Vehicle A series keys should start with `a_`; Vehicle B series keys should start with `b_`. The renderer colors A green and B orange. Shared/distance/pack-specific lines get neutral colors in `frontend/index.html`.

## Adding A Pack

1. Add an analysis function in `frontend/decision/packs.js`.
2. Reuse helpers from `frontend/decision/common.js` where possible.
3. Return the pack contract above.
4. Register the pack in the `packs` object in `frontend/decision/packs.js`.
5. Add the id to RCT's default/known software-analysis settings if the pack should appear in UI settings.
6. Keep metrics small. Large arrays belong in `series`, not `metrics`.
7. Run frontend syntax checks and focused tests.

Minimal shape:

```js
function myDecisionPack(samples) {
  const pack = packageInfo("my_decision_pack", "My decision pack");
  if (samples.length < 2) {
    return common.emptyAnalysis(pack, "Opinion: Waiting for enough telemetry history.");
  }
  return {
    package: pack,
    opinion: "Opinion: ...",
    confidence: 0.0,
    penalty_vehicle_id: null,
    metrics: {},
    series: samples.map((sample) => ({ time: sample.time, distance: 0 })),
  };
}
```

Then register:

```js
const packs = {
  ...,
  my_decision_pack: {
    info: packageInfo("my_decision_pack", "My decision pack"),
    analyze: myDecisionPack,
  },
};
```

## Saved Decision Records

The human steward's final decision is saved through:

```text
POST /monitor/REST/latest/accident-logs/{filename}/decision-record
```

The frontend includes:

- `decision_io_version`
- selected `decision_package_ids`
- pack `decision_results`
- final fault/no-decision fields
- memo

RCT writes the sidecar decision JSON next to the MCAP.

Current compatibility versions:

- decision record `schema_version`: `0.1`
- decision pack input/output version: `0.1`

Do not use git revision for compatibility checks. If a future pack changes input or output semantics incompatibly, bump the manual decision I/O version and preserve old-record display intentionally.

## Verification

Useful checks:

```bash
node --check frontend/decision/common.js
node --check frontend/decision/packs.js
perl -0ne 'while (/<script>\n(.*?)\n    <\/script>/sg) { print $1 }' frontend/index.html | node --check -
python3 -m py_compile rct/server.py rct/decision/common.py rct/decision/engine.py
python3 -m unittest tests.test_bridge tests.test_server_bridge.ServerBridgeFlowTests.test_monitor_accident_log_summary_returns_replay_frames
```
