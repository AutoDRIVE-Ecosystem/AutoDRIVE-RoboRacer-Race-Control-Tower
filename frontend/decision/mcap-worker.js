// SPDX-License-Identifier: BSD-3-Clause

(function () {
  "use strict";

  importScripts("../vendor/mcap/mcap-vendor.js");

  const LIDAR_REPLAY_ANGLE_MIN = -2.35619;
  const LIDAR_REPLAY_ANGLE_INCREMENT = 0.004363323;
  const LIDAR_REPLAY_MAX_RANGES = 270;
  const decoder = new TextDecoder("utf-8");

  self.addEventListener("message", (event) => {
    const message = event.data || {};
    if (message.type !== "load-rct-accident-mcap") {
      return;
    }
    loadRctAccidentMcap(message)
      .then((summary) => {
        self.postMessage({ type: "summary", requestId: message.requestId, summary });
      })
      .catch((error) => {
        self.postMessage({
          type: "error",
          requestId: message.requestId,
          error: error && error.message ? error.message : String(error),
        });
      });
  });

  async function loadRctAccidentMcap({ url, filename, sizeBytes, compactSummary }) {
    postProgress("Downloading MCAP");
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Failed to download MCAP: ${response.status} ${response.statusText}`);
    }
    const blob = await response.blob();
    postProgress("Parsing MCAP");
    const parsed = await parseMcapWithVendor(blob);
    const frames = await framesFromBridgeMessages(parsed.messages, { includeLidarScan: true });
    const durationSeconds = frames.length > 0 ? frames[frames.length - 1].time_offset_seconds : 0;
    const metadata = parsed.metadata || compactSummary && compactSummary.metadata || {};
    return {
      protocol: "autodrive-rct-monitor",
      version: compactSummary && compactSummary.version,
      filename,
      time: compactSummary && compactSummary.time ? compactSummary.time : filename.replace(/^autodrive /, "").replace(/\.mcap$/i, ""),
      size_bytes: Number(sizeBytes || blob.size),
      duration_seconds: durationSeconds,
      complete: compactSummary && Object.prototype.hasOwnProperty.call(compactSummary, "complete") ? compactSummary.complete : true,
      metadata,
      decision_record: compactSummary ? compactSummary.decision_record || null : null,
      frames,
      source: "frontend-mcap-worker",
    };
  }

  async function parseMcapWithVendor(blob) {
    const { BlobReadable, McapIndexedReader } = self.RCTMcapVendor || {};
    if (!BlobReadable || !McapIndexedReader) {
      throw new Error("MCAP vendor bundle is unavailable");
    }
    const reader = await McapIndexedReader.Initialize({
      readable: new BlobReadable(blob),
    });
    const channelsById = reader.channelsById || new Map();
    const state = { messages: [], metadata: null };
    for await (const message of reader.readMessages({
      topics: ["/rct/accident/metadata", "/rct/accident/bridge"],
    })) {
      const channel = channelsById.get(message.channelId);
      if (!channel || channel.messageEncoding !== "json") {
        continue;
      }
      let payload;
      try {
        payload = JSON.parse(decoder.decode(message.data));
      } catch (error) {
        continue;
      }
      if (channel.topic === "/rct/accident/metadata") {
        state.metadata = payload;
      } else if (channel.topic === "/rct/accident/bridge") {
        state.messages.push({ logTimeNs: message.logTime, payload });
      }
    }
    return state;
  }

  async function framesFromBridgeMessages(messages, options = {}) {
    const includeLidarScan = Boolean(options.includeLidarScan);
    const rows = [];
    for (const entry of messages) {
      const payload = entry.payload;
      const bridgePayload = payload && typeof payload === "object" ? payload.payload : null;
      const vehicles = extractMonitorTelemetry(bridgePayload);
      if (Object.keys(vehicles).length === 0) {
        continue;
      }
      if (includeLidarScan) {
        const lidarVehicleIds = new Set([...Object.keys(vehicles).map(Number), 1, 2]);
        const lidarScans = await extractLidarRangeArrays(bridgePayload, lidarVehicleIds);
        for (const [vehicleId, scan] of Object.entries(lidarScans)) {
          vehicles[vehicleId] = vehicles[vehicleId] || {};
          vehicles[vehicleId].lidar_scan = scan;
        }
      }
      rows.push({
        index: payload && typeof payload.index === "number" ? payload.index : rows.length,
        log_time_ns_bigint: entry.logTimeNs,
        wall_time_ns: numeric(payload && payload.wall_time_ns) || Number(entry.logTimeNs),
        vehicles: Object.fromEntries(Object.entries(vehicles).sort(([left], [right]) => Number(left) - Number(right))),
      });
    }
    if (rows.length === 0) {
      return [];
    }
    rows.sort((left, right) => compareBigInt(left.log_time_ns_bigint, right.log_time_ns_bigint));
    const start = rows[0].log_time_ns_bigint;
    const end = rows[rows.length - 1].log_time_ns_bigint;
    const durationSeconds = secondsBetween(start, end);
    return rows.map((row) => {
      const timeOffsetSeconds = secondsBetween(start, row.log_time_ns_bigint);
      const { log_time_ns_bigint, ...frame } = row;
      return {
        ...frame,
        log_time_ns: Number(log_time_ns_bigint),
        time_offset_seconds: Math.max(0, timeOffsetSeconds),
        time_to_accident_seconds: timeOffsetSeconds - durationSeconds,
      };
    });
  }

  function extractMonitorTelemetry(payload) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return {};
    }
    const telemetry = {};
    for (const [key, value] of Object.entries(payload)) {
      const vehicleId = vehicleIdFromKey(key);
      if (vehicleId === null) {
        continue;
      }
      const field = monitorFieldFromKey(key);
      if (field === null) {
        continue;
      }
      const vehicle = telemetry[String(vehicleId)] || {};
      if (field === "ips") {
        const ips = ipsValue(value);
        if (ips) {
          vehicle.ips = ips;
        }
      } else if (field === "collision_count" || field === "lap_count") {
        const count = numericCount(value);
        if (count !== null) {
          vehicle[field] = count;
        }
      } else if (field === "speed") {
        const speed = numeric(value);
        vehicle.speed = speed === null ? value : speed;
      } else if (field === "throttle" || field === "steering" || field === "brake" || field === "yaw_rate") {
        const scalar = numeric(value);
        if (scalar !== null) {
          vehicle[field] = scalar;
        }
      } else if (field === "linear_velocity") {
        const vector = vector3Value(value);
        if (vector) {
          vehicle.linear_velocity = vector;
          const horizontalSpeed = Math.hypot(vector.x, vector.y);
          if (horizontalSpeed > 0.01 && vehicle.heading_yaw === undefined) {
            vehicle.heading_yaw = Math.atan2(vector.y, vector.x);
          }
        }
      } else if (field === "orientation_quaternion") {
        const quaternion = quaternionValue(value);
        if (quaternion) {
          vehicle.orientation_quaternion = quaternion;
          vehicle.heading_yaw = yawFromQuaternion(quaternion);
        }
      } else if (field === "angular_velocity") {
        const vector = vector3Value(value);
        if (vector) {
          vehicle.angular_velocity = vector;
          vehicle.yaw_rate = vector.z;
        }
      } else {
        vehicle[field] = value;
      }
      telemetry[String(vehicleId)] = vehicle;
    }
    return telemetry;
  }

  async function extractLidarRangeArrays(payload, vehicleIds) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return {};
    }
    const scans = {};
    for (const [key, value] of Object.entries(payload)) {
      const vehicleId = vehicleIdFromKey(key);
      if (vehicleId === null || !vehicleIds.has(vehicleId) || !isLidarRangeArrayKey(key)) {
        continue;
      }
      const ranges = await lidarRangeValues(value);
      if (ranges.length > 0) {
        scans[String(vehicleId)] = replayLidarRangesPayload(ranges);
      }
    }
    return scans;
  }

  function replayLidarRangesPayload(ranges) {
    if (ranges.length <= LIDAR_REPLAY_MAX_RANGES) {
      return { ranges, angle_min: LIDAR_REPLAY_ANGLE_MIN, angle_increment: LIDAR_REPLAY_ANGLE_INCREMENT };
    }
    const step = Math.max(1, Math.round(ranges.length / LIDAR_REPLAY_MAX_RANGES));
    return {
      ranges: ranges.filter((_value, index) => index % step === 0),
      angle_min: LIDAR_REPLAY_ANGLE_MIN,
      angle_increment: LIDAR_REPLAY_ANGLE_INCREMENT * step,
      sample_step: step,
    };
  }

  async function lidarRangeValues(value) {
    if (Array.isArray(value)) {
      return value.map(numeric).filter((item) => item !== null);
    }
    if (typeof value === "string") {
      const text = await maybeGunzipBase64Text(value);
      return numericItemsFromText(text).map(Number);
    }
    return [];
  }

  async function maybeGunzipBase64Text(value) {
    const text = value.trim();
    if (!text) {
      return "";
    }
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(text)) {
      return text;
    }
    let bytes;
    try {
      bytes = base64ToBytes(text);
    } catch (error) {
      return text;
    }
    if (bytes.length < 2 || bytes[0] !== 0x1f || bytes[1] !== 0x8b) {
      return text;
    }
    if (typeof DecompressionStream !== "function") {
      return "";
    }
    try {
      const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
      return decoder.decode(await new Response(stream).arrayBuffer());
    } catch (error) {
      return "";
    }
  }

  function base64ToBytes(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }

  function vehicleIdFromKey(key) {
    const match = /(?:^|[^a-zA-Z0-9])V(?<v1>\d+)\b|roboracer_(?<v2>\d+)/i.exec(String(key));
    if (!match) {
      return null;
    }
    return Number(match.groups.v1 || match.groups.v2);
  }

  function monitorFieldFromKey(key) {
    const normalized = String(key).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    if (normalized.includes("best") && normalized.includes("lap") && normalized.includes("time")) {
      return "best_lap_time";
    }
    if (normalized.includes("collision")) {
      return "collision_count";
    }
    if (normalized.includes("last") && normalized.includes("lap") && (normalized.includes("count") || normalized.includes("time"))) {
      return "last_lap_time";
    }
    if (normalized.includes("lap") && normalized.includes("time")) {
      return "lap_time";
    }
    if (normalized.includes("lap") && normalized.includes("count")) {
      return "lap_count";
    }
    if (normalized.includes("throttle")) {
      return "throttle";
    }
    if (normalized.includes("steering")) {
      return "steering";
    }
    if (normalized.includes("brake")) {
      return "brake";
    }
    if (normalized.includes("yaw") && (normalized.includes("rate") || normalized.includes("velocity"))) {
      return "yaw_rate";
    }
    if (normalized.includes("angular") && normalized.includes("velocity")) {
      return "angular_velocity";
    }
    if (normalized.includes("speed")) {
      return "speed";
    }
    if (normalized.includes("linear") && normalized.includes("velocity")) {
      return "linear_velocity";
    }
    if (normalized.includes("orientation") && normalized.includes("quaternion")) {
      return "orientation_quaternion";
    }
    if (normalized.includes("ips") || normalized.includes("position")) {
      return "ips";
    }
    return null;
  }

  function isLidarRangeArrayKey(key) {
    const normalized = String(key).toLowerCase().replace(/[^a-z0-9]+/g, "_");
    return normalized.includes("lidar") && normalized.includes("range") && normalized.includes("array");
  }

  function ipsValue(value) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const x = numeric(value.x !== undefined ? value.x : value.X);
      const y = numeric(value.y !== undefined ? value.y : value.Y);
      const z = numeric(value.z !== undefined ? value.z : value.Z);
      if (x === null || y === null) {
        return null;
      }
      return z === null ? { x, y, raw: value } : { x, y, z, raw: value };
    }
    const numbers = Array.isArray(value) ? value.map(numeric) : numericItemsFromText(String(value)).map(Number);
    if (numbers.length < 2 || numbers[0] === null || numbers[1] === null) {
      return null;
    }
    const ips = { x: numbers[0], y: numbers[1], raw: value };
    if (numbers.length > 2 && numbers[2] !== null) {
      ips.z = numbers[2];
    }
    return ips;
  }

  function vector3Value(value) {
    let numbers;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      numbers = [
        numeric(value.x !== undefined ? value.x : value.X),
        numeric(value.y !== undefined ? value.y : value.Y),
        numeric(value.z !== undefined ? value.z : value.Z),
      ];
    } else {
      numbers = Array.isArray(value) ? value.map(numeric) : numericItemsFromText(String(value)).map(Number);
    }
    if (numbers.length < 2 || numbers[0] === null || numbers[1] === null) {
      return null;
    }
    return { x: numbers[0], y: numbers[1], z: numbers.length > 2 && numbers[2] !== null ? numbers[2] : 0 };
  }

  function quaternionValue(value) {
    let numbers;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      numbers = [
        numeric(value.x !== undefined ? value.x : value.X),
        numeric(value.y !== undefined ? value.y : value.Y),
        numeric(value.z !== undefined ? value.z : value.Z),
        numeric(value.w !== undefined ? value.w : value.W),
      ];
    } else {
      numbers = Array.isArray(value) ? value.map(numeric) : numericItemsFromText(String(value)).map(Number);
    }
    if (numbers.length < 4 || numbers.slice(0, 4).some((item) => item === null)) {
      return null;
    }
    return { x: numbers[0], y: numbers[1], z: numbers[2], w: numbers[3] };
  }

  function yawFromQuaternion(quaternion) {
    const sinyCosp = 2 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y);
    const cosyCosp = 1 - 2 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z);
    return Math.atan2(sinyCosp, cosyCosp);
  }

  function numeric(value) {
    if (value === null || value === undefined || (typeof value === "string" && value.trim() === "")) {
      return null;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function numericCount(value) {
    const number = numeric(value);
    return number === null ? null : Math.trunc(number);
  }

  function numericItemsFromText(value) {
    return String(value).match(/[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?/g) || [];
  }

  function compareBigInt(left, right) {
    return left < right ? -1 : (left > right ? 1 : 0);
  }

  function secondsBetween(startNs, endNs) {
    return Number(endNs - startNs) / 1_000_000_000;
  }

  function postProgress(stage) {
    self.postMessage({ type: "progress", stage });
  }
})();
