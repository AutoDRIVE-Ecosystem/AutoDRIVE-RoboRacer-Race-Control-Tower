// SPDX-License-Identifier: BSD-3-Clause

(function () {
  "use strict";

  const common = window.RCTDecisionCommon;
  const VERSION = common.VERSION;

  function packageInfo(id, label) {
    return { id, label, input_version: VERSION, output_version: VERSION };
  }

  function rearEndCollision(samples) {
    const pack = packageInfo("rear_end_collision", "Rear-end collision");
    if (samples.length < 2) {
      return common.emptyAnalysis(pack, "Opinion: Waiting for enough A/B position history.");
    }
    const candidates = [common.rearEndCandidate(samples, 1, 2), common.rearEndCandidate(samples, 2, 1)]
      .filter(Boolean)
      .sort((left, right) => right.score - left.score);
    const best = candidates[0];
    if (!best) {
      return common.emptyAnalysis(pack, "Opinion: Rear-end collision cannot be evaluated from this log.");
    }
    const label = common.vehicleLabel(best.vehicle_id);
    const other = common.vehicleLabel(best.other_id);
    let decision = "Rear-end unlikely";
    let penalty = null;
    if (best.score >= 0.7) {
      decision = "Rear-end likely";
      penalty = best.vehicle_id;
    } else if (best.score >= 0.5) {
      decision = "Rear-end possible";
      penalty = best.vehicle_id;
    }
    const speedNote = best.closing > 0.05
      ? `closing ${best.closing.toFixed(2)}m/s`
      : `directional gap ${best.longitudinal_gap.toFixed(2)}m`;
    return {
      package: pack,
      opinion: `Opinion: ${decision}; ${penalty && best.score >= 0.7 ? `primary penalty Vehicle ${label}` : (penalty ? `possible penalty Vehicle ${label}` : "no clear penalty")}. Confidence ${(best.score * 100).toFixed(0)}%. Vehicle ${label} was behind Vehicle ${other}; ${speedNote}.`,
      confidence: best.score,
      penalty_vehicle_id: penalty,
      metrics: common.metricsFromCandidates(candidates),
      series: common.rearEndSeries(samples),
    };
  }

  function singleVehicleCollision(samples) {
    const pack = packageInfo("single_vehicle_collision", "Single vehicle collision");
    if (samples.length < 2) {
      return common.emptyAnalysis(pack, "Opinion: Waiting for enough A/B telemetry history.");
    }
    const changes = collisionCountChanges(samples);
    const lastDistance = common.distance(samples[samples.length - 1].vehicles[1], samples[samples.length - 1].vehicles[2]);
    const recent = samples.slice(-Math.min(samples.length, 20));
    const minRecentDistance = Math.min(...recent.map((sample) => common.distance(sample.vehicles[1], sample.vehicles[2])));
    const changedVehicleIds = Array.from(new Set(changes.map((change) => change.vehicle_id))).sort();
    let faultVehicleId = changedVehicleIds.length === 1 ? changedVehicleIds[0] : null;
    let confidence;
    let decision;
    let detail;
    if (faultVehicleId !== null && minRecentDistance > 2.0) {
      confidence = 0.92;
      decision = "Single vehicle collision likely";
      detail = `only Vehicle ${common.vehicleLabel(faultVehicleId)} collision count increased while A-B distance stayed ${minRecentDistance.toFixed(2)}m or more`;
    } else if (faultVehicleId !== null) {
      confidence = 0.62;
      decision = "Single vehicle collision possible";
      detail = `only Vehicle ${common.vehicleLabel(faultVehicleId)} collision count increased, but A-B distance became close`;
    } else if (changedVehicleIds.length >= 2) {
      confidence = 0.08;
      decision = "Single vehicle collision unlikely";
      detail = "both vehicles recorded collision count increases";
    } else {
      confidence = 0.0;
      decision = "Single vehicle collision not detected";
      detail = "no collision count increase is visible in this analysis window";
    }
    return {
      package: pack,
      opinion: `Opinion: ${decision}; ${faultVehicleId ? `fault Vehicle ${common.vehicleLabel(faultVehicleId)}` : "no single-vehicle fault"}. Confidence ${(confidence * 100).toFixed(0)}%. ${detail}.`,
      confidence,
      penalty_vehicle_id: faultVehicleId,
      metrics: {
        collision_change_count: changes.length,
        changed_vehicles: changedVehicleIds.map(common.vehicleLabel).join(",") || "none",
        min_recent_ab_distance_m: common.round(minRecentDistance),
        final_ab_distance_m: common.round(lastDistance),
      },
      series: singleCollisionSeries(samples),
    };
  }

  function collisionCountChanges(samples) {
    const previous = {};
    const changes = [];
    for (const sample of samples) {
      [1, 2].forEach((vehicleId) => {
        const count = common.collisionCount(sample, vehicleId);
        if (count === null) {
          return;
        }
        const oldCount = previous[vehicleId];
        if (oldCount !== undefined && count > oldCount) {
          changes.push({ time: sample.time, vehicle_id: vehicleId, from: oldCount, to: count });
        }
        previous[vehicleId] = count;
      });
    }
    return changes;
  }

  function singleCollisionSeries(samples) {
    const previous = {};
    return samples.map((sample) => {
      const row = {
        time: sample.time,
        ab_distance: common.distance(sample.vehicles[1], sample.vehicles[2]),
      };
      [[1, "a_collision_delta"], [2, "b_collision_delta"]].forEach(([vehicleId, key]) => {
        const count = common.collisionCount(sample, vehicleId);
        const oldCount = previous[vehicleId];
        row[key] = count !== null && oldCount !== undefined ? Math.max(0, count - oldCount) : 0;
        if (count !== null) {
          previous[vehicleId] = count;
        }
      });
      return row;
    });
  }

  function unsafeLateralMovement(samples) {
    const pack = packageInfo("unsafe_lateral_movement", "Unsafe lateral movement");
    if (samples.length < 2) {
      return common.emptyAnalysis(pack, "Opinion: Waiting for enough A/B position history.");
    }
    const candidates = [common.lateralCandidate(samples, 1, 2), common.lateralCandidate(samples, 2, 1)]
      .filter(Boolean)
      .sort((left, right) => right.score - left.score);
    const best = candidates[0];
    if (!best) {
      return common.emptyAnalysis(pack, "Opinion: Unsafe lateral movement cannot be evaluated from this log.");
    }
    const label = common.vehicleLabel(best.vehicle_id);
    const other = common.vehicleLabel(best.other_id);
    const penalty = best.score >= 0.5 ? best.vehicle_id : null;
    const decision = best.score >= 0.7 ? "Unsafe lateral movement likely" : (best.score >= 0.5 ? "Unsafe lateral movement possible" : "Unsafe lateral movement unlikely");
    return {
      package: pack,
      opinion: `Opinion: ${decision}; ${best.score >= 0.7 ? `primary penalty Vehicle ${label}` : (penalty ? `possible penalty Vehicle ${label}` : "no clear penalty")}. Confidence ${(best.score * 100).toFixed(0)}%. Vehicle ${label} moved laterally toward Vehicle ${other} at ${best.toward.toFixed(2)}m/s.`,
      confidence: best.score,
      penalty_vehicle_id: penalty,
      metrics: common.metricsFromCandidates(candidates),
      series: common.lateralSeries(samples),
    };
  }

  function genericPack(id, label, mode, scoreLabel, extraOpinion) {
    const pack = packageInfo(id, label);
    return function analyze(samples) {
      const analysis = common.analyzeGenericPrimary(
        pack,
        samples,
        mode,
        label,
        scoreLabel,
        common.genericSeriesForMode(mode),
      );
      if (analysis.series.length && extraOpinion) {
        analysis.opinion += ` ${extraOpinion}`;
      }
      return analysis;
    };
  }

  function sharedRacingIncident(samples) {
    const pack = packageInfo("shared_racing_incident", "Shared racing incident");
    if (samples.length < 2) {
      return common.emptyAnalysis(pack, "Opinion: Waiting for enough A/B position history.");
    }
    const a = common.genericCandidate(samples, 1, 2, "shared");
    const b = common.genericCandidate(samples, 2, 1, "shared");
    if (!a || !b) {
      return common.emptyAnalysis(pack, "Opinion: Shared racing incident cannot be evaluated from this log.");
    }
    const average = (a.score + b.score) / 2;
    const delta = Math.abs(a.score - b.score);
    const shared = common.clipScore(average - delta * 0.65);
    const decision = shared >= 0.62 ? "Shared racing incident likely" : (shared >= 0.42 ? "Shared racing incident possible" : "Shared racing incident unlikely");
    return {
      package: pack,
      opinion: `Opinion: ${decision}; ${shared >= 0.42 ? "shared/no primary penalty recommended" : "one-sided responsibility remains possible"}. Confidence ${(shared * 100).toFixed(0)}%. A contribution ${(a.score * 100).toFixed(0)}%, B contribution ${(b.score * 100).toFixed(0)}%.`,
      confidence: shared,
      penalty_vehicle_id: null,
      metrics: { a_contribution: common.round(a.score), b_contribution: common.round(b.score), shared_score: common.round(shared) },
      series: common.sharedSeries(samples),
    };
  }

  const packs = {
    rear_end_collision: { info: packageInfo("rear_end_collision", "Rear-end collision"), analyze: rearEndCollision },
    single_vehicle_collision: { info: packageInfo("single_vehicle_collision", "Single vehicle collision"), analyze: singleVehicleCollision },
    unsafe_lateral_movement: { info: packageInfo("unsafe_lateral_movement", "Unsafe lateral movement"), analyze: unsafeLateralMovement },
    late_braking_divebomb: { info: packageInfo("late_braking_divebomb", "Late braking/divebomb"), analyze: genericPack("late_braking_divebomb", "Late braking/divebomb", "late", "dive score") },
    squeeze_at_corner_exit: { info: packageInfo("squeeze_at_corner_exit", "Squeeze at corner exit"), analyze: genericPack("squeeze_at_corner_exit", "Squeeze at corner exit", "squeeze", "squeeze score") },
    unsafe_rejoin: { info: packageInfo("unsafe_rejoin", "Unsafe rejoin"), analyze: genericPack("unsafe_rejoin", "Unsafe rejoin", "rejoin", "rejoin score", "Track-boundary data is not available, so this is rejoin-like motion only.") },
    shared_racing_incident: { info: packageInfo("shared_racing_incident", "Shared racing incident"), analyze: sharedRacingIncident },
  };

  window.RCTDecisionPacks = {
    VERSION,
    list() {
      return Object.values(packs).map((pack) => pack.info);
    },
    get(id) {
      return packs[id] || null;
    },
    analyze(id, summary) {
      const pack = packs[id];
      if (!pack) {
        throw new Error(`Unknown decision pack: ${id}`);
      }
      return {
        id,
        input_version: VERSION,
        output_version: VERSION,
        ...pack.analyze(common.samplesFromFrames(summary && summary.frames)),
      };
    },
  };
})();
