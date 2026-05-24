// SPDX-License-Identifier: BSD-3-Clause

(function () {
  "use strict";

  const common = window.RCTDecisionCommon;
  const VERSION = common.VERSION;
  const VEHICLES = [1, 2];
  const TTC_CAP_SECONDS = 5.0;
  const LIDAR_X_OFFSET_M = 0.2733;
  const WALL_DYNAMIC_FILTER_RADIUS_M = 0.55;
  const WALL_GRID_RESOLUTION_M = 0.05;
  const WALL_SIDE_WINDOW_LONGITUDINAL_M = 0.8;
  const contextCache = new WeakMap();

  const GRAPH_ORDER = [
    "G01", "G02", "G03", "G04", "G05",
    "G06", "G07", "G08", "G09", "G10",
    "G11", "G12", "G13", "G14", "G15",
  ];
  const GRAPH_LABELS = {
    G01: "Trajectory with reconstructed wall map",
    G02: "Inter-vehicle distance",
    G03: "Speed timeline",
    G04: "Relative geometry, both frames",
    G05: "Throttle / brake timeline",
    G06: "Closing speed",
    G07: "Steering timeline",
    G08: "Lateral gap / lateral separation",
    G09: "Longitudinal gap",
    G10: "Time-to-collision",
    G11: "Track-relative position from reconstructed walls",
    G12: "Yaw rate / heading change",
    G13: "Wall distance / side-wall clearance",
    G14: "Acceleration / jerk",
    G15: "Contribution / uncertainty score",
  };
  const CT_ORDER = ["CT1", "CT2", "CT3", "CT4", "CT5", "CT6", "CT7"];
  const CT_LABELS = {
    CT1: "Single-vehicle wall collision",
    CT2: "Loss-of-control / wall-rebound induced collision",
    CT3: "Rear-end / excessive closing-speed collision",
    CT4: "Late inside entry / divebomb",
    CT5: "Unsafe lateral movement / side-swipe",
    CT6: "Corner-exit squeeze",
    CT7: "Shared racing incident / indeterminate",
  };

  function pluginInfo(id, label) {
    return { id, label, input_version: VERSION, output_version: VERSION };
  }

  function graphInfo(id, label) {
    return { id, label, input_version: VERSION, output_version: VERSION };
  }

  function buildContext(summary) {
    if (summary && typeof summary === "object" && contextCache.has(summary)) {
      return contextCache.get(summary);
    }
    const samples = common.samplesFromFrames(summary && summary.frames);
    const rows = buildDerivedRows(samples);
    const wallMap = reconstructWallMap(samples);
    applyWallMetrics(rows, wallMap);
    const incident = incidentTimes(rows);
    const evidence = evaluateEvidence(rows, incident, wallMap);
    const context = {
      summary,
      samples,
      rows,
      wallMap,
      incident,
      evidence,
      common,
      vehicles: VEHICLES,
    };
    if (summary && typeof summary === "object") {
      contextCache.set(summary, context);
    }
    return context;
  }

  function buildDerivedRows(samples) {
    const rows = samples.map((sample, index) => {
      const a = sample.vehicles[1];
      const b = sample.vehicles[2];
      const relBInA = relativePosition(a, b);
      const relAInB = relativePosition(b, a);
      const row = {
        index,
        time: sample.time,
        a_x: a.x,
        a_y: a.y,
        b_x: b.x,
        b_y: b.y,
        distance: common.distance(a, b),
        a_speed: speedFor(a),
        b_speed: speedFor(b),
        a_throttle: finiteOrNull(a.throttle),
        b_throttle: finiteOrNull(b.throttle),
        a_brake: finiteOrNull(a.brake),
        b_brake: finiteOrNull(b.brake),
        a_steering: finiteOrNull(a.steering),
        b_steering: finiteOrNull(b.steering),
        a_yaw: headingFor(a),
        b_yaw: headingFor(b),
        long_r2_in_r1: relBInA.longitudinal,
        lat_r2_in_r1: relBInA.lateral,
        long_r1_in_r2: relAInB.longitudinal,
        lat_r1_in_r2: relAInB.lateral,
        lateral_gap: Math.abs(relBInA.lateral),
        a_lateral_toward: lateralToward(a, relBInA.lateral),
        b_lateral_toward: lateralToward(b, relAInB.lateral),
        a_collision_delta: 0,
        b_collision_delta: 0,
      };
      row.relative_heading = Number.isFinite(row.a_yaw) && Number.isFinite(row.b_yaw)
        ? wrapToPi(row.b_yaw - row.a_yaw)
        : null;
      return row;
    });
    applyCollisionDeltas(samples, rows);
    for (let index = 0; index < rows.length; index += 1) {
      const row = rows[index];
      row.closing_speed = -derivative(rows, index, "distance");
      row.ttc = row.closing_speed > 0.03 ? Math.min(TTC_CAP_SECONDS, row.distance / row.closing_speed) : null;
      row.a_acceleration = derivative(rows, index, "a_speed");
      row.b_acceleration = derivative(rows, index, "b_speed");
      row.a_yaw_rate = yawRateFor(samples[index].vehicles[1], rows, index, "a_yaw");
      row.b_yaw_rate = yawRateFor(samples[index].vehicles[2], rows, index, "b_yaw");
    }
    for (let index = 0; index < rows.length; index += 1) {
      rows[index].a_jerk = derivative(rows, index, "a_acceleration");
      rows[index].b_jerk = derivative(rows, index, "b_acceleration");
    }
    return rows;
  }

  function speedFor(point) {
    const speed = finiteOrNull(point.calculated_speed);
    return speed === null ? 0 : speed;
  }

  function headingFor(point) {
    const heading = finiteOrNull(point.heading_yaw);
    if (heading !== null) {
      return heading;
    }
    const velocity = point.velocity;
    if (velocity && Math.hypot(velocity.x, velocity.y) > 0.05) {
      return Math.atan2(velocity.y, velocity.x);
    }
    return 0;
  }

  function relativePosition(observer, target) {
    const yaw = headingFor(observer);
    const dx = target.x - observer.x;
    const dy = target.y - observer.y;
    return {
      longitudinal: Math.cos(yaw) * dx + Math.sin(yaw) * dy,
      lateral: -Math.sin(yaw) * dx + Math.cos(yaw) * dy,
    };
  }

  function lateralToward(vehicle, targetLateral) {
    if (!vehicle.velocity || !Number.isFinite(targetLateral) || Math.abs(targetLateral) < 0.001) {
      return 0;
    }
    const yaw = headingFor(vehicle);
    const lateralVelocity = -Math.sin(yaw) * vehicle.velocity.x + Math.cos(yaw) * vehicle.velocity.y;
    return lateralVelocity * Math.sign(targetLateral);
  }

  function applyCollisionDeltas(samples, rows) {
    const previous = {};
    rows.forEach((row, index) => {
      VEHICLES.forEach((vehicleId) => {
        const count = common.collisionCount(samples[index], vehicleId);
        const oldCount = previous[vehicleId];
        const key = vehicleId === 1 ? "a_collision_delta" : "b_collision_delta";
        row[key] = count !== null && oldCount !== undefined ? Math.max(0, count - oldCount) : 0;
        if (count !== null) {
          previous[vehicleId] = count;
        }
      });
    });
  }

  function yawRateFor(point, rows, index, yawKey) {
    const explicit = finiteOrNull(point.yaw_rate);
    if (explicit !== null) {
      return explicit;
    }
    const previous = rows[index - 1];
    const current = rows[index];
    if (!previous || !Number.isFinite(previous[yawKey]) || !Number.isFinite(current[yawKey])) {
      return null;
    }
    const dt = current.time - previous.time;
    if (dt <= 0.001) {
      return null;
    }
    return wrapToPi(current[yawKey] - previous[yawKey]) / dt;
  }

  function derivative(rows, index, key) {
    const current = rows[index];
    if (!current || !Number.isFinite(current[key])) {
      return 0;
    }
    const previous = rows[index - 1];
    if (previous && Number.isFinite(previous[key])) {
      const dt = current.time - previous.time;
      if (dt > 0.001) {
        return (current[key] - previous[key]) / dt;
      }
    }
    const next = rows[index + 1];
    if (next && Number.isFinite(next[key])) {
      const dt = next.time - current.time;
      if (dt > 0.001) {
        return (next[key] - current[key]) / dt;
      }
    }
    return 0;
  }

  function reconstructWallMap(samples) {
    const cells = new Map();
    let scanCount = 0;
    const frameStep = Math.max(1, Math.ceil(samples.length / 160));
    for (let sampleIndex = 0; sampleIndex < samples.length; sampleIndex += frameStep) {
      const sample = samples[sampleIndex];
      for (const vehicleId of VEHICLES) {
        const vehicle = sample.vehicles[vehicleId];
        const other = sample.vehicles[vehicleId === 1 ? 2 : 1];
        const scan = vehicle && vehicle.lidar_scan;
        if (!scan || !Array.isArray(scan.ranges) || scan.ranges.length === 0) {
          continue;
        }
        const angleMin = finiteOrDefault(scan.angle_min, -2.35619);
        const angleIncrement = finiteOrDefault(scan.angle_increment, 0.004363323);
        const yaw = headingFor(vehicle);
        const beamStep = Math.max(1, Math.ceil(scan.ranges.length / 180));
        scanCount += 1;
        for (let beamIndex = 0; beamIndex < scan.ranges.length; beamIndex += beamStep) {
          const range = finiteOrNull(scan.ranges[beamIndex]);
          if (range === null || range < 0.05 || range > 20) {
            continue;
          }
          const angle = angleMin + beamIndex * angleIncrement;
          const xBase = LIDAR_X_OFFSET_M + range * Math.cos(angle);
          const yBase = range * Math.sin(angle);
          const xWorld = vehicle.x + Math.cos(yaw) * xBase - Math.sin(yaw) * yBase;
          const yWorld = vehicle.y + Math.sin(yaw) * xBase + Math.cos(yaw) * yBase;
          if (other && Math.hypot(xWorld - other.x, yWorld - other.y) < WALL_DYNAMIC_FILTER_RADIUS_M) {
            continue;
          }
          const gx = Math.round(xWorld / WALL_GRID_RESOLUTION_M);
          const gy = Math.round(yWorld / WALL_GRID_RESOLUTION_M);
          const key = `${gx},${gy}`;
          const cell = cells.get(key) || { gx, gy, count: 0 };
          cell.count += 1;
          cells.set(key, cell);
        }
      }
    }
    const sorted = Array.from(cells.values()).sort((left, right) => right.count - left.count);
    const dense = sorted.filter((cell) => cell.count >= 2);
    const selected = (dense.length >= 30 ? dense : sorted).slice(0, 2500);
    const points = selected.map((cell) => ({
      x: cell.gx * WALL_GRID_RESOLUTION_M,
      y: cell.gy * WALL_GRID_RESOLUTION_M,
      count: cell.count,
    }));
    return {
      points,
      scan_count: scanCount,
      wall_reconstruction_used: scanCount >= 2 && points.length >= 30,
      fallback_used: !(scanCount >= 2 && points.length >= 30),
    };
  }

  function applyWallMetrics(rows, wallMap) {
    rows.forEach((row) => {
      const a = sideWallDistances(row.a_x, row.a_y, row.a_yaw, wallMap.points);
      const b = sideWallDistances(row.b_x, row.b_y, row.b_yaw, wallMap.points);
      row.a_left_wall = a.left;
      row.a_right_wall = a.right;
      row.a_min_wall_clearance = minFinite(a.left, a.right);
      row.a_track_offset = trackOffset(a.left, a.right);
      row.b_left_wall = b.left;
      row.b_right_wall = b.right;
      row.b_min_wall_clearance = minFinite(b.left, b.right);
      row.b_track_offset = trackOffset(b.left, b.right);
    });
  }

  function sideWallDistances(x, y, yaw, wallPoints) {
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(yaw) || wallPoints.length === 0) {
      return { left: null, right: null };
    }
    let left = null;
    let right = null;
    for (const point of wallPoints) {
      const dx = point.x - x;
      const dy = point.y - y;
      const longitudinal = Math.cos(yaw) * dx + Math.sin(yaw) * dy;
      if (Math.abs(longitudinal) > WALL_SIDE_WINDOW_LONGITUDINAL_M) {
        continue;
      }
      const lateral = -Math.sin(yaw) * dx + Math.cos(yaw) * dy;
      if (lateral > 0) {
        left = left === null ? lateral : Math.min(left, lateral);
      } else if (lateral < 0) {
        right = right === null ? Math.abs(lateral) : Math.min(right, Math.abs(lateral));
      }
    }
    return { left, right };
  }

  function trackOffset(left, right) {
    return Number.isFinite(left) && Number.isFinite(right) ? (right - left) / 2 : null;
  }

  function incidentTimes(rows) {
    if (rows.length === 0) {
      return {
        min_distance_time: null,
        min_distance_index: -1,
        min_distance_m: null,
        collision_time: null,
        collision_index: -1,
        collision_distance_m: null,
        analysis_time: null,
        analysis_index: -1,
        analysis_distance_m: null,
        collision_vehicle_ids: [],
      };
    }
    let minIndex = 0;
    for (let index = 1; index < rows.length; index += 1) {
      if (rows[index].distance < rows[minIndex].distance) {
        minIndex = index;
      }
    }
    const collisionVehicleIds = new Set();
    let collisionTime = null;
    let collisionIndex = -1;
    rows.forEach((row, index) => {
      if (row.a_collision_delta > 0) {
        collisionVehicleIds.add(1);
        if (collisionTime === null || row.time < collisionTime) {
          collisionTime = row.time;
          collisionIndex = index;
        }
      }
      if (row.b_collision_delta > 0) {
        collisionVehicleIds.add(2);
        if (collisionTime === null || row.time < collisionTime) {
          collisionTime = row.time;
          collisionIndex = index;
        }
      }
    });
    const analysisIndex = collisionIndex >= 0 ? collisionIndex : minIndex;
    return {
      min_distance_time: rows[minIndex].time,
      min_distance_index: minIndex,
      min_distance_m: rows[minIndex].distance,
      collision_time: collisionTime,
      collision_index: collisionIndex,
      collision_distance_m: collisionIndex >= 0 ? rows[collisionIndex].distance : null,
      analysis_time: rows[analysisIndex].time,
      analysis_index: analysisIndex,
      analysis_distance_m: rows[analysisIndex].distance,
      collision_vehicle_ids: Array.from(collisionVehicleIds).sort(),
    };
  }

  function evaluateEvidence(rows, incident, wallMap) {
    const preRows = preContactRows(rows, incident);
    const longitudinal = {
      1: longitudinalEvidence(preRows, 1),
      2: longitudinalEvidence(preRows, 2),
    };
    const lateral = {
      1: lateralEvidence(preRows, 1),
      2: lateralEvidence(preRows, 2),
    };
    const wall = {
      1: wallEvidence(preRows, incident, 1, wallMap),
      2: wallEvidence(preRows, incident, 2, wallMap),
    };
    const loss = {
      1: lossOfControlEvidence(preRows, 1, wall[1]),
      2: lossOfControlEvidence(preRows, 2, wall[2]),
    };
    const squeeze = {
      1: squeezeEvidence(preRows, 1, lateral[1], wall[2], wallMap),
      2: squeezeEvidence(preRows, 2, lateral[2], wall[1], wallMap),
    };
    const lowTtc = lowTtcScore(preRows);
    const topPrimaryScore = Math.max(
      wall[1].single_wall_score,
      wall[2].single_wall_score,
      loss[1].score,
      loss[2].score,
      longitudinal[1].score,
      longitudinal[2].score,
      lateral[1].score,
      lateral[2].score,
      squeeze[1].score,
      squeeze[2].score,
    );
    return {
      pre_rows: preRows,
      longitudinal,
      lateral,
      wall,
      loss,
      squeeze,
      low_ttc_score: lowTtc,
      side_by_side_score: sideBySideScore(preRows),
      top_primary_score: topPrimaryScore,
    };
  }

  function preContactRows(rows, incident) {
    const analysisIndex = Number.isInteger(incident.analysis_index) ? incident.analysis_index : incident.min_distance_index;
    if (!rows.length || analysisIndex < 0) {
      return [];
    }
    const analysisTime = Number.isFinite(incident.analysis_time) ? incident.analysis_time : incident.min_distance_time;
    const selected = rows.filter((row, index) => index <= analysisIndex && row.time >= analysisTime - 1.0);
    if (selected.length >= 3) {
      return selected;
    }
    return rows.slice(Math.max(0, analysisIndex - 20), analysisIndex + 1);
  }

  function longitudinalEvidence(rows, vehicleId) {
    const attackerIsA = vehicleId === 1;
    const longKey = attackerIsA ? "long_r1_in_r2" : "long_r2_in_r1";
    const attackerSpeedKey = attackerIsA ? "a_speed" : "b_speed";
    const targetSpeedKey = attackerIsA ? "b_speed" : "a_speed";
    const evidenceRows = rowsBeforeCollisionImpulse(rows);
    const terminalRows = trailingRows(evidenceRows, 0.55);
    const longValues = finiteValues(evidenceRows, longKey);
    const terminalLongValues = finiteValues(terminalRows, longKey);
    const behindFraction = Math.max(
      fraction(evidenceRows, (row) => Number.isFinite(row[longKey]) && row[longKey] < -0.05),
      fraction(terminalRows, (row) => Number.isFinite(row[longKey]) && row[longKey] < -0.05),
    );
    const speedAdvantage = Math.max(
      average(evidenceRows.map((row) => finiteOrNull(row[attackerSpeedKey] - row[targetSpeedKey])).filter(Number.isFinite)),
      average(terminalRows.map((row) => finiteOrNull(row[attackerSpeedKey] - row[targetSpeedKey])).filter(Number.isFinite)),
    );
    const speedScore = clip(speedAdvantage / 0.6);
    const firstLong = longValues.length ? longValues[0] : null;
    const lastLong = longValues.length ? longValues[longValues.length - 1] : null;
    const terminalFirstLong = terminalLongValues.length ? terminalLongValues[0] : null;
    const terminalLastLong = terminalLongValues.length ? terminalLongValues[terminalLongValues.length - 1] : null;
    const gapClosed = Math.max(
      firstLong !== null && lastLong !== null && firstLong < 0 ? Math.max(0, lastLong - firstLong) : 0,
      terminalFirstLong !== null && terminalLastLong !== null && terminalFirstLong < 0 ? Math.max(0, terminalLastLong - terminalFirstLong) : 0,
    );
    const gapScore = clip(gapClosed / 1.0);
    const closingScore = Math.max(
      clip(average(evidenceRows.map((row) => Math.max(0, finiteOrDefault(row.closing_speed, 0)))) / 0.8),
      clip(average(terminalRows.map((row) => Math.max(0, finiteOrDefault(row.closing_speed, 0)))) / 0.8),
    );
    const ttcScore = Math.max(lowTtcScore(evidenceRows), lowTtcScore(terminalRows));
    const fasterClosingGate = clip((speedAdvantage + 0.05) / 0.45);
    const score = clip(
      behindFraction * 0.18
      + speedScore * 0.28
      + closingScore * 0.22 * fasterClosingGate
      + gapScore * 0.22 * fasterClosingGate
      + ttcScore * 0.10 * fasterClosingGate,
    );
    return {
      vehicle_id: vehicleId,
      score,
      behind_fraction: behindFraction,
      speed_advantage_mps: speedAdvantage,
      gap_closed_m: gapClosed,
      closing_score: closingScore,
      ttc_score: ttcScore,
      faster_closing_gate: fasterClosingGate,
    };
  }

  function rowsBeforeCollisionImpulse(rows) {
    const filtered = rows.filter((row) => row.a_collision_delta <= 0 && row.b_collision_delta <= 0);
    return filtered.length >= 3 ? filtered : rows;
  }

  function trailingRows(rows, seconds) {
    if (rows.length < 3) {
      return rows;
    }
    const endTime = rows[rows.length - 1].time;
    const selected = rows.filter((row) => row.time >= endTime - seconds);
    if (selected.length >= 3) {
      return selected;
    }
    return rows.slice(-Math.min(rows.length, 12));
  }

  function lateralEvidence(rows, vehicleId) {
    const isA = vehicleId === 1;
    const towardKey = isA ? "a_lateral_toward" : "b_lateral_toward";
    const steeringKey = isA ? "a_steering" : "b_steering";
    const otherLatKey = isA ? "lat_r2_in_r1" : "lat_r1_in_r2";
    const gapValues = finiteValues(rows, "lateral_gap");
    const firstGap = gapValues.length ? gapValues[0] : null;
    const lastGap = gapValues.length ? gapValues[gapValues.length - 1] : null;
    const gapClosed = firstGap !== null && lastGap !== null ? Math.max(0, firstGap - lastGap) : 0;
    const towardScore = clip(average(rows.map((row) => Math.max(0, finiteOrDefault(row[towardKey], 0)))) / 0.35);
    const steeringScore = clip(average(rows.map((row) => {
      const steering = finiteOrDefault(row[steeringKey], 0);
      const lateral = finiteOrDefault(row[otherLatKey], 0);
      return Math.max(0, steering * Math.sign(lateral));
    })) / 0.45);
    const sideBySide = sideBySideScore(rows);
    const gapCloseScore = clip(gapClosed / 0.8);
    const finalGapScore = clip(1 - finiteOrDefault(lastGap, 3) / 1.2);
    const score = clip(sideBySide * 0.25 + gapCloseScore * 0.25 + towardScore * 0.25 + steeringScore * 0.15 + finalGapScore * 0.10);
    return {
      vehicle_id: vehicleId,
      score,
      side_by_side_score: sideBySide,
      gap_closed_m: gapClosed,
      toward_score: towardScore,
      steering_toward_score: steeringScore,
      final_lateral_gap_m: lastGap,
    };
  }

  function wallEvidence(rows, incident, vehicleId, wallMap) {
    const isA = vehicleId === 1;
    const clearanceKey = isA ? "a_min_wall_clearance" : "b_min_wall_clearance";
    const collisionKey = isA ? "a_collision_delta" : "b_collision_delta";
    const clearances = finiteValues(rows, clearanceKey);
    const minClearance = clearances.length ? Math.min(...clearances) : null;
    const firstClearance = clearances.length ? clearances[0] : null;
    const clearanceDrop = firstClearance !== null && minClearance !== null ? Math.max(0, firstClearance - minClearance) : 0;
    const clearanceScore = minClearance === null ? 0 : clip((0.65 - minClearance) / 0.65);
    const collapseScore = clip(clearanceDrop / 0.5);
    const collisionScore = rows.some((row) => row[collisionKey] > 0) || incident.collision_vehicle_ids.includes(vehicleId) ? 1 : 0;
    const eventDistance = Number.isFinite(incident.analysis_distance_m) ? incident.analysis_distance_m : incident.min_distance_m;
    const opponentFarScore = eventDistance !== null ? clip((eventDistance - 1.2) / 1.3) : 0;
    const isolatedCollisionScore = incident.collision_vehicle_ids.length === 1 && incident.collision_vehicle_ids.includes(vehicleId) ? 1 : 0;
    const fallbackIsolatedScore = wallMap.wall_reconstruction_used
      ? 0
      : (collisionScore ? clip(opponentFarScore * 0.45 + isolatedCollisionScore * 0.25) : 0);
    const singleWallScore = wallMap.wall_reconstruction_used
      ? clip(clearanceScore * 0.38 + collapseScore * 0.27 + collisionScore * 0.20 + opponentFarScore * 0.15)
      : fallbackIsolatedScore;
    return {
      vehicle_id: vehicleId,
      single_wall_score: singleWallScore,
      min_wall_clearance_m: minClearance,
      clearance_drop_m: clearanceDrop,
      clearance_score: clearanceScore,
      collapse_score: collapseScore,
      collision_score: collisionScore,
      opponent_far_score: opponentFarScore,
      isolated_collision_score: isolatedCollisionScore,
    };
  }

  function lossOfControlEvidence(rows, vehicleId, wallEvidenceResult) {
    const isA = vehicleId === 1;
    const yawKey = isA ? "a_yaw_rate" : "b_yaw_rate";
    const steeringKey = isA ? "a_steering" : "b_steering";
    const jerkKey = isA ? "a_jerk" : "b_jerk";
    const yawSpike = maxAbs(rows, yawKey);
    const jerkSpike = maxAbs(rows, jerkKey);
    const steeringValues = finiteValues(rows, steeringKey);
    const steeringRange = steeringValues.length ? Math.max(...steeringValues) - Math.min(...steeringValues) : 0;
    const yawScore = clip(yawSpike / 2.0);
    const steeringOscillationScore = clip(steeringRange / 0.8);
    const jerkScore = clip(jerkSpike / 5.0);
    const wallScore = wallEvidenceResult.clearance_score * 0.65 + wallEvidenceResult.collapse_score * 0.35;
    const score = clip(yawScore * 0.45 + steeringOscillationScore * 0.20 + jerkScore * 0.20 + wallScore * 0.15);
    return {
      vehicle_id: vehicleId,
      score,
      yaw_spike_radps: yawSpike,
      steering_range: steeringRange,
      jerk_spike_mps3: jerkSpike,
      wall_instability_score: wallScore,
    };
  }

  function squeezeEvidence(rows, vehicleId, lateralEvidenceResult, opponentWallEvidence, wallMap) {
    const sideBySide = sideBySideScore(rows);
    const rawOpponentWallPressure = opponentWallEvidence.min_wall_clearance_m === null
      ? 0
      : clip((0.35 - opponentWallEvidence.min_wall_clearance_m) / 0.35);
    const opponentWallPressure = rawOpponentWallPressure * clip(lateralEvidenceResult.score / 0.45);
    const wallAvailable = wallMap.wall_reconstruction_used ? 1 : 0;
    const score = clip(lateralEvidenceResult.score * 0.45 + sideBySide * 0.20 + opponentWallPressure * 0.30 + wallAvailable * 0.05);
    return {
      vehicle_id: vehicleId,
      score,
      side_by_side_score: sideBySide,
      opponent_wall_pressure: opponentWallPressure,
    };
  }

  function graphG01(context) {
    const info = {
      ...graphInfo("G01", GRAPH_LABELS.G01),
      legacy_equivalents: [
        "Vehicle Trajectories Before Collision",
        "11A_reconstructed_wall_map_trajectory.png",
      ],
      wall_reconstruction_used: context.wallMap.wall_reconstruction_used,
      fallback_used: context.wallMap.fallback_used,
    };
    const rows = context.rows;
    const traces = [];
    if (context.wallMap.wall_reconstruction_used) {
      traces.push({
        x: context.wallMap.points.map((point) => point.x),
        y: context.wallMap.points.map((point) => point.y),
        name: "Reconstructed wall map",
        type: "scatter",
        mode: "markers",
        marker: { color: "rgba(90, 90, 90, 0.35)", size: 3 },
        hoverinfo: "skip",
      });
    }
    traces.push(trajectoryTrace(rows, "a_x", "a_y", "Vehicle A", "#2e7d32"));
    traces.push(trajectoryTrace(rows, "b_x", "b_y", "Vehicle B", "#ef6c00"));
    const closest = rows[context.incident.min_distance_index];
    if (closest) {
      traces.push(markerTrace([closest.a_x, closest.b_x], [closest.a_y, closest.b_y], "Closest approach", "#1565c0"));
    }
    const collisionRow = firstCollisionRow(rows);
    if (collisionRow) {
      traces.push(markerTrace([collisionRow.a_x, collisionRow.b_x], [collisionRow.a_y, collisionRow.b_y], "Collision count event", "#dc2626", "x"));
    }
    return {
      graph: info,
      opinion: context.wallMap.wall_reconstruction_used
        ? "G01 overlays both trajectories on a reconstructed static wall-map proxy from LiDAR."
        : "G01 falls back to trajectory-only because LiDAR wall reconstruction was unavailable or low quality.",
      metrics: {
        wall_reconstruction_used: context.wallMap.wall_reconstruction_used,
        wall_point_count: context.wallMap.points.length,
        min_distance_m: common.round(context.incident.min_distance_m),
      },
      series: rows,
      plot: {
        traces,
        layout: {
          margin: { l: 46, r: 12, t: 12, b: 44 },
          xaxis: { title: { text: "world x (m)", font: { size: 11 } }, gridcolor: "#dee2e6", zerolinecolor: "#adb5bd" },
          yaxis: { title: { text: "world y (m)", font: { size: 11 } }, gridcolor: "#dee2e6", zerolinecolor: "#adb5bd", scaleanchor: "x", scaleratio: 1 },
          legend: { orientation: "h", y: -0.2, x: 0 },
        },
      },
    };
  }

  function trajectoryTrace(rows, xKey, yKey, name, color) {
    return {
      x: rows.map((row) => row[xKey]),
      y: rows.map((row) => row[yKey]),
      name,
      type: "scatter",
      mode: "lines",
      line: { color, width: 2.5 },
    };
  }

  function markerTrace(x, y, name, color, symbol = "circle") {
    return {
      x,
      y,
      name,
      type: "scatter",
      mode: "markers",
      marker: { color, size: 9, symbol },
    };
  }

  function timeSeriesTrace(rows, key, name, color, yaxis = "y") {
    return {
      x: rows.map((row) => row.time),
      y: rows.map((row) => row[key]),
      name,
      type: "scatter",
      mode: "lines",
      line: { color, width: 2.2 },
      connectgaps: false,
      yaxis,
    };
  }

  function timeMarkerShapes(context) {
    const shapes = [];
    const minDistanceTime = Number(context.incident && context.incident.min_distance_time);
    if (Number.isFinite(minDistanceTime)) {
      shapes.push({ type: "line", x0: minDistanceTime, x1: minDistanceTime, y0: 0, y1: 1, yref: "paper", line: { color: "#1565c0", width: 1, dash: "dot" } });
    }
    const collisionTime = Number(context.incident && context.incident.collision_time);
    if (Number.isFinite(collisionTime)) {
      shapes.push({ type: "line", x0: collisionTime, x1: collisionTime, y0: 0, y1: 1, yref: "paper", line: { color: "#dc2626", width: 1, dash: "dashdot" } });
    }
    return shapes;
  }

  function splitTimeSeriesLayout(context, upperTitle, lowerTitle, upperAxisTitle, lowerAxisTitle) {
    return {
      margin: { l: 52, r: 14, t: 32, b: 48 },
      xaxis: { title: { text: "time (s)", font: { size: 11 } }, gridcolor: "#dee2e6", zerolinecolor: "#6c757d" },
      yaxis: { domain: [0.57, 1.0], title: { text: upperAxisTitle, font: { size: 11 } }, gridcolor: "#dee2e6", zerolinecolor: "#adb5bd" },
      yaxis2: { domain: [0, 0.43], title: { text: lowerAxisTitle, font: { size: 11 } }, gridcolor: "#dee2e6", zerolinecolor: "#adb5bd" },
      legend: { orientation: "h", y: -0.18, x: 0 },
      shapes: timeMarkerShapes(context),
      annotations: [
        { text: upperTitle, x: 0.5, y: 1.08, xref: "paper", yref: "paper", showarrow: false, font: { size: 13 } },
        { text: lowerTitle, x: 0.5, y: 0.48, xref: "paper", yref: "paper", showarrow: false, font: { size: 13 } },
      ],
    };
  }

  function graphG02(context) {
    return graphResult(context, "G02", "G02 defines closest approach and whether a two-vehicle contact is plausible.", {
      min_distance_m: common.round(context.incident.min_distance_m),
      min_distance_time_s: common.round(context.incident.min_distance_time),
      collision_count_time_s: common.round(context.incident.collision_time),
    }, context.rows.map((row) => ({ time: row.time, distance: row.distance })));
  }

  function graphG03(context) {
    return graphResult(context, "G03", "G03 compares speed before contact for rear-end and divebomb evidence.", {}, context.rows.map((row) => ({
      time: row.time,
      a_speed: row.a_speed,
      b_speed: row.b_speed,
    })));
  }

  function graphG04(context) {
    return graphResult(context, "G04", "G04 shows ahead/behind and side relation in both vehicle frames.", {}, context.rows.map((row) => ({
      time: row.time,
      long_r2_in_r1: row.long_r2_in_r1,
      lat_r2_in_r1: row.lat_r2_in_r1,
      long_r1_in_r2: row.long_r1_in_r2,
      lat_r1_in_r2: row.lat_r1_in_r2,
    })));
  }

  function graphG05(context) {
    const hasBrake = context.rows.some((row) => Number.isFinite(row.a_brake) || Number.isFinite(row.b_brake));
    return graphResult(context, "G05", hasBrake
      ? "G05 includes throttle and brake intent near the incident."
      : "G05 includes throttle intent; brake telemetry is unavailable, so braking is not inferred.",
    { brake_data_available: hasBrake }, context.rows.map((row) => ({
      time: row.time,
      a_throttle: row.a_throttle,
      b_throttle: row.b_throttle,
      a_brake: row.a_brake,
      b_brake: row.b_brake,
    })));
  }

  function graphG06(context) {
    return graphResult(context, "G06", "G06 positive values mean A/B distance is closing.", {
      max_closing_speed_mps: common.round(maxValue(context.rows, "closing_speed")),
    }, context.rows.map((row) => ({ time: row.time, closing_speed: row.closing_speed })));
  }

  function graphG07(context) {
    return graphResult(context, "G07", "G07 checks steering changes and steering toward the opponent.", {}, context.rows.map((row) => ({
      time: row.time,
      a_steering: row.a_steering,
      b_steering: row.b_steering,
    })));
  }

  function graphG08(context) {
    return graphResult(context, "G08", "G08 shows whether lateral space collapses before contact.", {
      min_lateral_gap_m: common.round(minValue(context.rows, "lateral_gap")),
    }, context.rows.map((row) => ({ time: row.time, lateral_gap: row.lateral_gap })));
  }

  function graphG09(context) {
    return graphResult(context, "G09", "G09 negative values mean R2 is behind R1; approaching zero indicates overlap formation.", {}, context.rows.map((row) => ({
      time: row.time,
      longitudinal_gap_r2_in_r1: row.long_r2_in_r1,
    })));
  }

  function graphG10(context) {
    return graphResult(context, "G10", "G10 caps TTC at 5s and only reports it while distance is closing.", {
      min_ttc_s: common.round(minValue(context.rows, "ttc")),
    }, context.rows.map((row) => ({ time: row.time, ttc: row.ttc })));
  }

  function graphG11(context) {
    return graphResult(context, "G11", context.wallMap.wall_reconstruction_used
      ? "G11 estimates track-relative offset from reconstructed left/right wall distances."
      : "G11 is unavailable because wall reconstruction quality was insufficient.",
    { wall_reconstruction_used: context.wallMap.wall_reconstruction_used }, context.rows.map((row) => ({
      time: row.time,
      a_track_offset: row.a_track_offset,
      b_track_offset: row.b_track_offset,
    })));
  }

  function graphG12(context) {
    const result = graphResult(context, "G12", "G12 separates yaw-rate spikes from relative heading, so rotation evidence is not mixed with approach geometry.", {
      a_max_abs_yaw_rate_radps: common.round(maxAbs(context.rows, "a_yaw_rate")),
      b_max_abs_yaw_rate_radps: common.round(maxAbs(context.rows, "b_yaw_rate")),
    }, context.rows.map((row) => ({
      time: row.time,
      a_yaw_rate: row.a_yaw_rate,
      b_yaw_rate: row.b_yaw_rate,
      relative_heading: row.relative_heading,
    })));
    result.plot = {
      container_height: 520,
      traces: [
        timeSeriesTrace(context.rows, "a_yaw_rate", "A yaw rate", "#2e7d32"),
        timeSeriesTrace(context.rows, "b_yaw_rate", "B yaw rate", "#ef6c00"),
        timeSeriesTrace(context.rows, "relative_heading", "B heading - A heading", "#1565c0", "y2"),
      ],
      layout: splitTimeSeriesLayout(context, "G12A. Yaw rate", "G12B. Relative heading", "yaw rate", "relative heading (rad)"),
    };
    return result;
  }

  function graphG13(context) {
    return graphResult(context, "G13", context.wallMap.wall_reconstruction_used
      ? "G13 tracks side-wall clearance for wall impact and squeeze evidence."
      : "G13 is unavailable because reconstructed wall points were not reliable.",
    { wall_reconstruction_used: context.wallMap.wall_reconstruction_used }, context.rows.map((row) => ({
      time: row.time,
      a_left_wall: row.a_left_wall,
      a_right_wall: row.a_right_wall,
      a_min_wall_clearance: row.a_min_wall_clearance,
      b_left_wall: row.b_left_wall,
      b_right_wall: row.b_right_wall,
      b_min_wall_clearance: row.b_min_wall_clearance,
    })));
  }

  function graphG14(context) {
    const result = graphResult(context, "G14", "G14 separates acceleration and jerk proxies; both are secondary because derivative signals are noisy.", {}, context.rows.map((row) => ({
      time: row.time,
      a_acceleration: row.a_acceleration,
      b_acceleration: row.b_acceleration,
      a_jerk: row.a_jerk,
      b_jerk: row.b_jerk,
    })));
    result.plot = {
      container_height: 520,
      traces: [
        timeSeriesTrace(context.rows, "a_acceleration", "A acceleration proxy", "#2e7d32"),
        timeSeriesTrace(context.rows, "b_acceleration", "B acceleration proxy", "#ef6c00"),
        timeSeriesTrace(context.rows, "a_jerk", "A jerk proxy", "#2e7d32", "y2"),
        timeSeriesTrace(context.rows, "b_jerk", "B jerk proxy", "#ef6c00", "y2"),
      ],
      layout: splitTimeSeriesLayout(context, "G14A. Acceleration proxy", "G14B. Jerk proxy", "d(speed)/dt", "d(accel)/dt"),
    };
    return result;
  }

  function graphG15(context) {
    const series = context.rows.map((row) => contributionRow(row));
    return graphResult(context, "G15", "G15 is a heuristic contribution and uncertainty summary, not ground truth.", {
      final_a_contribution: common.round(series.length ? series[series.length - 1].a_contribution / 100 : null),
      final_b_contribution: common.round(series.length ? series[series.length - 1].b_contribution / 100 : null),
    }, series);
  }

  function graphResult(context, graphId, opinion, metrics, series) {
    return {
      graph: graphInfo(graphId, GRAPH_LABELS[graphId]),
      opinion,
      metrics: {
        min_distance_time_s: common.round(context.incident.min_distance_time),
        collision_count_time_s: common.round(context.incident.collision_time),
        ...metrics,
      },
      markers: {
        min_distance_time_s: context.incident.min_distance_time,
        collision_count_time_s: context.incident.collision_time,
      },
      series,
    };
  }

  function graphMapFromResults(graphResults) {
    return Object.fromEntries(graphResults.map((result) => [result.graph.id, result]));
  }

  function collisionTypeCT1(context, graphResults) {
    const info = pluginInfo("CT1", CT_LABELS.CT1);
    const best = bestVehicle(context.evidence.wall, "single_wall_score");
    const eventDistance = Number.isFinite(context.incident.analysis_distance_m)
      ? context.incident.analysis_distance_m
      : context.incident.min_distance_m;
    const distanceLarge = eventDistance !== null && eventDistance > 2.0;
    const score = distanceLarge ? best.single_wall_score : best.single_wall_score * 0.45;
    const decision = ctDecision(info.label, score);
    const penaltyVehicleId = score >= 0.55 ? best.vehicle_id : null;
    const faultPercentage = penaltyVehicleId ? Math.min(100, 70 + score * 30) : null;
    const detail = distanceLarge
      ? "opponent distance stayed large near the event"
      : "opponent proximity prevents a clean single-vehicle classification";
    return ctResult(info, decision, score, penaltyVehicleId, faultPercentage,
      `Opinion: ${decision}; ${penaltyVehicleId ? `fault Vehicle ${common.vehicleLabel(penaltyVehicleId)}` : "not primary"}. ${detail}; wall score ${(score * 100).toFixed(0)}%.`,
      {
        required_graphs: "G01,G13,G12,G14",
        wall_reconstruction_used: context.wallMap.wall_reconstruction_used,
        candidate_vehicle: common.vehicleLabel(best.vehicle_id),
        min_wall_clearance_m: common.round(best.min_wall_clearance_m),
        min_distance_m: common.round(context.incident.min_distance_m),
        event_distance_m: common.round(eventDistance),
      },
      graphResults);
  }

  function collisionTypeCT2(context, graphResults) {
    const info = pluginInfo("CT2", CT_LABELS.CT2);
    const loc = bestVehicle(context.evidence.loss, "score");
    const wall = context.evidence.wall[loc.vehicle_id];
    const eventDistance = Number.isFinite(context.incident.analysis_distance_m)
      ? context.incident.analysis_distance_m
      : context.incident.min_distance_m;
    const contactLikely = eventDistance !== null && eventDistance <= 2.2;
    const wallReboundSupport = context.wallMap.wall_reconstruction_used
      ? clip(wall.collapse_score * 0.55 + wall.clearance_score * 0.35 + wall.collision_score * 0.10)
      : 0;
    const contactGate = twoVehicleContactGate(context);
    const score = clip(contactGate * rearClosingConflictGate(context, loc.vehicle_id) * (
      loc.score * 0.55 * wallReboundSupport
      + wallReboundSupport * 0.35
      + (contactLikely && wallReboundSupport > 0.35 ? 0.10 : 0)
    ));
    const decision = ctDecision(info.label, score);
    const penaltyVehicleId = score >= 0.50 ? loc.vehicle_id : null;
    const faultPercentage = penaltyVehicleId ? 70 + score * 25 : null;
    return ctResult(info, decision, score, penaltyVehicleId, faultPercentage,
      `Opinion: ${decision}; ${penaltyVehicleId ? `unstable Vehicle ${common.vehicleLabel(penaltyVehicleId)} is primary` : "no clear wall-rebound initiator"}. Yaw/jerk/steering instability ${(loc.score * 100).toFixed(0)}%, wall-collapse ${(wall.collapse_score * 100).toFixed(0)}%.`,
      {
        required_graphs: "G01,G12,G13,G14",
        candidate_vehicle: common.vehicleLabel(loc.vehicle_id),
        yaw_spike_radps: common.round(loc.yaw_spike_radps),
        jerk_spike_mps3: common.round(loc.jerk_spike_mps3),
        wall_collapse_score: common.round(wall.collapse_score),
        wall_rebound_support: common.round(wallReboundSupport),
      },
      graphResults);
  }

  function collisionTypeCT3(context, graphResults) {
    const info = pluginInfo("CT3", CT_LABELS.CT3);
    const rear = bestVehicle(context.evidence.longitudinal, "score");
    const lateralAmbiguity = Math.max(context.evidence.lateral[1].score, context.evidence.lateral[2].score);
    const score = clip((rear.score - Math.max(0, lateralAmbiguity - 0.58) * 0.25) * twoVehicleContactGate(context));
    const decision = ctDecision(info.label, score);
    const penaltyVehicleId = score >= 0.50 ? rear.vehicle_id : null;
    const partialOverlap = context.evidence.side_by_side_score > 0.45;
    const faultPercentage = penaltyVehicleId ? Math.min(partialOverlap ? 85 : 100, 70 + score * 27) : null;
    return ctResult(info, decision, score, penaltyVehicleId, faultPercentage,
      `Opinion: ${decision}; ${penaltyVehicleId ? `rear/closing Vehicle ${common.vehicleLabel(penaltyVehicleId)} is primary` : "rear-closing evidence is weak"}. Behind ${(rear.behind_fraction * 100).toFixed(0)}%, speed advantage ${rear.speed_advantage_mps.toFixed(2)}m/s, TTC support ${(rear.ttc_score * 100).toFixed(0)}%.`,
      {
        required_graphs: "G03,G04,G06,G09,G10",
        candidate_vehicle: common.vehicleLabel(rear.vehicle_id),
        behind_fraction: common.round(rear.behind_fraction),
        speed_advantage_mps: common.round(rear.speed_advantage_mps),
        gap_closed_m: common.round(rear.gap_closed_m),
      },
      graphResults);
  }

  function collisionTypeCT4(context, graphResults) {
    const info = pluginInfo("CT4", CT_LABELS.CT4);
    const rear = bestVehicle(context.evidence.longitudinal, "score");
    const lateInside = lateInsideProxy(context, rear.vehicle_id);
    const score = clip(twoVehicleContactGate(context) * (
      rear.score * 0.55 * lateInside.score
      + lateInside.score * 0.35
      + context.evidence.low_ttc_score * 0.10 * lateInside.score
    ));
    const decision = ctDecision(info.label, score);
    const penaltyVehicleId = score >= 0.55 ? rear.vehicle_id : null;
    const faultPercentage = penaltyVehicleId ? 65 + score * 25 : null;
    return ctResult(info, decision, score, penaltyVehicleId, faultPercentage,
      `Opinion: ${decision}; ${penaltyVehicleId ? `late-entry Vehicle ${common.vehicleLabel(penaltyVehicleId)} is primary` : "corner-entry evidence is not strong enough"}. Rear-closing ${(rear.score * 100).toFixed(0)}%, inside-line proxy ${(lateInside.score * 100).toFixed(0)}%.`,
      {
        required_graphs: "G01,G03,G04,G06,G11",
        candidate_vehicle: common.vehicleLabel(rear.vehicle_id),
        rear_closing_score: common.round(rear.score),
        inside_line_proxy: common.round(lateInside.score),
        note: lateInside.note,
      },
      graphResults);
  }

  function collisionTypeCT5(context, graphResults) {
    const info = pluginInfo("CT5", CT_LABELS.CT5);
    const lateral = bestVehicle(context.evidence.lateral, "score");
    const rear = bestVehicle(context.evidence.longitudinal, "score");
    const longitudinalDominance = Math.max(0, rear.score - lateral.score);
    const primaryScore = clip(lateral.score - longitudinalDominance * 0.25);
    const minLateralGap = minValue(context.rows, "lateral_gap");
    const secondaryDescriptor = minLateralGap !== null && minLateralGap < 0.25 && context.evidence.side_by_side_score > 0.15;
    const score = clip(
      Math.max(primaryScore, secondaryDescriptor ? 0.46 : 0)
      * twoVehicleContactGate(context)
      * rearClosingConflictGate(context, lateral.vehicle_id),
    );
    const decision = ctDecision(info.label, score);
    const penaltyVehicleId = score >= 0.50 ? lateral.vehicle_id : null;
    const faultPercentage = penaltyVehicleId ? 60 + score * 30 : null;
    const noPenaltyDetail = secondaryDescriptor
      ? "secondary side-overlap descriptor only; longitudinal closing dominates"
      : "side-swipe evidence is secondary or weak";
    return ctResult(info, decision, score, penaltyVehicleId, faultPercentage,
      `Opinion: ${decision}; ${penaltyVehicleId ? `lateral-moving Vehicle ${common.vehicleLabel(penaltyVehicleId)} is primary` : noPenaltyDetail}. Lateral gap closed ${lateral.gap_closed_m.toFixed(2)}m; toward score ${(lateral.toward_score * 100).toFixed(0)}%.`,
      {
        required_graphs: "G04,G07,G08,G11",
        candidate_vehicle: common.vehicleLabel(lateral.vehicle_id),
        gap_closed_m: common.round(lateral.gap_closed_m),
        min_lateral_gap_m: common.round(minLateralGap),
        primary_score: common.round(primaryScore),
        secondary_descriptor: secondaryDescriptor,
        side_by_side_score: common.round(lateral.side_by_side_score),
        toward_score: common.round(lateral.toward_score),
      },
      graphResults);
  }

  function collisionTypeCT6(context, graphResults) {
    const info = pluginInfo("CT6", CT_LABELS.CT6);
    const squeeze = bestVehicle(context.evidence.squeeze, "score");
    const rawScore = context.wallMap.wall_reconstruction_used ? squeeze.score : squeeze.score * 0.45;
    const score = clip(rawScore * twoVehicleContactGate(context) * rearClosingConflictGate(context, squeeze.vehicle_id));
    const decision = ctDecision(info.label, score);
    const penaltyVehicleId = score >= 0.52 ? squeeze.vehicle_id : null;
    const faultPercentage = penaltyVehicleId ? 60 + score * 30 : null;
    return ctResult(info, decision, score, penaltyVehicleId, faultPercentage,
      `Opinion: ${decision}; ${penaltyVehicleId ? `squeezing Vehicle ${common.vehicleLabel(penaltyVehicleId)} is primary` : "wall-side squeeze evidence is weak"}. Opponent wall pressure ${(squeeze.opponent_wall_pressure * 100).toFixed(0)}%, side-by-side ${(squeeze.side_by_side_score * 100).toFixed(0)}%.`,
      {
        required_graphs: "G01,G04,G08,G11,G13",
        candidate_vehicle: common.vehicleLabel(squeeze.vehicle_id),
        opponent_wall_pressure: common.round(squeeze.opponent_wall_pressure),
        wall_reconstruction_used: context.wallMap.wall_reconstruction_used,
      },
      graphResults);
  }

  function collisionTypeCT7(context, graphResults) {
    const info = pluginInfo("CT7", CT_LABELS.CT7);
    const aRaw = vehicleCompositeScore(context, 1);
    const bRaw = vehicleCompositeScore(context, 2);
    const total = aRaw + bRaw;
    const aShare = total > 0.001 ? aRaw / total : 0.5;
    const bShare = total > 0.001 ? bRaw / total : 0.5;
    const balance = 1 - Math.abs(aShare - bShare);
    const score = clip((1 - context.evidence.top_primary_score) * 0.65 + balance * 0.35);
    const decision = score >= 0.62 ? `${info.label} likely` : (score >= 0.42 ? `${info.label} possible` : `${info.label} unlikely`);
    return ctResult(info, decision, score, null, null,
      `Opinion: ${decision}; shared/no primary penalty recommended. Estimated split A ${(aShare * 100).toFixed(0)}%, B ${(bShare * 100).toFixed(0)}%; uncertainty ${(score * 100).toFixed(0)}%.`,
      {
        required_graphs: "G02,G03,G04,G08,G15",
        a_estimated_share: common.round(aShare),
        b_estimated_share: common.round(bShare),
        top_primary_score: common.round(context.evidence.top_primary_score),
      },
      graphResults);
  }

  function ctDecision(label, score) {
    if (score >= 0.70) {
      return `${label} likely`;
    }
    if (score >= 0.45) {
      return `${label} possible`;
    }
    return `${label} unlikely`;
  }

  function ctResult(info, decision, contributionScore, penaltyVehicleId, faultPercentage, opinion, metrics, graphResults) {
    const normalizedFault = Number.isFinite(faultPercentage) ? Math.max(0, Math.min(100, faultPercentage)) : null;
    return {
      package: info,
      decision,
      contribution_score: contributionScore,
      fault_percentage: normalizedFault,
      opinion,
      confidence: contributionScore,
      penalty_vehicle_id: penaltyVehicleId,
      metrics: {
        ct_id: info.id,
        contribution_score: common.round(contributionScore),
        ...metrics,
      },
      graphs: graphResults,
      series: graphResults.length ? graphResults[0].series : [],
    };
  }

  function incidentEventDistance(incident) {
    return Number.isFinite(incident && incident.analysis_distance_m)
      ? incident.analysis_distance_m
      : (Number.isFinite(incident && incident.min_distance_m) ? incident.min_distance_m : null);
  }

  function twoVehicleContactGate(context) {
    const distance = incidentEventDistance(context && context.incident);
    if (distance === null) {
      return 1;
    }
    return clip((3.0 - distance) / 0.8);
  }

  function rearClosingConflictGate(context, candidateVehicleId) {
    const rear = bestVehicle(context.evidence.longitudinal, "score");
    if (rear.vehicle_id === candidateVehicleId) {
      return 1;
    }
    const strongRearClosing = rear.score >= 0.65 && rear.behind_fraction >= 0.8 && rear.speed_advantage_mps >= 0.4;
    if (!strongRearClosing) {
      return 1;
    }
    return 1 - clip((rear.score - 0.65) / 0.25) * 0.75;
  }

  function contributionRow(row) {
    const aLong = row.long_r1_in_r2 < -0.05 ? 0.22 : 0;
    const bLong = row.long_r2_in_r1 < -0.05 ? 0.22 : 0;
    const aSpeed = Math.max(0, row.a_speed - row.b_speed);
    const bSpeed = Math.max(0, row.b_speed - row.a_speed);
    const closing = clip(Math.max(0, finiteOrDefault(row.closing_speed, 0)) / 0.8);
    const ttc = row.ttc === null ? 0 : clip((2.0 - row.ttc) / 2.0);
    const aLat = clip(Math.max(0, finiteOrDefault(row.a_lateral_toward, 0)) / 0.35);
    const bLat = clip(Math.max(0, finiteOrDefault(row.b_lateral_toward, 0)) / 0.35);
    const aWall = row.a_min_wall_clearance === null ? 0 : clip((0.65 - row.a_min_wall_clearance) / 0.65);
    const bWall = row.b_min_wall_clearance === null ? 0 : clip((0.65 - row.b_min_wall_clearance) / 0.65);
    const aLoc = clip(Math.abs(finiteOrDefault(row.a_yaw_rate, 0)) / 2.0 + Math.abs(finiteOrDefault(row.a_jerk, 0)) / 8.0);
    const bLoc = clip(Math.abs(finiteOrDefault(row.b_yaw_rate, 0)) / 2.0 + Math.abs(finiteOrDefault(row.b_jerk, 0)) / 8.0);
    const a = clip(aLong + clip(aSpeed / 0.6) * 0.18 + closing * 0.12 + ttc * 0.08 + aLat * 0.22 + aWall * 0.10 + aLoc * 0.08);
    const b = clip(bLong + clip(bSpeed / 0.6) * 0.18 + closing * 0.12 + ttc * 0.08 + bLat * 0.22 + bWall * 0.10 + bLoc * 0.08);
    const total = a + b;
    const aShare = total > 0.001 ? a / total : 0.5;
    const bShare = total > 0.001 ? b / total : 0.5;
    return {
      time: row.time,
      a_contribution: aShare * 100,
      b_contribution: bShare * 100,
      uncertainty: (1 - Math.max(a, b)) * 100,
    };
  }

  function lateInsideProxy(context, vehicleId) {
    const rows = context.evidence.pre_rows;
    const isA = vehicleId === 1;
    const offsetKey = isA ? "a_track_offset" : "b_track_offset";
    const toward = context.evidence.lateral[vehicleId].toward_score;
    const offsets = finiteValues(rows, offsetKey);
    if (!context.wallMap.wall_reconstruction_used || offsets.length < 2) {
      return { score: toward * 0.35, note: "wall-derived inside-line evidence unavailable; using lateral motion only" };
    }
    const offsetChange = Math.abs(offsets[offsets.length - 1] - offsets[0]);
    const lateralMotionGate = clip(toward / 0.25);
    return {
      score: clip(clip(offsetChange / 0.35) * 0.65 * lateralMotionGate + toward * 0.35),
      note: "inside-line proxy uses track-offset change from reconstructed walls, gated by lateral motion toward the other vehicle",
    };
  }

  function vehicleCompositeScore(context, vehicleId) {
    const evidence = context.evidence;
    return (
      evidence.longitudinal[vehicleId].score * 0.32
      + evidence.lateral[vehicleId].score * 0.28
      + evidence.wall[vehicleId].single_wall_score * 0.18
      + evidence.loss[vehicleId].score * 0.14
      + evidence.squeeze[vehicleId].score * 0.08
    );
  }

  function enabledGraphIdsForCollisionType(collisionType, enabledGraphs) {
    return collisionType.graph_ids.filter((id) => enabledGraphs[id] !== false);
  }

  function bestVehicle(byVehicle, scoreKey) {
    return VEHICLES
      .map((vehicleId) => byVehicle[vehicleId])
      .sort((left, right) => right[scoreKey] - left[scoreKey])[0];
  }

  function sideBySideScore(rows) {
    return fraction(rows, (row) => Math.abs(finiteOrDefault(row.long_r2_in_r1, 99)) < 1.0);
  }

  function lowTtcScore(rows) {
    const ttcValues = finiteValues(rows, "ttc");
    if (!ttcValues.length) {
      return 0;
    }
    return clip((2.0 - Math.min(...ttcValues)) / 2.0);
  }

  function firstCollisionRow(rows) {
    return rows.find((row) => row.a_collision_delta > 0 || row.b_collision_delta > 0) || null;
  }

  function finiteValues(rows, key) {
    return rows.map((row) => finiteOrNull(row[key])).filter(Number.isFinite);
  }

  function fraction(rows, predicate) {
    if (!rows.length) {
      return 0;
    }
    return rows.filter(predicate).length / rows.length;
  }

  function average(values) {
    const finite = values.filter(Number.isFinite);
    return finite.length ? finite.reduce((total, value) => total + value, 0) / finite.length : 0;
  }

  function minValue(rows, key) {
    const values = finiteValues(rows, key);
    return values.length ? Math.min(...values) : null;
  }

  function maxValue(rows, key) {
    const values = finiteValues(rows, key);
    return values.length ? Math.max(...values) : null;
  }

  function maxAbs(rows, key) {
    const values = finiteValues(rows, key).map(Math.abs);
    return values.length ? Math.max(...values) : 0;
  }

  function minFinite(...values) {
    const finite = values.filter(Number.isFinite);
    return finite.length ? Math.min(...finite) : null;
  }

  function finiteOrNull(value) {
    if (value === null || value === undefined || (typeof value === "string" && value.trim() === "")) {
      return null;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function finiteOrDefault(value, fallback) {
    if (value === null || value === undefined || (typeof value === "string" && value.trim() === "")) {
      return fallback;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function clip(value) {
    return common.clipScore(value);
  }

  function wrapToPi(angle) {
    return Math.atan2(Math.sin(angle), Math.cos(angle));
  }

  const graphs = Object.fromEntries(GRAPH_ORDER.map((id) => [id, {
    info: graphInfo(id, GRAPH_LABELS[id]),
    analyze: {
      G01: graphG01,
      G02: graphG02,
      G03: graphG03,
      G04: graphG04,
      G05: graphG05,
      G06: graphG06,
      G07: graphG07,
      G08: graphG08,
      G09: graphG09,
      G10: graphG10,
      G11: graphG11,
      G12: graphG12,
      G13: graphG13,
      G14: graphG14,
      G15: graphG15,
    }[id],
  }]));

  const collisionTypes = {
    CT1: {
      info: pluginInfo("CT1", CT_LABELS.CT1),
      graph_ids: ["G01", "G02", "G03", "G04", "G13", "G12", "G14"],
      analyze: collisionTypeCT1,
    },
    CT2: {
      info: pluginInfo("CT2", CT_LABELS.CT2),
      graph_ids: ["G01", "G02", "G03", "G04", "G13", "G12", "G14", "G07", "G11"],
      analyze: collisionTypeCT2,
    },
    CT3: {
      info: pluginInfo("CT3", CT_LABELS.CT3),
      graph_ids: ["G01", "G02", "G03", "G04", "G06", "G09", "G10"],
      analyze: collisionTypeCT3,
    },
    CT4: {
      info: pluginInfo("CT4", CT_LABELS.CT4),
      graph_ids: ["G01", "G02", "G03", "G04", "G06", "G09", "G10", "G11", "G05", "G07", "G13"],
      analyze: collisionTypeCT4,
    },
    CT5: {
      info: pluginInfo("CT5", CT_LABELS.CT5),
      graph_ids: ["G01", "G02", "G03", "G04", "G07", "G08", "G11", "G12", "G15"],
      analyze: collisionTypeCT5,
    },
    CT6: {
      info: pluginInfo("CT6", CT_LABELS.CT6),
      graph_ids: ["G01", "G02", "G03", "G04", "G07", "G08", "G11", "G13", "G12", "G15"],
      analyze: collisionTypeCT6,
    },
    CT7: {
      info: pluginInfo("CT7", CT_LABELS.CT7),
      graph_ids: ["G01", "G02", "G03", "G04", "G08", "G15", "G06", "G10", "G11", "G12", "G13"],
      analyze: collisionTypeCT7,
    },
  };

  window.RCTDecisionPacksV2 = {
    VERSION,
    listGraphs() {
      return GRAPH_ORDER.map((id) => graphs[id].info);
    },
    listCollisionTypes() {
      return CT_ORDER.map((id) => collisionTypes[id].info);
    },
    getCollisionType(id) {
      return collisionTypes[id] || null;
    },
    analyze(id, summary, options = {}) {
      const collisionType = collisionTypes[id];
      if (!collisionType) {
        throw new Error(`Unknown decision pack v2 collision type: ${id}`);
      }
      const context = buildContext(summary);
      const enabledGraphs = options.graphs && typeof options.graphs === "object" ? options.graphs : {};
      const graphResults = enabledGraphIdsForCollisionType(collisionType, enabledGraphs)
        .map((graphId) => graphs[graphId].analyze(context));
      return {
        id,
        input_version: VERSION,
        output_version: VERSION,
        framework_version: "2",
        ...collisionType.analyze(context, graphResults),
      };
    },
  };
})();
