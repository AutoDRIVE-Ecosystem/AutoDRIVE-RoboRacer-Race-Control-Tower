(function registerLateBrakingDivebombDecisionModule() {
  window.RctDecisionModules = window.RctDecisionModules || {};

  function point(frame, vehicleId) {
    const telemetry = frame && frame.vehicles && frame.vehicles[String(vehicleId)];
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

  function samplesFromFrames(frames) {
    const samples = [];
    for (const frame of frames) {
      const a = point(frame, 1);
      const b = point(frame, 2);
      if (!a || !b) {
        continue;
      }
      const time = Number(frame.time_to_accident_seconds);
      samples.push({ time: Number.isFinite(time) ? time : samples.length, vehicles: { 1: a, 2: b } });
    }
    for (let index = 0; index < samples.length; index += 1) {
      for (const vehicleId of [1, 2]) {
        const current = samples[index].vehicles[vehicleId];
        current.velocity = velocityAt(samples, index, vehicleId);
        current.calculatedSpeed = current.speed !== null ? current.speed : length(current.velocity);
        if (!Number.isFinite(current.headingYaw) && current.velocity && length(current.velocity) > 0.05) {
          current.headingYaw = Math.atan2(current.velocity.y, current.velocity.x);
        }
      }
    }
    return samples;
  }

  function velocityAt(samples, index, vehicleId) {
    const current = samples[index] && samples[index].vehicles[vehicleId];
    if (!current) {
      return null;
    }
    if (
      current.linearVelocity
      && Number.isFinite(Number(current.linearVelocity.x))
      && Number.isFinite(Number(current.linearVelocity.y))
    ) {
      return { x: Number(current.linearVelocity.x), y: Number(current.linearVelocity.y) };
    }
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const previous = samples[cursor] && samples[cursor].vehicles[vehicleId];
      const dt = samples[index].time - samples[cursor].time;
      if (previous && Number.isFinite(dt) && dt > 0.001) {
        return { x: (current.x - previous.x) / dt, y: (current.y - previous.y) / dt };
      }
    }
    return null;
  }

  function length(vector) {
    return vector ? Math.hypot(vector.x, vector.y) : 0;
  }

  function distance(left, right) {
    return Math.hypot(right.x - left.x, right.y - left.y);
  }

  function basis(vehicle, target) {
    let heading = vehicle.headingYaw;
    if (!Number.isFinite(heading) && vehicle.velocity && length(vehicle.velocity) > 0.05) {
      heading = Math.atan2(vehicle.velocity.y, vehicle.velocity.x);
    }
    if (!Number.isFinite(heading)) {
      heading = Math.atan2(target.y - vehicle.y, target.x - vehicle.x);
    }
    const forward = { x: Math.cos(heading), y: Math.sin(heading) };
    return { forward, right: { x: -forward.y, y: forward.x } };
  }

  function brakingDelta(samples, vehicleId) {
    if (samples.length < 2) {
      return 0;
    }
    const last = samples[samples.length - 1].vehicles[vehicleId];
    const first = samples.find((sample) => sample.time >= samples[samples.length - 1].time - 1.5) || samples[0];
    const firstSpeed = Number(first.vehicles[vehicleId].calculatedSpeed);
    const lastSpeed = Number(last.calculatedSpeed);
    if (!Number.isFinite(firstSpeed) || !Number.isFinite(lastSpeed)) {
      return 0;
    }
    return firstSpeed - lastSpeed;
  }

  function candidate(samples, attackerId, defenderId) {
    if (samples.length < 3) {
      return null;
    }
    const last = samples[samples.length - 1];
    const attacker = last.vehicles[attackerId];
    const defender = last.vehicles[defenderId];
    const attackerBasis = basis(attacker, defender);
    const dx = defender.x - attacker.x;
    const dy = defender.y - attacker.y;
    const longitudinal = dx * attackerBasis.forward.x + dy * attackerBasis.forward.y;
    const lateral = Math.abs(dx * attackerBasis.right.x + dy * attackerBasis.right.y);
    const finalDistance = distance(attacker, defender);
    const attackerVelocity = attacker.velocity || { x: 0, y: 0 };
    const defenderVelocity = defender.velocity || { x: 0, y: 0 };
    const relativeVelocity = { x: attackerVelocity.x - defenderVelocity.x, y: attackerVelocity.y - defenderVelocity.y };
    const closing = relativeVelocity.x * attackerBasis.forward.x + relativeVelocity.y * attackerBasis.forward.y;
    const first = samples.find((sample) => sample.time >= last.time - 1.5) || samples[0];
    const approach = distance(first.vehicles[attackerId], first.vehicles[defenderId]) - finalDistance;
    const attackerBrake = brakingDelta(samples, attackerId);
    const defenderBrake = brakingDelta(samples, defenderId);
    const lateSpeedAdvantage = Number(attacker.calculatedSpeed) - Number(defender.calculatedSpeed);

    let score = 0;
    if (longitudinal > -0.6 && longitudinal < 3.0) {
      score += 0.18;
    }
    if (lateral < 1.2) {
      score += 0.18;
    } else if (lateral < 1.8) {
      score += 0.09;
    }
    if (closing > 0.35) {
      score += 0.28;
    } else if (closing > 0.12) {
      score += 0.14;
    }
    if (approach > 0.7) {
      score += 0.2;
    } else if (approach > 0.25) {
      score += 0.1;
    }
    if (attackerBrake < defenderBrake - 0.15 || lateSpeedAdvantage > 0.25) {
      score += 0.16;
    }

    return {
      attackerId,
      defenderId,
      score: Math.min(1, score),
      longitudinal,
      lateral,
      finalDistance,
      closing,
      approach,
      attackerBrake,
      defenderBrake,
      lateSpeedAdvantage,
    };
  }

  function scoreLabel(candidates, attackerId, formatNumber) {
    const item = candidates.find((candidateItem) => candidateItem.attackerId === attackerId);
    return item ? `${formatNumber(item.score * 100, 0)}%` : "-";
  }

  function analyze(frames, context) {
    const { displayRoboracerLabel, formatNumber } = context;
    const samples = samplesFromFrames(frames);
    if (samples.length < 3) {
      return { rows: [], opinion: "Opinion: Waiting for enough A/B position history.", metrics: [] };
    }
    const candidates = [
      candidate(samples, 1, 2),
      candidate(samples, 2, 1),
    ].filter(Boolean).sort((left, right) => right.score - left.score);
    const best = candidates[0];
    if (!best) {
      return { rows: [], opinion: "Opinion: Late braking/divebomb cannot be evaluated from this log.", metrics: [] };
    }
    const attackerLabel = displayRoboracerLabel(best.attackerId);
    const defenderLabel = displayRoboracerLabel(best.defenderId);
    let decision = "Late braking/divebomb unlikely";
    let penalty = "no clear penalty";
    if (best.score >= 0.7) {
      decision = "Late braking/divebomb likely";
      penalty = `primary penalty Vehicle ${attackerLabel}`;
    } else if (best.score >= 0.5) {
      decision = "Late braking/divebomb possible";
      penalty = `possible penalty Vehicle ${attackerLabel}`;
    }

    const rows = samples.map((sample, index) => {
      const partial = samples.slice(0, index + 1);
      const a = partial.length >= 3 ? candidate(partial, 1, 2) : null;
      const b = partial.length >= 3 ? candidate(partial, 2, 1) : null;
      return {
        time: sample.time,
        distance: distance(sample.vehicles[1], sample.vehicles[2]),
        aClosing: a ? a.closing : null,
        bClosing: b ? b.closing : null,
        aScore: a ? a.score * 100 : null,
        bScore: b ? b.score * 100 : null,
      };
    });

    return {
      rows,
      opinion: `Opinion: ${decision}; ${penalty}. Confidence ${Math.round(best.score * 100)}%. Vehicle ${attackerLabel} closed on Vehicle ${defenderLabel} at ${formatNumber(best.closing, 2)}m/s with ${formatNumber(best.approach, 2)}m late approach.`,
      metrics: [
        `A dive score ${scoreLabel(candidates, 1, formatNumber)}`,
        `B dive score ${scoreLabel(candidates, 2, formatNumber)}`,
        `Final gap ${formatNumber(best.finalDistance, 2)}m`,
        `Brake delta A/B ${formatNumber(best.attackerBrake, 2)}/${formatNumber(best.defenderBrake, 2)}m/s`,
      ],
    };
  }

  function draw(canvas, analysis, context) {
    drawSeriesChart(canvas, analysis.rows, context, [
      { key: "aClosing", label: "A closing", color: "#dc3545" },
      { key: "bClosing", label: "B closing", color: "#198754" },
      { key: "distance", label: "distance", color: "#0d6efd" },
      { key: "aScore", label: "A score", color: "#6f42c1", dash: [4, 3] },
    ]);
  }

  function drawSeriesChart(canvas, rows, context, series) {
    const { formatNumber } = context;
    const ctx = canvas.getContext("2d");
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(rect.width * ratio));
    const height = Math.max(1, Math.round(rect.height * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    const pad = { left: 42 * ratio, right: 12 * ratio, top: 18 * ratio, bottom: 30 * ratio };
    const plotWidth = Math.max(1, width - pad.left - pad.right);
    const plotHeight = Math.max(1, height - pad.top - pad.bottom);
    ctx.strokeStyle = "#dee2e6";
    ctx.lineWidth = ratio;
    ctx.strokeRect(pad.left, pad.top, plotWidth, plotHeight);
    if (!rows || rows.length < 2) {
      ctx.fillStyle = "#6c757d";
      ctx.font = `${12 * ratio}px system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText("No chart data", width / 2, height / 2);
      return;
    }
    const values = rows.flatMap((row) => series.map((item) => row[item.key])).filter((value) => Number.isFinite(value));
    const minValue = Math.min(0, ...values);
    const maxValue = Math.max(1, ...values);
    const range = Math.max(1, maxValue - minValue);
    const firstTime = rows[0].time;
    const lastTime = rows[rows.length - 1].time;
    const xForTime = (time) => pad.left + ((time - firstTime) / Math.max(0.001, lastTime - firstTime)) * plotWidth;
    const yForValue = (value) => pad.top + plotHeight - ((value - minValue) / range) * plotHeight;
    ctx.fillStyle = "#6c757d";
    ctx.font = `${11 * ratio}px system-ui, sans-serif`;
    ctx.textAlign = "left";
    ctx.fillText(formatNumber(maxValue, 1), 6 * ratio, pad.top + 4 * ratio);
    ctx.fillText(formatNumber(minValue, 1), 6 * ratio, pad.top + plotHeight);
    ctx.textAlign = "center";
    ctx.fillText("time to collision", pad.left + plotWidth / 2, height - 8 * ratio);
    for (const item of series) {
      ctx.beginPath();
      ctx.strokeStyle = item.color;
      ctx.lineWidth = 2 * ratio;
      ctx.setLineDash((item.dash || []).map((value) => value * ratio));
      let started = false;
      for (const row of rows) {
        const value = row[item.key];
        if (!Number.isFinite(value)) {
          continue;
        }
        const x = xForTime(row.time);
        const y = yForValue(value);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }
    let legendX = pad.left;
    const legendY = 11 * ratio;
    ctx.textAlign = "left";
    for (const item of series) {
      ctx.fillStyle = item.color;
      ctx.fillRect(legendX, legendY - 7 * ratio, 8 * ratio, 3 * ratio);
      ctx.fillStyle = "#495057";
      ctx.fillText(item.label, legendX + 12 * ratio, legendY);
      legendX += (item.label.length * 6 + 28) * ratio;
    }
  }

  window.RctDecisionModules["late-braking-divebomb"] = {
    mount(root, context) {
      const chart = root.querySelector(".rct-late-braking-chart");
      const metrics = root.querySelector(".rct-late-braking-metrics");
      let currentFrames = Array.isArray(context.initialFrames) ? context.initialFrames : [];
      const render = (frames) => {
        currentFrames = Array.isArray(frames) ? frames : [];
        const analysis = analyze(currentFrames, context);
        context.setOpinion(analysis.opinion);
        metrics.innerHTML = "";
        for (const metric of analysis.metrics) {
          const item = document.createElement("span");
          item.textContent = metric;
          metrics.append(item);
        }
        draw(chart, analysis, context);
      };
      if ("ResizeObserver" in window) {
        new ResizeObserver(() => render(currentFrames)).observe(chart);
      }
      return render;
    },
  };
}());
