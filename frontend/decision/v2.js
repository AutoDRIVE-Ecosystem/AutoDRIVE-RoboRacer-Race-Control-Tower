// SPDX-License-Identifier: BSD-3-Clause

(function () {
  "use strict";

  const common = window.RCTDecisionCommon;
  const VERSION = common.VERSION;

  function pluginInfo(id, label) {
    return { id, label, input_version: VERSION, output_version: VERSION };
  }

  function graphInfo(id, label) {
    return { id, label, input_version: VERSION, output_version: VERSION };
  }

  function buildContext(summary) {
    const samples = common.samplesFromFrames(summary && summary.frames);
    return {
      summary,
      samples,
      common,
      vehicles: [1, 2],
    };
  }

  function emptyGraph(info, opinion) {
    return {
      graph: info,
      opinion,
      metrics: {},
      series: [],
    };
  }

  function graphG01(context) {
    const info = graphInfo("G01", "A/B distance and collision count");
    const samples = context.samples;
    if (samples.length < 2) {
      return emptyGraph(info, "Graph G01 waiting for A/B telemetry history.");
    }
    const previous = {};
    const series = samples.map((sample) => {
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
    const distances = series.map((row) => row.ab_distance).filter(Number.isFinite);
    const minDistance = distances.length ? Math.min(...distances) : null;
    const collisionDeltas = series.reduce((total, row) => total + row.a_collision_delta + row.b_collision_delta, 0);
    return {
      graph: info,
      opinion: "Graph G01 tracks separation and collision-count transitions for single/two-car incident checks.",
      metrics: {
        min_ab_distance_m: common.round(minDistance),
        collision_delta_count: collisionDeltas,
      },
      series,
    };
  }

  function graphG02(context) {
    const info = graphInfo("G02", "Closing speed and lateral pressure");
    const samples = context.samples;
    if (samples.length < 2) {
      return emptyGraph(info, "Graph G02 waiting for enough motion history.");
    }
    const series = samples.map((sample, index) => {
      const partial = samples.slice(0, index + 1);
      const rearA = partial.length >= 2 ? common.rearEndCandidate(partial, 1, 2) : null;
      const rearB = partial.length >= 2 ? common.rearEndCandidate(partial, 2, 1) : null;
      const lateralA = partial.length >= 2 ? common.lateralCandidate(partial, 1, 2) : null;
      const lateralB = partial.length >= 2 ? common.lateralCandidate(partial, 2, 1) : null;
      return {
        time: sample.time,
        a_closing: rearA ? rearA.closing : null,
        b_closing: rearB ? rearB.closing : null,
        a_lateral_toward: lateralA ? lateralA.toward : null,
        b_lateral_toward: lateralB ? lateralB.toward : null,
      };
    });
    const last = series[series.length - 1] || {};
    return {
      graph: info,
      opinion: "Graph G02 separates longitudinal closing behavior from lateral pressure indicators.",
      metrics: {
        final_a_closing_mps: common.round(last.a_closing),
        final_b_closing_mps: common.round(last.b_closing),
        final_a_lateral_toward_mps: common.round(last.a_lateral_toward),
        final_b_lateral_toward_mps: common.round(last.b_lateral_toward),
      },
      series,
    };
  }

  function graphMapFromResults(graphResults) {
    return Object.fromEntries(graphResults.map((result) => [result.graph.id, result]));
  }

  function collisionTypeCT1(context, graphResults) {
    const info = pluginInfo("CT1", "Single-vehicle wall collision");
    const graphMap = graphMapFromResults(graphResults);
    const g01 = graphMap.G01;
    if (!g01 || context.samples.length < 2) {
      return emptyCollisionType(info, "No decision", "Opinion: CT1 requires G01 and enough A/B telemetry history.", graphResults);
    }
    const changedVehicles = new Set();
    for (const row of g01.series) {
      if (row.a_collision_delta > 0) {
        changedVehicles.add(1);
      }
      if (row.b_collision_delta > 0) {
        changedVehicles.add(2);
      }
    }
    const minDistance = Number(g01.metrics.min_ab_distance_m);
    const singleVehicleId = changedVehicles.size === 1 ? Array.from(changedVehicles)[0] : null;
    let faultPercentage = 0;
    let decision = "No decision";
    let penaltyVehicleId = null;
    let opinionDetail = "no isolated collision-count increase was found";
    if (singleVehicleId !== null && Number.isFinite(minDistance) && minDistance > 2.0) {
      faultPercentage = 92;
      decision = "CT1 likely";
      penaltyVehicleId = singleVehicleId;
      opinionDetail = `Vehicle ${common.vehicleLabel(singleVehicleId)} has the isolated collision-count increase and A/B distance stayed above ${minDistance.toFixed(2)}m`;
    } else if (singleVehicleId !== null) {
      faultPercentage = 62;
      decision = "CT1 possible";
      penaltyVehicleId = singleVehicleId;
      opinionDetail = `Vehicle ${common.vehicleLabel(singleVehicleId)} has the isolated collision-count increase, but opponent proximity is not excluded`;
    } else if (changedVehicles.size >= 2) {
      faultPercentage = 8;
      decision = "CT1 unlikely";
      opinionDetail = "both vehicles recorded collision-count increases";
    }
    return {
      package: info,
      decision,
      fault_percentage: faultPercentage,
      opinion: `Opinion: ${decision}; ${penaltyVehicleId ? `fault Vehicle ${common.vehicleLabel(penaltyVehicleId)}` : "no CT1 fault"}. Fault percentage ${faultPercentage.toFixed(0)}%. ${opinionDetail}.`,
      confidence: faultPercentage / 100,
      penalty_vehicle_id: penaltyVehicleId,
      metrics: {
        ct_id: info.id,
        required_graphs: "G01",
        min_ab_distance_m: g01.metrics.min_ab_distance_m,
        changed_vehicles: Array.from(changedVehicles).map(common.vehicleLabel).join(",") || "none",
      },
      graphs: graphResults,
      series: g01.series,
    };
  }

  function emptyCollisionType(info, decision, opinion, graphResults) {
    return {
      package: info,
      decision,
      fault_percentage: 0,
      opinion,
      confidence: 0,
      penalty_vehicle_id: null,
      metrics: {},
      graphs: graphResults,
      series: [],
    };
  }

  const graphs = {
    G01: { info: graphInfo("G01", "A/B distance and collision count"), analyze: graphG01 },
    G02: { info: graphInfo("G02", "Closing speed and lateral pressure"), analyze: graphG02 },
  };

  const collisionTypes = {
    CT1: {
      info: pluginInfo("CT1", "Single-vehicle wall collision"),
      graph_ids: ["G01"],
      analyze: collisionTypeCT1,
    },
  };

  function enabledGraphIdsForCollisionType(collisionType, enabledGraphs) {
    return collisionType.graph_ids.filter((id) => enabledGraphs[id] !== false);
  }

  window.RCTDecisionPacksV2 = {
    VERSION,
    listGraphs() {
      return Object.values(graphs).map((graph) => graph.info);
    },
    listCollisionTypes() {
      return Object.values(collisionTypes).map((collisionType) => collisionType.info);
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
