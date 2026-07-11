# AutoDRIVE RCT Monitor Protocol

Version: `0.1`

This document describes the monitoring protocol between the RCT server and the
browser frontend. The monitor protocol is separate from the simulator and
DevKit Socket.IO bridge. Browser monitor clients use plain HTTP REST and plain
WebSocket endpoints served by `aiohttp`.

## Path Layout

```text
/monitor/{transport}/{version}
```

Supported transports:

- `REST`: HTTP snapshots, settings, commands, and file downloads
- `WS`: plain WebSocket event stream and JSON command channel

Supported versions:

- `0.1`: current protocol version
- `latest`: alias for `0.1`

Current base endpoints:

```text
GET ws://<host>:<port>/monitor/WS/0.1
GET ws://<host>:<port>/monitor/WS/latest
GET http://<host>:<port>/monitor/REST/0.1
GET http://<host>:<port>/monitor/REST/latest
```

Unless otherwise noted, REST responses are JSON. Error responses use:

```json
{
  "error": "human-readable message"
}
```

## Shared State

REST responses and WebSocket status events are backed by `RaceControlState`.
Monitor WebSocket fanout goes through `MonitorEventHub`.

State changes should be applied first, then events should be broadcast. Do not
perform network I/O while mutating shared race-control state.

## Common Types

### DevKit State

```json
{
  "name": "devkit:1",
  "vehicle_id": 1,
  "url": "ws://127.0.0.1:4568",
  "host": "127.0.0.1",
  "port": 4568,
  "configured": true,
  "enabled": true,
  "connected": false,
  "queued_messages": 0,
  "bridge_hz": 0.0,
  "bridge_per_minute": 0
}
```

Lightweight status events omit `url`, `host`, `port`, `configured`, and
`enabled` from each DevKit entry.

### Full Status State

Returned by `GET /monitor/REST/{version}` and by the initial WebSocket
`status` event.

```json
{
  "monitor_protocol": {
    "name": "autodrive-rct-monitor",
    "version": "0.1"
  },
  "trace_lidar_vehicle_ids": [],
  "revision": 1,
  "simulator_clients": 0,
  "monitor_clients": 1,
  "devkits": [],
  "accident_recorder": {
    "pre_accident_seconds": 5.0,
    "include_camera": false
  },
  "penalty_rule": {
    "restart_delay_seconds": 2.0,
    "decision_pack_version": "v2",
    "sw_analysis": {
      "rear_end_collision": true,
      "single_vehicle_collision": true,
      "unsafe_lateral_movement": true,
      "late_braking_divebomb": true,
      "squeeze_at_corner_exit": true,
      "unsafe_rejoin": true,
      "shared_racing_incident": true
    },
    "decision_pack_v2": {
      "automatic_decision": false,
      "enable_evaluation": false,
      "graphs": {
        "G01": true,
        "G02": true,
        "G03": true,
        "G04": true,
        "G05": true,
        "G06": true,
        "G07": true,
        "G08": true,
        "G09": true,
        "G10": true,
        "G11": true,
        "G12": true,
        "G13": true,
        "G14": true,
        "G15": true
      },
      "collision_types": {
        "CT1": true,
        "CT2": true,
        "CT3": true,
        "CT4": true,
        "CT5": true,
        "CT6": true,
        "CT7": true
      }
    }
  },
  "racing_rule": {
    "total_lap_count": 10,
    "maximum_penalty_count": 0,
    "celebration_with_confetti": true
  },
  "audit_rule": {
    "bridge_hz_maximum": 120.0,
    "bridge_hz_minimum": 20.0,
    "bridge_hz_drop_percent": 25.0
  },
  "penalty_decision": {
    "active": false,
    "collision_vehicle_ids": [],
    "filtered_vehicle_ids": [],
    "penalty_vehicle_id": null,
    "victim_vehicle_id": null,
    "release_delay_seconds": 2.0
  },
  "vehicle_penalties": {},
  "race_result": {
    "active": false,
    "winner_vehicle_id": null,
    "loser_vehicle_id": null,
    "reason": null
  },
  "review_time_seconds": 0.0,
  "simulator_socketio_path": "/socket.io/"
}
```

`accident_logs`, `audit_log`, `topic_selections`, and `race_time_seconds` are
not included in status snapshots. Load logs and topic selections through their
dedicated REST endpoints. Race time is exposed on telemetry events.

