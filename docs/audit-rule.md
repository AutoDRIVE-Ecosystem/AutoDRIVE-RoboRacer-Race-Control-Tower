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
- `kind`: display category, one of `Race Start`, `Race End`, `Accident`, `Decision`, or `Others`
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
