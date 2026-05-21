(function registerRearEndCollisionDecisionModule() {
  window.RctDecisionModules = window.RctDecisionModules || {};

  function vehicleFramePoint(frame, vehicleId) {
    const vehicles = frame && frame.vehicles;
    const telemetry = vehicles && vehicles[String(vehicleId)];
    const ips = telemetry && telemetry.ips;
    if (!ips || !Number.isFinite(Number(ips.x)) || !Number.isFinite(Number(ips.y))) {
      return null;
    }
    return {
      x: Number(ips.x),
      y: Number(ips.y),
      speed: Number.isFinite(Number(telemetry.speed)) ? Number(telemetry.speed) : null,
      headingYaw: Number.isFinite(Number(telemetry.heading_yaw)) ? Number(telemetry.heading_yaw) : null,
      linearVelocity: telemetry.linear_velocity || null,
    };
  }

  function velocityFromFrame(samples, index, vehicleId) {
    const sample = samples[index];
    const point = sample && sample.vehicles[vehicleId];
    if (!point) {
      return null;
    }
    if (
      point.linearVelocity
      && Number.isFinite(Number(point.linearVelocity.x))
      && Number.isFinite(Number(point.linearVelocity.y))
    ) {
      return { x: Number(point.linearVelocity.x), y: Number(point.linearVelocity.y) };
    }

    let previousSample = null;
    let previousPoint = null;
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const candidate = samples[cursor];
      const candidatePoint = candidate && candidate.vehicles[vehicleId];
      if (candidatePoint) {
        previousSample = candidate;
        previousPoint = candidatePoint;
        break;
      }
    }
    if (!previousSample || !previousPoint) {
      return null;
    }
    const dt = sample.time - previousSample.time;
    if (!Number.isFinite(dt) || dt <= 0.001) {
      return null;
    }
    return {
      x: (point.x - previousPoint.x) / dt,
      y: (point.y - previousPoint.y) / dt,
    };
  }

  function speedFromVelocity(velocity) {
    return velocity ? Math.hypot(velocity.x, velocity.y) : null;
  }

  function headingFromSample(point, velocity) {
    if (Number.isFinite(point.headingYaw)) {
      return point.headingYaw;
    }
    if (velocity && Math.hypot(velocity.x, velocity.y) > 0.05) {
      return Math.atan2(velocity.y, velocity.x);
    }
    return null;
  }

  function rearEndSamplesFromFrames(frames) {
    const samples = [];
    for (const frame of frames) {
      const vehicleA = vehicleFramePoint(frame, 1);
      const vehicleB = vehicleFramePoint(frame, 2);
      if (!vehicleA || !vehicleB) {
        continue;
      }
      const time = Number(frame.time_to_accident_seconds);
      samples.push({
        time: Number.isFinite(time) ? time : samples.length,
        vehicles: {
          1: vehicleA,
          2: vehicleB,
        },
      });
    }
    for (let index = 0; index < samples.length; index += 1) {
      for (const vehicleId of [1, 2]) {
        const point = samples[index].vehicles[vehicleId];
        const velocity = velocityFromFrame(samples, index, vehicleId);
        point.velocity = velocity;
        point.calculatedSpeed = point.speed !== null ? point.speed : speedFromVelocity(velocity);
        point.headingYaw = headingFromSample(point, velocity);
      }
    }
    return samples;
  }

  function rearEndCandidate(samples, attackerId, targetId) {
    if (samples.length < 2) {
      return null;
    }
    const last = samples[samples.length - 1];
    const attacker = last.vehicles[attackerId];
    const target = last.vehicles[targetId];
    if (!attacker || !target || !Number.isFinite(attacker.headingYaw)) {
      return null;
    }

    const forward = { x: Math.cos(attacker.headingYaw), y: Math.sin(attacker.headingYaw) };
    const right = { x: -forward.y, y: forward.x };
    const dx = target.x - attacker.x;
    const dy = target.y - attacker.y;
    const longitudinal = dx * forward.x + dy * forward.y;
    const lateral = Math.abs(dx * right.x + dy * right.y);
    const distance = Math.hypot(dx, dy);
    const attackerVelocity = attacker.velocity;
    const targetVelocity = target.velocity;
    const relativeVelocity = attackerVelocity && targetVelocity
      ? { x: attackerVelocity.x - targetVelocity.x, y: attackerVelocity.y - targetVelocity.y }
      : null;
    const closingSpeed = relativeVelocity
      ? relativeVelocity.x * forward.x + relativeVelocity.y * forward.y
      : (
          Number.isFinite(attacker.calculatedSpeed) && Number.isFinite(target.calculatedSpeed)
            ? attacker.calculatedSpeed - target.calculatedSpeed
            : null
        );
    const first = samples.find((sample) => sample.time >= last.time - 2.0) || samples[0];
    const firstAttacker = first.vehicles[attackerId];
    const firstTarget = first.vehicles[targetId];
    const firstDistance = firstAttacker && firstTarget
      ? Math.hypot(firstTarget.x - firstAttacker.x, firstTarget.y - firstAttacker.y)
      : distance;
    const approach = firstDistance - distance;

    let score = 0;
    if (longitudinal > 0.15) {
      score += 0.34;
    }
    if (lateral <= 1.2) {
      score += 0.2;
    } else if (lateral <= 1.8) {
      score += 0.1;
    }
    if (Number.isFinite(closingSpeed) && closingSpeed > 0.2) {
      score += 0.25;
    } else if (Number.isFinite(closingSpeed) && closingSpeed > 0.05) {
      score += 0.12;
    }
    if (approach > 0.25) {
      score += 0.14;
    } else if (approach > 0.05) {
      score += 0.07;
    }
    if (distance <= 2.0) {
      score += 0.07;
    }

    return {
      attackerId,
      targetId,
      score: Math.min(1, score),
      longitudinal,
      lateral,
      distance,
      closingSpeed,
      approach,
    };
  }

  function rearEndScoreLabel(candidates, attackerId, formatNumber) {
    const candidate = candidates.find((item) => item.attackerId === attackerId);
    return candidate ? `${formatNumber(candidate.score * 100, 0)}%` : "-";
  }

  function analyzeRearEndCollision(frames, context) {
    const { displayRoboracerLabel, formatNumber } = context;
    const samples = rearEndSamplesFromFrames(frames);
    if (samples.length < 2) {
      return {
        samples,
        opinion: "Opinion: Waiting for enough A/B position history.",
        metrics: [],
      };
    }

    const candidates = [
      rearEndCandidate(samples, 1, 2),
      rearEndCandidate(samples, 2, 1),
    ].filter(Boolean).sort((left, right) => right.score - left.score);
    const best = candidates[0];
    const runnerUp = candidates[1];
    if (!best) {
      return {
        samples,
        opinion: "Opinion: Rear-end collision cannot be evaluated from this log.",
        metrics: [],
      };
    }

    const attackerLabel = displayRoboracerLabel(best.attackerId);
    const targetLabel = displayRoboracerLabel(best.targetId);
    const confidence = Math.round(best.score * 100);
    let decision = "Rear-end unlikely";
    let penalty = "no clear penalty";
    if (best.score >= 0.7 && (!runnerUp || best.score - runnerUp.score >= 0.15)) {
      decision = "Rear-end likely";
      penalty = `primary penalty Vehicle ${attackerLabel}`;
    } else if (best.score >= 0.5) {
      decision = "Rear-end possible";
      penalty = runnerUp && best.score - runnerUp.score < 0.15
        ? "shared/uncertain responsibility"
        : `possible penalty Vehicle ${attackerLabel}`;
    }

    const reasonParts = [
      `Vehicle ${attackerLabel} was ${formatNumber(Math.max(0, best.longitudinal), 2)}m behind Vehicle ${targetLabel}`,
      `lateral gap ${formatNumber(best.lateral, 2)}m`,
    ];
    if (Number.isFinite(best.closingSpeed)) {
      reasonParts.push(`closing ${formatNumber(best.closingSpeed, 2)}m/s`);
    }

    return {
      samples,
      candidate: best,
      opinion: `Opinion: ${decision}; ${penalty}. Confidence ${confidence}%. ${reasonParts.join(", ")}.`,
      metrics: [
        `A->B score ${rearEndScoreLabel(candidates, 1, formatNumber)}`,
        `B->A score ${rearEndScoreLabel(candidates, 2, formatNumber)}`,
        `Final gap ${formatNumber(best.distance, 2)}m`,
        `Approach ${formatNumber(best.approach, 2)}m`,
      ],
    };
  }

  function drawRearEndAnalysisChart(canvas, analysis, context) {
    const { formatNumber } = context;
    const drawingContext = canvas.getContext("2d");
    const rect = canvas.getBoundingClientRect();
    const pixelRatio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(rect.width * pixelRatio));
    const height = Math.max(1, Math.round(rect.height * pixelRatio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    drawingContext.clearRect(0, 0, width, height);
    drawingContext.fillStyle = "#ffffff";
    drawingContext.fillRect(0, 0, width, height);

    const samples = analysis.samples || [];
    const padding = { left: 42 * pixelRatio, right: 12 * pixelRatio, top: 18 * pixelRatio, bottom: 30 * pixelRatio };
    const plotWidth = Math.max(1, width - padding.left - padding.right);
    const plotHeight = Math.max(1, height - padding.top - padding.bottom);
    drawingContext.strokeStyle = "#dee2e6";
    drawingContext.lineWidth = pixelRatio;
    drawingContext.strokeRect(padding.left, padding.top, plotWidth, plotHeight);

    if (samples.length < 2) {
      drawingContext.fillStyle = "#6c757d";
      drawingContext.font = `${12 * pixelRatio}px system-ui, sans-serif`;
      drawingContext.textAlign = "center";
      drawingContext.fillText("No chart data", width / 2, height / 2);
      return;
    }

    const firstTime = samples[0].time;
    const lastTime = samples[samples.length - 1].time;
    const rows = samples.map((sample, index) => {
      const vehicleA = sample.vehicles[1];
      const vehicleB = sample.vehicles[2];
      const candidateA = rearEndCandidate(samples.slice(0, index + 1), 1, 2);
      return {
        time: sample.time,
        distance: Math.hypot(vehicleB.x - vehicleA.x, vehicleB.y - vehicleA.y),
        speedA: Number.isFinite(vehicleA.calculatedSpeed) ? vehicleA.calculatedSpeed : null,
        speedB: Number.isFinite(vehicleB.calculatedSpeed) ? vehicleB.calculatedSpeed : null,
        closing: candidateA && Number.isFinite(candidateA.closingSpeed) ? candidateA.closingSpeed : null,
      };
    });
    const values = rows.flatMap((row) => [row.distance, row.speedA, row.speedB, row.closing])
      .filter((value) => Number.isFinite(value));
    const minValue = Math.min(0, ...values);
    const maxValue = Math.max(1, ...values);
    const valueRange = Math.max(1, maxValue - minValue);
    const xForTime = (time) => padding.left + ((time - firstTime) / Math.max(0.001, lastTime - firstTime)) * plotWidth;
    const yForValue = (value) => padding.top + plotHeight - ((value - minValue) / valueRange) * plotHeight;

    drawingContext.fillStyle = "#6c757d";
    drawingContext.font = `${11 * pixelRatio}px system-ui, sans-serif`;
    drawingContext.textAlign = "left";
    drawingContext.fillText(`${formatNumber(maxValue, 1)}`, 6 * pixelRatio, padding.top + 4 * pixelRatio);
    drawingContext.fillText(`${formatNumber(minValue, 1)}`, 6 * pixelRatio, padding.top + plotHeight);
    drawingContext.textAlign = "center";
    drawingContext.fillText("time to collision", padding.left + plotWidth / 2, height - 8 * pixelRatio);

    const drawSeries = (key, color, dash = []) => {
      drawingContext.beginPath();
      drawingContext.strokeStyle = color;
      drawingContext.lineWidth = 2 * pixelRatio;
      drawingContext.setLineDash(dash.map((item) => item * pixelRatio));
      let started = false;
      for (const row of rows) {
        const value = row[key];
        if (!Number.isFinite(value)) {
          continue;
        }
        const x = xForTime(row.time);
        const y = yForValue(value);
        if (!started) {
          drawingContext.moveTo(x, y);
          started = true;
        } else {
          drawingContext.lineTo(x, y);
        }
      }
      drawingContext.stroke();
      drawingContext.setLineDash([]);
    };

    drawSeries("distance", "#0d6efd");
    drawSeries("speedA", "#dc3545");
    drawSeries("speedB", "#198754");
    drawSeries("closing", "#6f42c1", [4, 3]);

    const legend = [
      ["A-B distance", "#0d6efd"],
      ["A speed", "#dc3545"],
      ["B speed", "#198754"],
      ["A closing", "#6f42c1"],
    ];
    let legendX = padding.left;
    const legendY = 11 * pixelRatio;
    drawingContext.textAlign = "left";
    for (const [label, color] of legend) {
      drawingContext.fillStyle = color;
      drawingContext.fillRect(legendX, legendY - 7 * pixelRatio, 8 * pixelRatio, 3 * pixelRatio);
      drawingContext.fillStyle = "#495057";
      drawingContext.fillText(label, legendX + 12 * pixelRatio, legendY);
      legendX += (label.length * 6 + 28) * pixelRatio;
    }
  }

  window.RctDecisionModules["rear-end-collision"] = {
    mount(root, context) {
      const chart = root.querySelector(".rct-rear-end-chart");
      const metrics = root.querySelector(".rct-rear-end-metrics");
      let currentFrames = Array.isArray(context.initialFrames) ? context.initialFrames : [];
      const render = (frames) => {
        currentFrames = Array.isArray(frames) ? frames : [];
        const analysis = analyzeRearEndCollision(currentFrames, context);
        context.setOpinion(analysis.opinion);
        metrics.innerHTML = "";
        for (const metric of analysis.metrics) {
          const item = document.createElement("span");
          item.textContent = metric;
          metrics.append(item);
        }
        drawRearEndAnalysisChart(chart, analysis, context);
      };
      if ("ResizeObserver" in window) {
        new ResizeObserver(() => render(currentFrames)).observe(chart);
      }
      return render;
    },
  };
}());