### Accident Log Entry

```json
{
  "filename": "autodrive 2026-05-25 14:25:21:035.mcap",
  "path": "accident_logs_/autodrive 2026-05-25 14:25:21:035.mcap",
  "time": "2026-05-25 14:25:21:035",
  "size_bytes": 1863259,
  "decision_record": null
}
```

If a matching decision JSON exists beside the `.mcap`, `decision_record`
contains that parsed JSON object.

### Audit Log Entry

```json
{
  "index": 1,
  "timestamp_ns": 1779218451540000000,
  "time": "2026-05-25 14:25:21:035",
  "event_type": "race_start",
  "text": "Race started: simulator connected.",
  "race_number": 1,
  "kind": "Others",
  "accident_log_filename": null,
  "accident_log_time": null,
  "decision_mode": null,
  "decision_result": null,
  "memo": null
}
```

## REST API

Use either `/monitor/REST/0.1/...` or `/monitor/REST/latest/...`.

### GET `/monitor/REST/{version}`

Returns protocol metadata and the full current status state.

Input: none.

Output:

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
    "trace_lidar_vehicle_ids": [],
    "revision": 1,
    "simulator_clients": 0,
    "monitor_clients": 0,
    "devkits": [],
    "review_time_seconds": 0.0,
    "simulator_socketio_path": "/socket.io/"
  }
}
```

### GET `/monitor/REST/{version}/topics`

Returns bridge topic options and current frontend selections.

Input: none.

Output:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "topics": [
    {
      "topic": "/autodrive/roboracer_1/front_camera",
      "access": "input",
      "checked": false,
      "mutable": true,
      "recommended_off": true,
      "bridge_filterable": true,
      "bridge_ignored": false
    }
  ],
  "topic_selections": {
    "/autodrive/roboracer_1/front_camera": false
  }
}
```

### POST `/monitor/REST/{version}/topics`

Updates one or more topic selections and publishes a full `status` event.

Input:

```json
{
  "topic_selections": {
    "/autodrive/roboracer_1/front_camera": false,
    "/autodrive/roboracer_1/lidar": true
  }
}
```

`topics` is accepted as an alias for `topic_selections`. Keys must be supported
topic names and values must be booleans.

Output:

```json
{
  "ok": true,
  "topics": [],
  "topic_selections": {
    "/autodrive/roboracer_1/front_camera": false
  }
}
```

### GET `/monitor/REST/{version}/accident-recorder`

Returns accident recorder settings.

Input: none.

Output:

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

### POST `/monitor/REST/{version}/accident-recorder`

Updates accident recorder settings and publishes a full `status` event.

Input:

```json
{
  "pre_accident_seconds": 5.0,
  "include_camera": false
}
```

Validation:

- `pre_accident_seconds`: number, `0` to `60`
- `include_camera`: boolean

Output:

```json
{
  "ok": true,
  "accident_recorder": {
    "pre_accident_seconds": 5.0,
    "include_camera": false
  }
}
```

### GET `/monitor/REST/{version}/penalty-rule`

Returns penalty rule settings.

Input: none.

