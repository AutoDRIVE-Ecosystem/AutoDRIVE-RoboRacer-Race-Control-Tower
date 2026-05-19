# AutoDRIVE RCT Monitor Protocol

Version: `0.1`

AutoDRIVE RCT Monitor Protocol defines communication between the browser frontend and the RCT server. Its primary purpose is to let the web frontend monitor the simulator, Roboracer DevKit instances, and the bridge traffic relayed by RCT.

## Path Layout

The protocol uses this path layout:

```text
/monitor/{transport}/{version}
```

Current endpoints:

```text
/monitor/REST/latest
/monitor/WS/latest
/monitor/REST/0.1
/monitor/WS/0.1
```

`latest` is an alias for the current protocol version, `0.1`.

The transport-before-version layout is intentional. Monitor clients first choose how they communicate with RCT, then choose either an explicit version or the `latest` alias. This keeps the REST and WebSocket surfaces parallel and avoids mixing static frontend paths with API paths.

## Transports

- `REST`: HTTP GET/POST commands and snapshots served by `aiohttp`
- `WS`: plain WebSocket monitor event stream served by `aiohttp`

The monitor WebSocket is separate from the simulator/DevKit Socket.IO bridge. Browser monitoring does not need Socket.IO.

## Shared State Model

RCT keeps monitorable state in one in-process `RaceControlState` object. REST handlers read snapshots from this object, and WebSocket handlers publish events derived from the same object. This keeps GET responses and WS events consistent.

Monitor WebSocket delivery is handled by `MonitorEventHub`. State mutation and network fanout are intentionally separate:

1. Update `RaceControlState`.
2. Build a snapshot or event payload.
3. Broadcast through `MonitorEventHub`.

Network I/O must not happen while mutating shared state. This prevents slow monitor clients from blocking simulator, DevKit, or REST state updates.

### REST

REST endpoints are used to query RCT server state and, later, send control commands.

Implemented in `0.1`:

```http
GET /monitor/REST/0.1
GET /monitor/REST/latest
```

Response shape:

```json
{
  "protocol": "autodrive-rct-monitor",
  "transport": "REST",
  "requested_version": "latest",
  "version": "0.1",
  "latest": "0.1",
  "aliases": {
    "latest": "/monitor/REST/latest",
    "versioned": "/monitor/REST/0.1",
    "events": "/monitor/WS/latest"
  },
  "state": {
    "monitor_protocol": {
      "name": "autodrive-rct-monitor",
      "version": "0.1"
    },
    "simulator_clients": 0,
    "monitor_clients": 1,
    "devkits": []
  }
}
```

REST command surface:

```http
POST /monitor/REST/0.1/devkits/{vehicle_id}/connect
POST /monitor/REST/0.1/devkits/{vehicle_id}/disconnect
POST /monitor/REST/0.1/devkits/{vehicle_id}/endpoint
GET  /monitor/REST/0.1/accident-recorder
POST /monitor/REST/0.1/accident-recorder
GET  /monitor/REST/0.1/penalty-rule
POST /monitor/REST/0.1/penalty-rule
GET  /monitor/REST/0.1/accident-logs
GET  /monitor/REST/0.1/accident-logs/{filename}/summary
DELETE /monitor/REST/0.1/accident-logs
```

These commands start or stop the Socket.IO client session from RCT to the selected DevKit bridge instance. Normal operation starts DevKit sessions automatically when the simulator connects.

`/endpoint` updates the runtime DevKit target and can optionally connect or disconnect the selected slot in the same request.

Example:

```json
{
  "host": "host-a.local",
  "port": 5000,
  "enabled": true
}
```

When `enabled` is `true`, RCT updates the DevKit endpoint and connects it immediately. When `enabled` is `false`, RCT updates the endpoint and disconnects the DevKit immediately.

Accident recorder settings:

```http
GET /monitor/REST/0.1/accident-recorder
```

