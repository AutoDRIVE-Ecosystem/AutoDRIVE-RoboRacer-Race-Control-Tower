// SPDX-License-Identifier: BSD-3-Clause

(function () {
  "use strict";

  const VERSION = "0.1";

  function numeric(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function vehicleLabel(vehicleId) {
    return { 1: "A", 2: "B" }[Number(vehicleId)] || String(vehicleId);
  }

  function pointFromFrame(frame, vehicleId) {
    const telemetry = frame && frame.vehicles ? frame.vehicles[String(vehicleId)] : null;
    const ips = telemetry && telemetry.ips;
    if (!ips || typeof ips !== "object") {
      return null;
    }
    const x = numeric(ips.x);
    const y = numeric(ips.y);
    if (x === null || y === null) {
      return null;
    }
    const linearVelocity = telemetry.linear_velocity && typeof telemetry.linear_velocity === "object"
      ? telemetry.linear_velocity
      : null;
    return {
      x,
      y,
      speed: numeric(telemetry.speed),
      collision_count: numeric(telemetry.collision_count),
      heading_yaw: numeric(telemetry.heading_yaw),
      linear_velocity: linearVelocity,
    };
  }

  function samplesFromFrames(frames) {
    const samples = [];
    for (const frame of Array.isArray(frames) ? frames : []) {
      const vehicleA = pointFromFrame(frame, 1);
      const vehicleB = pointFromFrame(frame, 2);
      if (!vehicleA || !vehicleB) {
        continue;
      }
      const timeValue = numeric(frame.time_to_accident_seconds);
      samples.push({
        time: timeValue === null ? samples.length : timeValue,
        vehicles: { 1: vehicleA, 2: vehicleB },
      });
    }
    samples.forEach((sample, index) => {
      [1, 2].forEach((vehicleId) => {
        const point = sample.vehicles[vehicleId];
        const velocity = velocityAt(samples, index, vehicleId);
        point.velocity = velocity;
        point.calculated_speed = point.speed === null ? vectorLength(velocity) : point.speed;
        if (point.heading_yaw === null && velocity && vectorLength(velocity) > 0.05) {
          point.heading_yaw = Math.atan2(velocity.y, velocity.x);
        }
      });
    });
    return samples;
  }

  function collisionCount(sample, vehicleId) {
    const value = sample.vehicles[vehicleId].collision_count;
    return value === null ? null : Math.trunc(Number(value));
  }

  function velocityAt(samples, index, vehicleId) {
    const point = samples[index].vehicles[vehicleId];
    const linearVelocity = point.linear_velocity;
    if (linearVelocity && typeof linearVelocity === "object") {
      const x = numeric(linearVelocity.x);
      const y = numeric(linearVelocity.y);
      if (x !== null && y !== null) {
        return { x, y };
      }
    }
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const previous = samples[cursor].vehicles[vehicleId];
      const dt = samples[index].time - samples[cursor].time;
      if (dt > 0.001) {
        return { x: (point.x - previous.x) / dt, y: (point.y - previous.y) / dt };
      }
    }
    return null;
  }

  function vectorLength(vector) {
    return vector ? Math.hypot(vector.x, vector.y) : 0;
  }

  function distance(left, right) {
    return Math.hypot(right.x - left.x, right.y - left.y);
  }

  function basis(vehicle, target) {
    let heading = vehicle.heading_yaw;
    if (heading === null && vehicle.velocity && vectorLength(vehicle.velocity) > 0.05) {
      heading = Math.atan2(vehicle.velocity.y, vehicle.velocity.x);
    }
    if (heading === null) {
      heading = Math.atan2(vehicle.y - target.y, vehicle.x - target.x);
    }
    const forward = { x: Math.cos(heading), y: Math.sin(heading) };
    return [forward, { x: -forward.y, y: forward.x }];
  }

  function basisFromSamples(samples, index, vehicleId, otherId) {
    const vehicle = samples[index].vehicles[vehicleId];
    const other = samples[index].vehicles[otherId];
    for (let cursor = Math.max(0, index - 40); cursor < index; cursor += 1) {
      const previous = samples[cursor].vehicles[vehicleId];
      const dx = vehicle.x - previous.x;
      const dy = vehicle.y - previous.y;
      const length = Math.hypot(dx, dy);
      if (length >= 0.05 && length <= 4.0) {
        const forward = { x: dx / length, y: dy / length };
        return [forward, { x: -forward.y, y: forward.x }];
      }
    }
    return basis(vehicle, other);
  }

  function sampleHasPositionJump(samples, index) {
    if (index <= 0) {
      return false;
    }
    const previous = samples[index - 1];
    const current = samples[index];
    const dt = current.time - previous.time;
    return [1, 2].some((vehicleId) => {
      const jump = distance(previous.vehicles[vehicleId], current.vehicles[vehicleId]);
      return jump > 0.75 && (dt <= 0.05 || jump > 2.0);
    });
  }

  function recentSamples(samples, seconds) {
    if (!samples.length) {
      return [];
    }
    const lastTime = samples[samples.length - 1].time;
    const selected = samples.filter((sample) => sample.time >= lastTime - seconds);
    return selected.length >= 2 ? selected : samples.slice(-Math.min(samples.length, 12));
  }

  function clipScore(value) {
    return Math.max(0, Math.min(1, value));
  }

  function emptyAnalysis(packageInfo, opinion) {
    return { package: packageInfo, opinion, confidence: 0, penalty_vehicle_id: null, metrics: {}, series: [] };
  }

  function rearEndCandidate(samples, attackerId, targetId) {
    if (samples.length < 2) {
      return null;
    }
    const windowSamples = recentSamples(samples, 0.75);
    const startIndex = samples.length - windowSamples.length;
    const candidates = [];
    for (let index = startIndex; index < samples.length; index += 1) {
      if (!sampleHasPositionJump(samples, index)) {
        const candidate = rearEndCandidateAt(samples, index, attackerId, targetId);
        if (candidate) {
          candidates.push(candidate);
        }
      }
    }
    return candidates.sort((left, right) => (right.score - left.score) || (left.distance - right.distance) || (right.time - left.time))[0] || null;
  }

  function rearEndCandidateAt(samples, index, attackerId, targetId) {
    const sample = samples[index];
    const attacker = sample.vehicles[attackerId];
    const target = sample.vehicles[targetId];
    const [forward, right] = basisFromSamples(samples, index, targetId, attackerId);
    const dx = target.x - attacker.x;
    const dy = target.y - attacker.y;
    const longitudinal = dx * forward.x + dy * forward.y;
    const lateral = Math.abs(dx * right.x + dy * right.y);
    const finalDistance = distance(attacker, target);
    const av = attacker.velocity;
    const tv = target.velocity;
    const closing = av && tv
      ? (av.x - tv.x) * forward.x + (av.y - tv.y) * forward.y
      : Number(attacker.calculated_speed || 0) - Number(target.calculated_speed || 0);
    const first = samples[Math.max(0, index - 40)];
    const approach = distance(first.vehicles[attackerId], first.vehicles[targetId]) - finalDistance;
    let score = 0.34 * clipScore(longitudinal / 0.6);
    score += 0.2 * clipScore(1.0 - lateral / 1.2);
    score += closing > 0.2 ? 0.25 : (closing > 0.05 ? 0.12 : 0);
    score += approach > 0.25 ? 0.14 : (approach > 0.05 ? 0.07 : 0);
    score += finalDistance <= 2.0 ? 0.07 : 0;
    return {
      vehicle_id: attackerId,
      other_id: targetId,
      score: clipScore(score),
      closing,
      lateral_gap: lateral,
      distance: finalDistance,
      approach,
      longitudinal_gap: longitudinal,
      time: sample.time,
    };
  }

  function lateralCandidate(samples, vehicleId, otherId) {
    if (samples.length < 2) {
      return null;
    }
    const windowSamples = recentSamples(samples, 0.75);
    const startIndex = samples.length - windowSamples.length;
    const candidates = [];
    for (let index = startIndex; index < samples.length; index += 1) {
      if (!sampleHasPositionJump(samples, index)) {
        const candidate = lateralCandidateAt(samples, index, vehicleId, otherId);
        if (candidate) {
          candidates.push(candidate);
        }
      }
    }
    return candidates.sort((left, right) => (right.score - left.score) || (left.distance - right.distance) || (right.time - left.time))[0] || null;
  }

  function lateralCandidateAt(samples, index, vehicleId, otherId) {
    const sample = samples[index];
    const vehicle = sample.vehicles[vehicleId];
    const other = sample.vehicles[otherId];
    const [, right] = basisFromSamples(samples, index, vehicleId, otherId);
    const lateral = (other.x - vehicle.x) * right.x + (other.y - vehicle.y) * right.y;
    const lateralGap = Math.abs(lateral);
    const velocity = vehicle.velocity || { x: 0, y: 0 };
    const toward = lateral === 0 ? 0 : (velocity.x * right.x + velocity.y * right.y) * (lateral > 0 ? 1 : -1);
    const firstIndex = Math.max(0, index - 40);
    const first = samples[firstIndex];
    const firstVehicle = first.vehicles[vehicleId];
    const firstOther = first.vehicles[otherId];
    const [, firstRight] = basisFromSamples(samples, firstIndex, vehicleId, otherId);
    const firstGap = Math.abs((firstOther.x - firstVehicle.x) * firstRight.x + (firstOther.y - firstVehicle.y) * firstRight.y);
    const gapClosed = firstGap - lateralGap;
    const finalDistance = distance(vehicle, other);
    let score = 0;
    score += toward > 0.25 ? 0.34 : (toward > 0.08 ? 0.16 : 0);
    score += gapClosed > 0.5 ? 0.28 : (gapClosed > 0.15 ? 0.12 : 0);
    score += lateralGap < 1.0 ? 0.22 : (lateralGap < 1.6 ? 0.12 : 0);
    score += finalDistance < 2.0 ? 0.16 : 0;
    return {
      vehicle_id: vehicleId,
      other_id: otherId,
      score: clipScore(score),
      lateral_gap: lateralGap,
      toward,
      gap_closed: gapClosed,
      distance: finalDistance,
      time: sample.time,
    };
  }

  function acceleration(samples, vehicleId) {
    if (samples.length < 2) {
      return 0;
    }
    const last = samples[samples.length - 1];
    const previous = samples[samples.length - 2];
    const dt = last.time - previous.time;
    if (dt <= 0.001) {
      return 0;
    }
    return (Number(last.vehicles[vehicleId].calculated_speed || 0) - Number(previous.vehicles[vehicleId].calculated_speed || 0)) / dt;
  }

  function genericCandidate(samples, vehicleId, otherId, mode) {
    const rear = rearEndCandidate(samples, vehicleId, otherId);
    const lateral = lateralCandidate(samples, vehicleId, otherId);
    if (!rear || !lateral) {
      return null;
    }
    const accel = acceleration(samples, vehicleId);
    let score;
    if (mode === "late") {
      score = clipScore(rear.score * 0.75 + (rear.closing > 0.35 ? 0.18 : 0) + (rear.approach > 0.7 ? 0.1 : 0));
    } else if (mode === "squeeze") {
      score = clipScore(lateral.score * 0.75 + (accel > 0.1 ? 0.16 : 0) + (lateral.gap_closed > 0.45 ? 0.1 : 0));
    } else if (mode === "rejoin") {
      score = clipScore(lateral.score * 0.65 + (lateral.gap_closed > 0.7 ? 0.2 : 0) + (lateral.distance < 2.2 ? 0.12 : 0));
    } else {
      score = clipScore((rear.score + lateral.score) / 2);
    }
    return { vehicle_id: vehicleId, other_id: otherId, score, rear, lateral, accel };
  }

  function metricsFromCandidates(candidates) {
    const metrics = {};
    candidates.forEach((candidate) => {
      metrics[`vehicle_${candidate.vehicle_id}_score`] = round(candidate.score);
    });
    const best = candidates[0];
    if (best) {
      ["closing", "longitudinal_gap", "lateral_gap", "distance", "approach", "toward", "gap_closed"].forEach((key) => {
        if (key in best) {
          metrics[key] = round(Number(best[key]));
        }
      });
    }
    return metrics;
  }

  function rearEndSeries(samples) {
    return samples.map((sample, index) => {
      const partial = samples.slice(0, index + 1);
      const a = rearEndCandidate(partial, 1, 2);
      const b = rearEndCandidate(partial, 2, 1);
      return {
        time: sample.time,
        distance: distance(sample.vehicles[1], sample.vehicles[2]),
        a_closing: a ? a.closing : null,
        b_closing: b ? b.closing : null,
      };
    });
  }

  function lateralSeries(samples) {
    return samples.map((sample, index) => {
      const partial = samples.slice(0, index + 1);
      const a = lateralCandidate(partial, 1, 2);
      const b = lateralCandidate(partial, 2, 1);
      return {
        time: sample.time,
        distance: distance(sample.vehicles[1], sample.vehicles[2]),
        a_toward: a ? a.toward : null,
        b_toward: b ? b.toward : null,
        lateral_gap: a ? a.lateral_gap : null,
      };
    });
  }

  function genericSeriesForMode(mode) {
    return function build(samples) {
      return samples.map((sample, index) => {
        const partial = samples.slice(0, index + 1);
        const a = partial.length >= 2 ? genericCandidate(partial, 1, 2, mode) : null;
        const b = partial.length >= 2 ? genericCandidate(partial, 2, 1, mode) : null;
        return {
          time: sample.time,
          distance: distance(sample.vehicles[1], sample.vehicles[2]),
          a_score: a ? a.score * 100 : null,
          b_score: b ? b.score * 100 : null,
        };
      });
    };
  }

  function sharedSeries(samples) {
    return genericSeriesForMode("shared")(samples).map((row) => {
      const a = Number(row.a_score || 0);
      const b = Number(row.b_score || 0);
      return { ...row, shared_score: Math.max(0, (a + b) / 2 - Math.abs(a - b) * 0.65) };
    });
  }

  function analyzeGenericPrimary(packageInfo, samples, mode, label, scoreLabel, seriesBuilder) {
    if (samples.length < 3) {
      return emptyAnalysis(packageInfo, "Opinion: Waiting for enough A/B position history.");
    }
    const candidates = [genericCandidate(samples, 1, 2, mode), genericCandidate(samples, 2, 1, mode)]
      .filter(Boolean)
      .sort((left, right) => right.score - left.score);
    const best = candidates[0];
    if (!best) {
      return emptyAnalysis(packageInfo, `Opinion: ${label} cannot be evaluated from this log.`);
    }
    const vehicle = vehicleLabel(best.vehicle_id);
    const other = vehicleLabel(best.other_id);
    const penalty = best.score >= 0.5 ? best.vehicle_id : null;
    const decision = best.score >= 0.7 ? `${label} likely` : (best.score >= 0.5 ? `${label} possible` : `${label} unlikely`);
    const opinion = `Opinion: ${decision}; ${best.score >= 0.7 ? `primary penalty Vehicle ${vehicle}` : (penalty ? `possible penalty Vehicle ${vehicle}` : "no clear penalty")}. Confidence ${(best.score * 100).toFixed(0)}%. Vehicle ${vehicle} pressure toward Vehicle ${other}; ${scoreLabel} ${(best.score * 100).toFixed(0)}%.`;
    return {
      package: packageInfo,
      opinion,
      confidence: best.score,
      penalty_vehicle_id: penalty,
      metrics: {
        ...Object.fromEntries(candidates.map((item) => [`vehicle_${item.vehicle_id}_score`, round(item.score)])),
        distance_m: round(best.lateral.distance),
        lateral_gap_m: round(best.lateral.lateral_gap),
      },
      series: seriesBuilder(samples),
    };
  }

  function round(value, digits = 3) {
    return Number.isFinite(value) ? Number(value.toFixed(digits)) : value;
  }

  window.RCTDecisionCommon = {
    VERSION,
    numeric,
    vehicleLabel,
    samplesFromFrames,
    collisionCount,
    distance,
    clipScore,
    emptyAnalysis,
    rearEndCandidate,
    lateralCandidate,
    genericCandidate,
    analyzeGenericPrimary,
    metricsFromCandidates,
    rearEndSeries,
    lateralSeries,
    genericSeriesForMode,
    sharedSeries,
    round,
  };
})();