Output:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "penalty_rule": {
    "restart_delay_seconds": 2.0,
    "decision_pack_version": "v2",
    "sw_analysis": {
      "rear_end_collision": true,
      "single_vehicle_collision": true,
      "unsafe_lateral_movement": true,
      "late_braking_divebomb": true,
      "squeeze_at_corner_exit": true,
      "unsafe_rejoin": true,
      "shared_racing_incident": true
    },
    "decision_pack_v2": {
      "automatic_decision": false,
      "enable_evaluation": false,
      "graphs": {
        "G01": true
      },
      "collision_types": {
        "CT1": true
      }
    }
  }
}
```

### POST `/monitor/REST/{version}/penalty-rule`

Updates penalty rule settings and publishes a full `status` event.

Input:

```json
{
  "restart_delay_seconds": 2.0,
  "decision_pack_version": "v2",
  "sw_analysis": {
    "rear_end_collision": true,
    "single_vehicle_collision": true,
    "unsafe_lateral_movement": true,
    "late_braking_divebomb": true,
    "squeeze_at_corner_exit": true,
    "unsafe_rejoin": true,
    "shared_racing_incident": true
  },
  "decision_pack_v2": {
    "automatic_decision": false,
    "enable_evaluation": false,
    "graphs": {
      "G01": true,
      "G02": true,
      "G03": true,
      "G04": true,
      "G05": true,
      "G06": true,
      "G07": true,
      "G08": true,
      "G09": true,
      "G10": true,
      "G11": true,
      "G12": true,
      "G13": true,
      "G14": true,
      "G15": true
    },
    "collision_types": {
      "CT1": true,
      "CT2": true,
      "CT3": true,
      "CT4": true,
      "CT5": true,
      "CT6": true,
      "CT7": true
    }
  }
}
```

Validation:

- `restart_delay_seconds`: number, `0` to `60`
- `decision_pack_version`: `v1` or `v2`
- `sw_analysis`: object of supported boolean software-analysis flags
- `decision_pack_v2.automatic_decision`: boolean
- `decision_pack_v2.enable_evaluation`: boolean
- `decision_pack_v2.graphs`: object with `G01` through `G15` boolean keys
- `decision_pack_v2.collision_types`: object with `CT1` through `CT7` boolean keys

Output:

```json
{
  "ok": true,
  "penalty_rule": {
    "restart_delay_seconds": 2.0,
    "decision_pack_version": "v2",
    "sw_analysis": {},
    "decision_pack_v2": {
      "automatic_decision": false,
      "enable_evaluation": false,
      "graphs": {},
      "collision_types": {}
    }
  }
}
```

### GET `/monitor/REST/{version}/racing-rule`

Returns racing rule settings.

Input: none.

Output:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "racing_rule": {
    "total_lap_count": 10,
    "maximum_penalty_count": 0,
    "celebration_with_confetti": true
  }
}
```

### POST `/monitor/REST/{version}/racing-rule`

Updates racing rule settings and publishes a full `status` event.

Input:

```json
{
  "total_lap_count": 10,
  "maximum_penalty_count": 0,
  "celebration_with_confetti": true
}
```

Validation:

- `total_lap_count`: number converted to integer, `1` to `1000`
- `maximum_penalty_count`: number converted to integer, `0` to `1000`; `0` disables penalty-count loss
- `celebration_with_confetti`: boolean

Output:

```json
{
  "ok": true,
  "racing_rule": {
    "total_lap_count": 10,
    "maximum_penalty_count": 0,
    "celebration_with_confetti": true
  }
}
```

### GET `/monitor/REST/{version}/audit-rule`

Returns audit rule settings.

Input: none.

Output:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "audit_rule": {
    "bridge_hz_maximum": 120.0,
    "bridge_hz_minimum": 20.0,
    "bridge_hz_drop_percent": 25.0
  }
}
```

### POST `/monitor/REST/{version}/audit-rule`

Updates audit rule settings and publishes a full `status` event.

Input:

```json
{
  "bridge_hz_maximum": 120.0,
  "bridge_hz_minimum": 20.0,
  "bridge_hz_drop_percent": 25.0
}
```

Validation:

- `bridge_hz_maximum`: number, greater than `0`, up to `1000`
- `bridge_hz_minimum`: number, `0` to `1000`, less than `bridge_hz_maximum`
- `bridge_hz_drop_percent`: number, `5` to `50`

Output:

```json
{
  "ok": true,
  "audit_rule": {
    "bridge_hz_maximum": 120.0,
    "bridge_hz_minimum": 20.0,
    "bridge_hz_drop_percent": 25.0
  }
}
```

### GET `/monitor/REST/{version}/accident-logs`

Refreshes accident logs from disk and returns them newest first.

Input: none.

Output:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "accident_logs": [
    {
      "filename": "autodrive 2026-05-25 14:25:21:035.mcap",
      "path": "accident_logs_/autodrive 2026-05-25 14:25:21:035.mcap",
      "time": "2026-05-25 14:25:21:035",
      "size_bytes": 1863259,
      "decision_record": null
    }
  ]
}
```

### GET `/monitor/REST/{version}/accident-logs/{filename}/summary`

Returns replay telemetry extracted from one accident MCAP.

Input:

- Path parameter `filename`: basename from `accident_logs[].filename`
- Query `frames=0|false|no`: return compact metadata without frame list
- Query `lidar=0|false|no`: omit decoded LiDAR scan payloads from full summaries