Response:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "accident_recorder": {
    "pre_accident_seconds": 5.0,
    "include_camera": false
  }
}
```

```http
POST /monitor/REST/0.1/accident-recorder
```

Request:

```json
{
  "pre_accident_seconds": 5.0,
  "include_camera": false
}
```

`pre_accident_seconds` must be a number from `0` to `60`. `include_camera` must be a boolean. The response returns `ok: true` and the applied `accident_recorder` settings. RCT publishes an updated `status` event after the settings change.

Penalty rule settings:

```http
GET /monitor/REST/0.1/penalty-rule
```

Response:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "penalty_rule": {
    "restart_delay_seconds": 2.0
  }
}
```

```http
POST /monitor/REST/0.1/penalty-rule
```

Request:

```json
{
  "restart_delay_seconds": 2.0
}
```

`restart_delay_seconds` must be a number from `0` to `60`. When greater than `0`, a vehicle that receives a manual penalty stays command-filtered for that duration after the decision while the other vehicle is released immediately. When set to `0`, both vehicles are released immediately after the decision. The response returns `ok: true` and the applied `penalty_rule` settings. RCT publishes an updated `status` event after the settings change.

Accident logs:

```http
GET /monitor/REST/0.1/accident-logs
```

Response:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "accident_logs": [
    {
      "filename": "autodrive 2026-05-19 23:20:56:540.mcap",
      "path": "accident_logs/autodrive 2026-05-19 23:20:56:540.mcap",
      "time": "2026-05-19 23:20:56:540",
      "size_bytes": 1863259
    }
  ]
}
```

Logs are returned newest first. RCT refreshes the list from the accident recorder output directory before responding.

```http
GET /monitor/REST/0.1/accident-logs/{filename}/summary
```

`filename` must be a basename from the accident log list. Path segments are rejected. RCT writes new accident MCAP files to a temporary filename and atomically publishes the final `.mcap` filename after the writer finishes. The summary endpoint still reads MCAP files sequentially and reports whether it reached the footer through the `complete` field.

Response:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "filename": "autodrive 2026-05-19 23:20:56:540.mcap",
  "time": "2026-05-19 23:20:56:540",
  "size_bytes": 1863259,
  "duration_seconds": 4.99534,
  "complete": true,
  "metadata": {
    "type": "metadata",
    "created_at": "2026-05-19T23:20:56.540000",
    "trigger_vehicle_id": 1,
    "collision_count": 2,
    "record_count": 735
  },
  "frames": [
    {
      "index": 0,
      "log_time_ns": 1779218451540000000,
      "wall_time_ns": 1779218451540000000,
      "time_offset_seconds": 0.0,
      "time_to_accident_seconds": -4.99534,
      "vehicles": {
        "1": {
          "collision_count": 1,
          "ips": {
            "x": 1.25,
            "y": -0.5
          }
        },
        "2": {
          "collision_count": 1,
          "ips": {
            "x": 1.75,
            "y": -0.25
          }
        }
      }
    }
  ]
}
```

`frames` contain monitor telemetry extracted from each recorded simulator `Bridge` payload. Binary fields and non-monitor bridge fields are not returned in the summary response.

```http
DELETE /monitor/REST/0.1/accident-logs
```

Deletes `autodrive *.mcap` files from the recorder output directory, refreshes shared monitor state, publishes a `status` event, and returns:

```json
{
  "ok": true,
  "deleted": 2,
  "accident_logs": []
}
```

### WebSocket

WebSocket endpoints are used for live monitor events.

```text
ws://<rct-host>:<rct-port>/monitor/WS/0.1
ws://<rct-host>:<rct-port>/monitor/WS/latest
```

Initial event:

