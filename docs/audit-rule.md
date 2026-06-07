# Race Records Audit Rule

Race Control Tower keeps a persistent audit trail in `race_records/audit.mcap`.
The audit file is append-only at the logical event level and can contain events
from multiple simulator race sessions.

## Storage

- File: `race_records/audit.mcap`
- MCAP profile: `rct-audit-log`
- Topic: `/rct/audit/log`
- Encoding: JSON
- Timestamp format exposed to monitor clients: `YYYY-MM-DD HH:MM:SS:sss`

Each audit message includes:

- `index`: zero-based index within the current audit file
- `race_number`: one-based race count since `audit.mcap` was created
- `timestamp_ns`: event timestamp in nanoseconds
- `time`: display time
- `kind`: display category, one of `Race Start`, `Race End`, `Vehicle Connected`, `Vehicle Disconnected`, `Bridge Hz`, `Accident`, `Decision`, or `Others`
- `event_type`: audit event category
- `text`: human-readable audit text
- `accident_log_filename`: related accident MCAP filename, when applicable
- `accident_log_time`: related accident record time, when applicable
- `decision_mode`: `manual` or `auto`, for decision events
- `decision_result`: structured decision summary, for decision events
- `memo`: decision note, when supplied

## Events

RCT records these audit events:

- Race start when the first simulator Socket.IO client connects.
- Vehicle connect when an RCT DevKit bridge slot for a vehicle connects.
- Vehicle disconnect when an RCT DevKit bridge slot for a vehicle disconnects.
- Bridge protocol Hz anomalies when Audit Rule thresholds are crossed or a drop is detected.
- Race end when the last simulator client disconnects before a race result.
- Race end when a vehicle reaches the configured total lap count.
- Race end when a vehicle reaches the configured maximum penalty count.
- Accident record creation after an accident MCAP is saved.
- Decision record creation after a manual or automatic decision is saved.

The race number starts at `1` when the first `race_start` event is written to a
new audit file. Each subsequent simulator connection that starts a race
increments the race number. Events written between two race starts keep the most
recent race number.

Accident and decision audit events include the related accident log filename and
time so the frontend can cross-select the matching Accident Records item.

Bridge Hz audit events are intended to capture race-affecting runtime symptoms.
Very high, very low, or suddenly dropping bridge protocol rates can indicate
that the runtime environment could not support the race reliably, which can help
a race director decide whether a rerun is justified. A recorded drop is evidence
that needs follow-up analysis; it does not by itself prove whether the drop
originated in the vehicle or in the Simulator/RCT path.

Audit Rule settings:

- `bridge_hz_maximum`: default `120`. RCT records one audit event when a
  vehicle's Bridge Hz enters `>= bridge_hz_maximum`. It does not keep appending
  while the value remains above the threshold; it records again only after the
  value returns below the maximum and crosses the threshold again.
- `bridge_hz_minimum`: default `20`. RCT records one audit event when a
  connected vehicle's Bridge Hz enters `<= bridge_hz_minimum`. It records again
  only after the value returns above the minimum and crosses the threshold again.
  The first low-boundary crossing after a vehicle connects is ignored because the
  rate can briefly look low while the bridge stream is warming up.
- `bridge_hz_drop_percent`: default `25`. RCT keeps a short per-vehicle Hz
  history and records a drop when the current Bridge Hz is lower than the sample
  about one second earlier by at least this percentage. The allowed range is
  `5` to `50`. Upward changes are not recorded as drop audit events. Repeated
  drop recoveries can produce repeated drop audit events.

Bridge Hz audit is recorded only while a simulator race session is active and no
race result has been reached. Disconnected vehicles do not produce Bridge Hz
minimum-boundary or drop audit events. Bridge Hz drop events are also ignored
while a penalty review is waiting for a decision after an accident.

## Monitor API

REST clients can load the audit log with:

```text
GET /monitor/REST/latest/audit-log
GET /monitor/REST/0.1/audit-log
```

The response body contains:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "audit_log": []
}
```

Monitor WebSocket clients receive an `audit-log` event whenever a new audit
record is created. The event carries only the new `audit_entry`; it does not
carry the full audit array. Clients should load the full list through REST when
they need to render the Audit Log tab.

## Frontend

The Race Records dialog has an Audit Log tab. It renders audit events in time
order with four columns:

- race number
- event time
- kind
- audit text

Rows show only the `HH:MM:SS:sss` time in the Audit Log tab. The full timestamp
remains stored in `audit.mcap`.

The frontend loads the full audit list only when the Race Records dialog is open
and the Audit Log tab is selected. When that tab is visible and a new
`audit_entry` arrives over WebSocket, the frontend appends it unless the entry is
already present, then scrolls to the newest item. When the dialog or Audit Log
tab is not active, audit WebSocket events are ignored and the next tab open
refreshes from REST. Accident and decision rows are clickable when they
reference an accident log. Clicking one switches to the Accident Records tab and
selects the matching accident record.