Output:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "filename": "autodrive 2026-05-25 14:25:21:035.mcap",
  "time": "2026-05-25 14:25:21:035",
  "size_bytes": 1863259,
  "duration_seconds": 4.99534,
  "complete": true,
  "metadata": {
    "type": "metadata",
    "created_at": "2026-05-25T14:25:21.035000",
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
        }
      }
    }
  ]
}
```

`frames` contain monitor telemetry extracted from recorded simulator `Bridge`
payloads. Binary fields and non-monitor bridge fields are not returned.

### GET `/monitor/REST/{version}/accident-logs/{filename}/rct.mcap`

Downloads the original RCT accident MCAP.

Input:

- Path parameter `filename`: basename from `accident_logs[].filename`
- Optional `Range` header is supported

Output:

- `200 OK` or `206 Partial Content`
- `Content-Type: application/octet-stream`
- Body: binary MCAP

### GET `/monitor/REST/{version}/accident-logs/{filename}/ros2.mcap`

Converts the RCT accident MCAP to ROS 2 MCAP and returns it as a binary
download.

Input:

- Path parameter `filename`: basename from `accident_logs[].filename`
- Optional `Range` header is supported

Output:

- `200 OK` or `206 Partial Content`
- `Content-Type: application/octet-stream`
- Body: binary ROS 2 MCAP

### GET `/monitor/REST/{version}/accident-logs/{filename}`

Legacy alias for `/{filename}/ros2.mcap`.

Input and output are the same as `/{filename}/ros2.mcap`.

### GET `/monitor/REST/{version}/accident-logs/ros2-mcap?path={path}`

Converts an accident MCAP selected by path and returns ROS 2 MCAP. The resolved
path must stay inside the accident log output directory.

Input:

- Query `path`: accident MCAP path
- Optional `Range` header is supported

Output:

- `200 OK` or `206 Partial Content`
- `Content-Type: application/octet-stream`
- Body: binary ROS 2 MCAP

### POST `/monitor/REST/{version}/accident-logs/{filename}/decision-record`

Creates or replaces the decision JSON beside an accident MCAP, refreshes
accident logs, publishes `accident-logs`, and records a decision audit entry.

Input:

```json
{
  "decision_io_version": "0.1",
  "decision_mode": "manual",
  "fault_vehicle_id": 2,
  "penalty_vehicle_id": 2,
  "no_decision": false,
  "decision_package_ids": ["CT3"],
  "decision_results": {
    "CT3": {
      "result": "penalty"
    }
  },
  "evaluation": {
    "steward 1": true,
    "steward 2": true,
    "steward 3": true
  },
  "memo": "Penalty recorded by steward."
}
```

Validation:

- `decision_io_version`: optional, must be `0.1`
- `decision_mode`: optional, `manual` or `auto`
- `fault_vehicle_id`: optional, integer `1` or `2`
- `penalty_vehicle_id`: optional unless no decision, integer `1` or `2`
- `no_decision`: boolean-like; when true, both vehicle id fields are stored as `null`
- `decision_package_ids`: list of known rule ids from `sw_analysis` or `decision_pack_v2.collision_types`
- `decision_results`: object
- `evaluation`: optional object with boolean `steward 1`, `steward 2`, and `steward 3`
- `memo`: string

Output:

```json
{
  "ok": true,
  "decision_record": {
    "filename": "autodrive 2026-05-25 14:25:21:035.mcap",
    "created_at": "2026-05-25T14:30:00+00:00",
    "schema_version": "0.1",
    "decision_io_version": "0.1",
    "fault_vehicle_id": 2,
    "penalty": {
      "type": "late_start_delay",
      "vehicle_id": 2,
      "delay_seconds": 2.0,
      "label": "2s late start delay"
    },
    "penalty_vehicle_id": 2,
    "no_decision": false,
    "decision_package_ids": ["CT3"],
    "decision_results": {},
    "evaluation": {
      "steward 1": true,
      "steward 2": true,
      "steward 3": true
    },
    "memo": "Penalty recorded by steward."
  }
}
```

### POST `/monitor/REST/{version}/accident-logs/{filename}/decision-record/evaluation`

Updates only `evaluation` in an existing decision record JSON.

Input:

```json
{
  "evaluation": {
    "steward 1": true,
    "steward 2": false,
    "steward 3": true
  }
}
```

Output:

```json
{
  "ok": true,
  "decision_record": {
    "filename": "autodrive 2026-05-25 14:25:21:035.mcap",
    "evaluation": {
      "steward 1": true,
      "steward 2": false,
      "steward 3": true
    }
  }
}
```

### DELETE `/monitor/REST/{version}/accident-logs`

Deletes `autodrive *.mcap` files and adjacent decision JSON files from the
accident log directory, deletes `audit.mcap`, refreshes state, and publishes
`accident-logs`, `audit-log`, and `status`.

Input:

- Query `keep={filename}`: optional accident MCAP basename to preserve

Output:

```json
{
  "ok": true,
  "deleted": 3,
  "accident_logs": [],
  "audit_log": []
}
```

### GET `/monitor/REST/{version}/audit-log`

Refreshes the audit log from disk and returns it.

Input: none.

Output:

```json
{
  "protocol": "autodrive-rct-monitor",
  "version": "0.1",
  "audit_log": [
    {
      "index": 1,
      "timestamp_ns": 1779218451540000000,
      "time": "2026-05-25 14:25:21:035",
      "event_type": "race_start",
      "text": "Race started: simulator connected.",
      "race_number": 1,
      "kind": "Others",
      "accident_log_filename": null,
      "accident_log_time": null,
      "decision_mode": null,
      "decision_result": null,
      "memo": null
    }
  ]
}
```

### POST `/monitor/REST/{version}/devkits/{vehicle_id}/endpoint`

Updates one DevKit endpoint. If `enabled` is true, RCT configures and connects
that DevKit. If `enabled` is false, RCT stores the endpoint, disables the slot,
and disconnects it. When `enabled` is false and no endpoint is provided, RCT
disconnects the slot.

Input:

```json
{
  "host": "127.0.0.1",
  "port": 4568,
  "enabled": true
}
```

`hostname` is accepted as an alias for `host`.

Validation:

- `vehicle_id`: path integer matching a configured DevKit slot
- `enabled`: boolean, default `true`
- `host` or `hostname`: required when enabling, non-empty string
- `port`: required when enabling, integer `1` to `65535`

Output:

```json
{
  "ok": true,
  "state": {
    "monitor_protocol": {
      "name": "autodrive-rct-monitor",
      "version": "0.1"
    },
    "devkits": []
  }
}
```

### POST `/monitor/REST/{version}/devkits/{vehicle_id}/connect`

Connects the selected DevKit using its current endpoint and publishes a
lightweight `status` event.

Input: empty JSON body or no body.

Output:

```json
{
  "ok": true,
  "state": {
    "monitor_protocol": {
      "name": "autodrive-rct-monitor",
      "version": "0.1"
    },
    "devkits": []
  }
}
```

### POST `/monitor/REST/{version}/devkits/{vehicle_id}/disconnect`

Disconnects the selected DevKit and publishes a lightweight `status` event.

Input: empty JSON body or no body.

Output:

```json
{
  "ok": true,
  "state": {
    "monitor_protocol": {
      "name": "autodrive-rct-monitor",
      "version": "0.1"
    },
    "devkits": []
  }
}
```

### POST `/monitor/REST/{version}/vehicles/{vehicle_id}/trace-lidar`

Enables or disables decoded LiDAR trace data for one vehicle in live telemetry
and publishes a lightweight `status` event.

Input:

```json
{
  "enabled": true
}
```

`trace_lidar` and `value` are accepted as aliases for `enabled`.

Output:

```json
{
  "ok": true,
  "vehicle_id": 1,
  "trace_lidar": true
}
```

## WebSocket API

Connect to:

```text
ws://<host>:<port>/monitor/WS/0.1
ws://<host>:<port>/monitor/WS/latest
```

Server-to-client and client-to-server messages are JSON text frames. Binary
client messages are rejected and broadcast as an `error` event.

All server events share this envelope:

```json
{
  "event": "status",
  "timestamp": "2026-05-25T14:25:21.035000+00:00"
}
```

### Server Event: `status`

Sent immediately after WebSocket connection with full status. Later status
events are lightweight unless a command explicitly publishes full status.

Full status example:

```json
{
  "event": "status",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "monitor_protocol": {
    "name": "autodrive-rct-monitor",
    "version": "0.1"
  },
  "trace_lidar_vehicle_ids": [],
  "revision": 1,
  "simulator_clients": 0,
  "monitor_clients": 1,
  "devkits": [],
  "accident_recorder": {
    "pre_accident_seconds": 5.0,
    "include_camera": false
  },
  "penalty_rule": {
    "restart_delay_seconds": 2.0,
    "decision_pack_version": "v2",
    "sw_analysis": {},
    "decision_pack_v2": {
      "automatic_decision": false,
      "enable_evaluation": false,
      "graphs": {},
      "collision_types": {}
    }
  },
  "racing_rule": {
    "total_lap_count": 10,
    "maximum_penalty_count": 0,
    "celebration_with_confetti": true
  },
  "audit_rule": {
    "bridge_hz_maximum": 120.0,
    "bridge_hz_minimum": 20.0,
    "bridge_hz_drop_percent": 25.0
  },
  "penalty_decision": {
    "active": false,
    "collision_vehicle_ids": [],
    "filtered_vehicle_ids": [],
    "penalty_vehicle_id": null,
    "victim_vehicle_id": null,
    "release_delay_seconds": 2.0
  },
  "vehicle_penalties": {},
  "race_result": {
    "active": false,
    "winner_vehicle_id": null,
    "loser_vehicle_id": null,
    "reason": null
  },
  "review_time_seconds": 0.0,
  "simulator_socketio_path": "/socket.io/"
}
```

Lightweight status example:

```json
{
  "event": "status",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "monitor_protocol": {
    "name": "autodrive-rct-monitor",
    "version": "0.1"
  },
  "trace_lidar_vehicle_ids": [1],
  "revision": 2,
  "simulator_clients": 1,
  "monitor_clients": 1,
  "devkits": [
    {
      "name": "devkit:1",
      "vehicle_id": 1,
      "connected": true,
      "queued_messages": 0,
      "bridge_hz": 59.5,
      "bridge_per_minute": 3570
    }
  ],
  "penalty_decision": {
    "active": false,
    "collision_vehicle_ids": [],
    "filtered_vehicle_ids": [],
    "penalty_vehicle_id": null,
    "victim_vehicle_id": null,
    "release_delay_seconds": 2.0
  },
  "vehicle_penalties": {},
  "race_result": {
    "active": false,
    "winner_vehicle_id": null,
    "loser_vehicle_id": null,
    "reason": null
  },
  "review_time_seconds": 0.0
}
```

### Server Event: `telemetry`

Sent from cached simulator telemetry when RCT extracts monitor fields from
simulator `Bridge` payloads. If `RCT_MONITOR_WS_HZ <= 0`, telemetry is sent
immediately on input. Otherwise it is sent by the periodic monitor stream.

```json
{
  "event": "telemetry",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "rct-cache",
  "socketio_event": "cached",
  "race_time_seconds": 42.0,
  "review_time_seconds": 0.0,
  "vehicles": {
    "1": {
      "throttle": 0.2,
      "steering": -0.1,
      "ips": {
        "x": 1.25,
        "y": -0.5,
        "z": 0.0
      },
      "heading_yaw": 1.57,
      "linear_velocity": {
        "x": 1.0,
        "y": 0.0,
        "z": 0.0
      },
      "lap_count": 2,
      "lap_time": 12.34,
      "last_lap_time": 13.1,
      "best_lap_time": 12.0,
      "collision_count": 0,
      "lidar_scan": []
    }
  }
}
```

Vehicle keys are stringified ids. The concrete fields depend on the simulator
payload and selected topics. `lidar_scan` is included only for vehicles enabled
through the trace-LiDAR REST endpoint.

### Server Event: `frame`

Observation event for Socket.IO bridge traffic. Disabled by default. Enable it
with `RCT_MONITOR_FRAME_EVENTS=true`.

```json
{
  "event": "frame",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "devkit:1",
  "target": "simulator",
  "vehicle_id": 1,
  "socketio_event": "Bridge",
  "args": [
    {
      "encoding": "json",
      "payload": {
        "V1 Throttle": "0.1"
      }
    }
  ]
}
```

Argument encodings:

- `json`: payload is JSON-compatible
- `base64`: payload is base64 text for binary Socket.IO args
- `text`: payload is a string fallback

### Server Event: `accident-logs`

Published after accident log state changes or decision record updates.

```json
{
  "event": "accident-logs",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "rct",
  "accident_logs": [
    {
      "filename": "autodrive 2026-05-25 14:25:21:035.mcap",
      "path": "accident_logs_/autodrive 2026-05-25 14:25:21:035.mcap",
      "time": "2026-05-25 14:25:21:035",
      "size_bytes": 1863259,
      "decision_record": null
    }
  ]
}
```

### Server Event: `audit-log`

Published either as a full log list or as one new entry.

Full list:

```json
{
  "event": "audit-log",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "rct",
  "audit_log": []
}
```

Single entry:

```json
{
  "event": "audit-log",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "rct",
  "audit_entry": {
    "index": 1,
    "timestamp_ns": 1779218451540000000,
    "time": "2026-05-25 14:25:21:035",
    "event_type": "vehicle_connect",
    "text": "Vehicle A connected to RCT (127.0.0.1:4568).",
    "race_number": 1,
    "kind": "Others",
    "accident_log_filename": null,
    "accident_log_time": null,
    "decision_mode": null,
    "decision_result": null,
    "memo": null
  }
}
```

### Server Event: `penalty-decision`

Published when a manual penalty-decision workflow starts, changes, completes, or
is reset for a new simulator session.

Decision pending:

```json
{
  "event": "penalty-decision",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "rct",
  "active": true,
  "collision_vehicle_ids": [1, 2],
  "filtered_vehicle_ids": [1, 2],
  "review_time_seconds": 0.0,
  "release_delay_seconds": 2.0
}
```

Penalty selected:

```json
{
  "event": "penalty-decision",
  "timestamp": "2026-05-25T14:25:22.035000+00:00",
  "source": "monitor",
  "active": true,
  "collision_vehicle_ids": [1, 2],
  "filtered_vehicle_ids": [2],
  "penalty_vehicle_id": 2,
  "victim_vehicle_id": 1,
  "review_time_seconds": 1.0,
  "release_delay_seconds": 2.0
}
```

Penalty released:

```json
{
  "event": "penalty-decision",
  "timestamp": "2026-05-25T14:25:24.035000+00:00",
  "source": "rct",
  "active": false,
  "collision_vehicle_ids": [1, 2],
  "filtered_vehicle_ids": [],
  "penalty_vehicle_id": 2,
  "victim_vehicle_id": 1,
  "review_time_seconds": 1.0,
  "release_delay_seconds": 2.0
}
```

No decision:

```json
{
  "event": "penalty-decision",
  "timestamp": "2026-05-25T14:25:22.035000+00:00",
  "source": "monitor",
  "active": false,
  "collision_vehicle_ids": [1, 2],
  "filtered_vehicle_ids": [],
  "no_decision": true,
  "review_time_seconds": 1.0,
  "release_delay_seconds": 2.0
}
```

Simulator-session reset:

```json
{
  "event": "penalty-decision",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "rct",
  "active": false,
  "collision_vehicle_ids": [],
  "filtered_vehicle_ids": [],
  "reset_reason": "simulator-connected",
  "review_time_seconds": 0.0,
  "release_delay_seconds": 2.0
}
```

While a decision is pending, RCT filters both vehicles' throttle and steering to
`0.0`. After a penalty is selected, only the penalty vehicle remains filtered
for `release_delay_seconds`. `vehicle_penalties` increments when a manual
penalty decision is accepted.

### Server Event: `race-result`

Published when a race finishes or is reset for a new simulator session.

Race finished:

```json
{
  "event": "race-result",
  "timestamp": "2026-05-25T14:30:00.000000+00:00",
  "source": "rct",
  "active": true,
  "winner_vehicle_id": 1,
  "loser_vehicle_id": 2,
  "reason": "total_lap_count",
  "celebration_with_confetti": true
}
```

Race reset:

```json
{
  "event": "race-result",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "rct",
  "active": false,
  "winner_vehicle_id": null,
  "loser_vehicle_id": null,
  "reason": null,
  "reset_reason": "simulator-connected"
}
```

`reason` is currently `total_lap_count` or `maximum_penalty_count`.

### Server Event: `command`

Acknowledges an accepted WebSocket command.

Monitor command ack:

```json
{
  "event": "command",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "monitor",
  "command": "connect-devkit"
}
```

Socket.IO forwarding ack:

```json
{
  "event": "command",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "monitor",
  "target": "simulator",
  "socketio_event": "Bridge"
}
```

### Server Event: `error`

Broadcast when a monitor command is invalid or unsupported.

```json
{
  "event": "error",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "monitor",
  "message": "monitor command must be JSON"
}
```

## WebSocket Client Commands

Client commands are JSON text frames sent to `/monitor/WS/{version}`.

### Command: `configure-devkits`

Configures one or more DevKit endpoints, enables them, connects them, publishes
full `status`, then broadcasts a `command` ack.

Input:

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
      "hostname": "127.0.0.1",
      "port": 4569
    }
  ]
}
```