```json
{
  "event": "status",
  "timestamp": "2026-04-19T00:00:00+00:00",
  "monitor_protocol": {
    "name": "autodrive-rct-monitor",
    "version": "0.1"
  },
  "simulator_clients": 0,
  "monitor_clients": 1,
  "devkits": [],
  "accident_recorder": {
    "pre_accident_seconds": 5.0,
    "include_camera": false
  },
  "penalty_rule": {
    "restart_delay_seconds": 2.0
  },
  "accident_logs": [],
  "vehicle_penalties": {
    "1": 0,
    "2": 0
  },
  "penalty_decision": {
    "active": false,
    "collision_vehicle_ids": [],
    "filtered_vehicle_ids": [],
    "penalty_vehicle_id": null,
    "victim_vehicle_id": null,
    "release_delay_seconds": 2.0
  }
}
```

Simulator telemetry event:

```json
{
  "event": "telemetry",
  "timestamp": "2026-04-19T00:00:00+00:00",
  "source": "simulator",
  "socketio_event": "Bridge",
  "vehicles": {
    "1": {
      "best_lap_time": "00:12.34",
      "collision_count": 0,
      "ips": {
        "x": 1.25,
        "y": -0.5
      },
      "lap_count": 2,
      "last_lap_count": "00:13.10",
      "speed": 3.2
    }
  }
}
```

Live monitor event categories:

- `status`: RCT server, simulator, monitor client, and DevKit connection state
- `telemetry`: filtered per-Roboracer simulator values for `best_lap_time`, `collision_count`, `ips`, `lap_count`, `last_lap_count`, and `speed`
- `frame`: DevKit-to-simulator command observation event
- `penalty-decision`: accident penalty decision state transition event
- `error`: monitor protocol or command error

Penalty decision event:

```json
{
  "event": "penalty-decision",
  "timestamp": "2026-05-19T19:20:56.540000+00:00",
  "source": "rct",
  "active": true,
  "collision_vehicle_ids": [1, 2],
  "filtered_vehicle_ids": [1, 2],
  "release_delay_seconds": 2.0
}
```

RCT emits `penalty-decision` with `active: true` when both vehicles' collision counts increase in the same simulator telemetry update. While active and before a manual decision, RCT filters both vehicles' throttle and steering commands to `0.0` before merging into the outgoing control cache and before emitting the cache to the simulator.

After a manual decision, RCT emits another active `penalty-decision` event with `penalty_vehicle_id`, `victim_vehicle_id`, and only the penalty vehicle in `filtered_vehicle_ids`:

```json
{
  "event": "penalty-decision",
  "timestamp": "2026-05-19T19:20:57.100000+00:00",
  "source": "monitor",
  "active": true,
  "collision_vehicle_ids": [1, 2],
  "filtered_vehicle_ids": [2],
  "penalty_vehicle_id": 2,
  "victim_vehicle_id": 1,
  "release_delay_seconds": 2.0
}
```

The victim vehicle is released immediately. The penalty vehicle remains filtered for `release_delay_seconds` and is then released. RCT emits a final `penalty-decision` event with `active: false` and an empty `filtered_vehicle_ids` list.

RCT increments `status.vehicle_penalties[penalty_vehicle_id]` when a manual penalty decision is accepted. Penalty counts are monitor-only RCT state; they are not forwarded to the simulator or DevKit bridge protocol.

If the operator chooses no decision, RCT releases both vehicles immediately, does not increment any penalty count, and emits `penalty-decision` with `active: false`, `filtered_vehicle_ids: []`, and `no_decision: true`.

The bundled frontend opens the Accident Logs dialog when it receives an active `penalty-decision` event or a `status.penalty_decision.active` snapshot. It selects the newest accident log and starts replay loading through `GET /monitor/REST/0.1/accident-logs/{filename}/summary`.

Monitor WebSocket command surface:

```json
{
  "command": "configure-devkits",
  "devkits": [
    {
      "vehicle_id": 1,
      "host": "127.0.0.1",
      "port": 4568
    },
    {
      "vehicle_id": 2,
      "host": "127.0.0.1",
      "port": 4569
    }
  ]
}
```

```json
{
  "command": "connect-devkit",
  "vehicle_id": 1,
  "host": "127.0.0.1",
  "port": 4568
}
```