Output events:

- `status` with full status fields
- `command` ack with `command: "configure-devkits"`

### Command: `connect-devkit`

Connects one DevKit. `host` and `port` are optional; when provided, RCT updates
the endpoint before connecting.

Input:

```json
{
  "command": "connect-devkit",
  "vehicle_id": 1,
  "host": "127.0.0.1",
  "port": 4568
}
```

Output events:

- `status` lightweight
- `command` ack with `command: "connect-devkit"`

### Command: `disconnect-devkit`

Disconnects one DevKit.

Input:

```json
{
  "command": "disconnect-devkit",
  "vehicle_id": 1
}
```

Output events:

- `status` lightweight
- `command` ack with `command: "disconnect-devkit"`

### Command: `manual-penalty-decision`

Applies a manual penalty to one vehicle during an active penalty decision.

Input:

```json
{
  "command": "manual-penalty-decision",
  "penalty_vehicle_id": 2
}
```

`vehicle_id` is accepted as an alias for `penalty_vehicle_id`.

Output events:

- `status`
- `penalty-decision`
- `command` ack with `command: "manual-penalty-decision"`

### Command: `manual-no-decision`

Ends an active penalty decision without penalizing either vehicle.

Input:

```json
{
  "command": "manual-no-decision"
}
```

Output events:

- `status`
- `penalty-decision` with `no_decision: true`
- `command` ack with `command: "manual-no-decision"`

### Socket.IO Forwarding Command

If the WebSocket message has no `command` field, RCT treats it as a forwarding
request to the simulator or DevKit bridge.

Input:

```json
{
  "target": "simulator",
  "event": "Bridge",
  "args": [
    {
      "V1 Reset": "False",
      "V1 Throttle": "0.0",
      "V1 Steering": "0.0"
    }
  ]
}
```

Alternative single payload form:

```json
{
  "target": "devkit:1",
  "event": "message",
  "encoding": "json",
  "payload": {
    "example": true
  }
}
```

Targets:

- `simulator`: emit to all connected simulator Socket.IO clients
- `all-devkits`: rewrite simulator ids to DevKit id `1` and enqueue for all DevKits
- `devkit:<vehicle_id>`: rewrite simulator ids to DevKit id `1` and enqueue for one DevKit, for example `devkit:1`

`event` defaults to `message`. If `args` is present it must be a list. If
`args` is absent, RCT builds one argument from `payload` and `encoding`.
Supported encodings are `json`, `base64`, and `text`.

Output event:

```json
{
  "event": "command",
  "timestamp": "2026-05-25T14:25:21.035000+00:00",
  "source": "monitor",
  "target": "simulator",
  "socketio_event": "Bridge"
}
```

## Non-Monitor Paths

Simulator Socket.IO endpoint:

```text
ws://<host>:<port>/socket.io/?EIO=4&transport=websocket
```

Frontend static files:

```text
http://<host>:<port>/
```

## DevKit Socket.IO Notes

RCT initializes DevKit bridge slots from `RCT_DEVKIT_URLS`, but the active
host/port endpoint can be updated by monitor REST or WebSocket commands. RCT
connects configured and enabled DevKit slots when the simulator connects, and
monitor commands may connect or disconnect them manually.

DevKit URLs may use `ws://`, `wss://`, `http://`, or `https://`. Before calling
`python-socketio`, RCT normalizes:

```text
ws://  -> http://
wss:// -> https://
```

RCT then connects with:

```text
socketio_path=socket.io
transports=["websocket"]
```

Payload rewriting rules:

- Simulator to DevKit: assigned simulator vehicle id becomes id `1`.
- DevKit to Simulator: DevKit id `1` becomes the assigned simulator vehicle id.
- Dict/list/text payloads preserve their original shape whenever possible.
- Binary payloads are forwarded without id rewriting.