```json
{
  "command": "disconnect-devkit",
  "vehicle_id": 1
}
```

```json
{
  "command": "manual-penalty-decision",
  "penalty_vehicle_id": 2
}
```

`manual-penalty-decision` is valid only while a penalty decision is active. The selected `penalty_vehicle_id` must be one of the vehicles in `status.penalty_decision.collision_vehicle_ids`. The selected vehicle remains command-filtered for `release_delay_seconds`; the other vehicle is treated as the victim and is released immediately.

```json
{
  "command": "manual-no-decision"
}
```

`manual-no-decision` is valid only while a penalty decision is active. It releases all filtered vehicles immediately and leaves `vehicle_penalties` unchanged.

RCT initializes DevKit bridge endpoints from `RCT_DEVKIT_URLS` and connects configured and enabled DevKit bridge instances when the simulator connects, even if no frontend is connected. The frontend reads the current DevKit endpoint state from the monitor snapshot, and the connected/disconnected buttons update the selected DevKit through the REST endpoint above. Manual runtime changes now use `POST /monitor/REST/0.1/devkits/{vehicle_id}/endpoint`.

## Bridge Proxy Cache

RCT keeps two Bridge caches:

- Incoming cache: latest `Bridge` payload received from the simulator.
- Outgoing cache: latest command payload sent to the simulator.

The outgoing cache starts with:

```json
{
  "V1 Reset": "False",
  "V1 Throttle": "0.0",
  "V1 Steering": "0.0",
  "V2 Reset": "False",
  "V2 Throttle": "0.0",
  "V2 Steering": "0.0"
}
```

When a DevKit sends a `Bridge` event, RCT rewrites that DevKit's id `1` fields back to the assigned simulator vehicle id, merges the changed control fields into the outgoing cache, then emits the complete outgoing cache to the simulator. This ensures the simulator always receives V1 and V2 reset/throttle/steering fields together.

RCT also tracks which DevKit caused each outgoing simulator `Bridge` message. The next simulator `Bridge` response is stored in the incoming cache and forwarded to that DevKit after rewriting the assigned simulator vehicle id back to DevKit id `1`. If no pending DevKit response target exists, simulator `Bridge` data is forwarded to all configured and enabled DevKit bridge instances.

Each DevKit state includes a rolling 1-second completed-cycle Bridge rate:

- `bridge_hz`
- `bridge_per_minute`

The rate is recorded when a simulator `Bridge` response is routed back to the DevKit that caused the outgoing simulator command.

## Non-Monitor Paths

Simulator Socket.IO endpoint:

```text
ws://<rct-host>:<rct-port>/socket.io/?EIO=4&transport=websocket
```

Frontend static files:

```text
http://<rct-host>:<rct-port>/
```

RCT uses `aiohttp` for static files and monitor REST/WS routes, and `python-socketio` for simulator and DevKit bridge sessions. The simulator and DevKit bridge payloads are still the AutoDRIVE bridge payloads; Socket.IO is the transport and event envelope.

## Proxy Transport

The simulator connects to RCT as a Socket.IO client. RCT then connects to each configured DevKit bridge as a Socket.IO client using the WebSocket transport.

DevKit URLs are configured through `RCT_DEVKIT_URLS`. RCT accepts both WebSocket-looking URLs and HTTP-looking URLs:

```text
ws://127.0.0.1:4568
http://127.0.0.1:4568
```

`python-socketio` connects with an HTTP(S) base URL and a Socket.IO path. RCT normalizes `ws://` to `http://` and `wss://` to `https://`, then connects with:

```text
socketio_path=socket.io
transports=["websocket"]
```

Payload rewriting still follows the RCT bridge rules:

- Simulator to DevKit: assigned simulator id becomes id `1`.
- DevKit to Simulator: id `1` becomes the assigned simulator id.
- Dict/list payloads keep their Python shape.
- Text payloads keep their text shape.
- Binary payloads are forwarded without id rewriting.
