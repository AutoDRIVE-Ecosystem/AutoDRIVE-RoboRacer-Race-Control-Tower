(function registerUnsafeLateralMovementDecisionModule() {
  window.RctDecisionModules = window.RctDecisionModules || {};

  function pointFromFrame(frame, vehicleId) {
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

  function sampleFrames(frames) {
    const samples = [];
    for (const frame of frames) {
      const vehicleA = pointFromFrame(frame, 1);
      const vehicleB = pointFromFrame(frame, 2);
      if (!vehicleA || !vehicleB) {
        continue;
      }
      const time = Number(frame.time_to_accident_seconds);
      samples.push({
        time: Number.isFinite(time) ? time : samples.length,
        vehicles: { 1: vehicleA, 2: vehicleB },
      });
    }

    for (let index = 0; index < samples.length; index += 1) {
      for (const vehicleId of [1, 2]) {
        const point = samples[index].vehicles[vehicleId];
        point.velocity = velocityAt(samples, index, vehicleId);
        if (!Number.isFinite(point.headingYaw) && point.velocity && speed(point.velocity) > 0.05) {
          point.headingYaw = Math.atan2(point.velocity.y, point.velocity.x);
        }
      }
    }
    return samples;
  }

  function velocityAt(samples, index, vehicleId) {
    const point = samples[index] && samples[index].vehicles[vehicleId];
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
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const previous = samples[cursor] && samples[cursor].vehicles[vehicleId];
      if (!previous) {
        continue;
      }
      const dt = samples[index].time - samples[cursor].time;
      if (Number.isFinite(dt) && dt > 0.001) {
        return { x: (point.x - previous.x) / dt, y: (point.y - previous.y) / dt };
      }
    }
    return null;
  }

  function speed(vector) {
    return vector ? Math.hypot(vector.x, vector.y) : 0;
  }

  function sideBasis(point, fallbackTarget) {
    let heading = point.headingYaw;
    if (!Number.isFinite(heading) && point.velocity && speed(point.velocity) > 0.05) {
      heading = Math.atan2(point.velocity.y, point.velocity.x);
    }
    if (!Number.isFinite(heading)) {
      heading = Math.atan2(fallbackTarget.y - point.y, fallbackTarget.x - point.x);
    }
    const forward = { x: Math.cos(heading), y: Math.sin(heading) };
    return {
      forward,
      right: { x: -forward.y, y: forward.x },
    };
  }

  function lateralCandidate(samples, moverId, otherId) {
    if (samples.length < 2) {
      return null;
    }
    const last = samples[samples.length - 1];
    const mover = last.vehicles[moverId];
    const other = last.vehicles[otherId];
    const basis = sideBasis(mover, other);
    const dx = other.x - mover.x;
    const dy = other.y - mover.y;
    const lateral = dx * basis.right.x + dy * basis.right.y;
    const lateralGap = Math.abs(lateral);
    const longitudinalGap = Math.abs(dx * basis.forward.x + dy * basis.forward.y);
    const moverVelocity = mover.velocity || { x: 0, y: 0 };
    const lateralVelocity = moverVelocity.x * basis.right.x + moverVelocity.y * basis.right.y;
    const towardOtherVelocity = lateral === 0 ? 0 : lateralVelocity * Math.sign(lateral);
    const first = samples.find((sample) => sample.time >= last.time - 2.0) || samples[0];
    const firstMover = first.vehicles[moverId];
    const firstOther = first.vehicles[otherId];
    const firstBasis = sideBasis(firstMover, firstOther);
    const firstLateralGap = Math.abs((firstOther.x - firstMover.x) * firstBasis.right.x + (firstOther.y - firstMover.y) * firstBasis.right.y);
    const gapClosed = firstLateralGap - lateralGap;

    let score = 0;
    if (towardOtherVelocity > 0.25) {
      score += 0.34;
    } else if (towardOtherVelocity > 0.08) {
      score += 0.16;
    }
    if (gapClosed > 0.5) {
      score += 0.28;
    } else if (gapClosed > 0.15) {
      score += 0.12;
    }
    if (lateralGap < 1.0) {
      score += 0.22;
    } else if (lateralGap < 1.6) {
      score += 0.12;
    }
    if (longitudinalGap < 2.0) {
      score += 0.16;
    }

    return {
      moverId,
      otherId,
      score: Math.min(1, score),
      lateralGap,
      longitudinalGap,
      towardOtherVelocity,
      gapClosed,
    };
  }

  function scoreLabel(candidates, moverId, formatNumber) {
    const candidate = candidates.find((item) => item.moverId === moverId);
    return candidate ? `${formatNumber(candidate.score * 100, 0)}%` : "-";
  }

  function analyze(frames, context) {
    const { displayRoboracerLabel, formatNumber } = context;
    const samples = sampleFrames(frames);
    if (samples.length < 2) {
      return { samples, rows: [], opinion: "Opinion: Waiting for enough A/B position history.", metrics: [] };
    }

    const candidates = [
      lateralCandidate(samples, 1, 2),
      lateralCandidate(samples, 2, 1),
    ].filter(Boolean).sort((left, right) => right.score - left.score);
    const best = candidates[0];
    if (!best) {
      return { samples, rows: [], opinion: "Opinion: Unsafe lateral movement cannot be evaluated from this log.", metrics: [] };
    }

    const moverLabel = displayRoboracerLabel(best.moverId);
    const otherLabel = displayRoboracerLabel(best.otherId);
    let decision = "Unsafe lateral movement unlikely";
    let penalty = "no clear penalty";
    if (best.score >= 0.7) {
      decision = "Unsafe lateral movement likely";
      penalty = `primary penalty Vehicle ${moverLabel}`;
    } else if (best.score >= 0.5) {
      decision = "Unsafe lateral movement possible";
      penalty = `possible penalty Vehicle ${moverLabel}`;
    }

    const rows = samples.map((sample, index) => {
      const partial = samples.slice(0, index + 1);
      const a = lateralCandidate(partial, 1, 2);
      const b = lateralCandidate(partial, 2, 1);
      const vehicleA = sample.vehicles[1];
      const vehicleB = sample.vehicles[2];
      return {
        time: sample.time,
        distance: Math.hypot(vehicleB.x - vehicleA.x, vehicleB.y - vehicleA.y),
        lateralGap: a ? a.lateralGap : null,
        aToward: a ? a.towardOtherVelocity : null,
        bToward: b ? b.towardOtherVelocity : null,
      };
    });

    return {
      samples,
      rows,
      opinion: `Opinion: ${decision}; ${penalty}. Confidence ${Math.round(best.score * 100)}%. Vehicle ${moverLabel} moved laterally toward Vehicle ${otherLabel} at ${formatNumber(best.towardOtherVelocity, 2)}m/s; lateral gap ${formatNumber(best.lateralGap, 2)}m.`,
      metrics: [
        `A lateral score ${scoreLabel(candidates, 1, formatNumber)}`,
        `B lateral score ${scoreLabel(candidates, 2, formatNumber)}`,
        `Gap closed ${formatNumber(best.gapClosed, 2)}m`,
        `Longitudinal gap ${formatNumber(best.longitudinalGap, 2)}m`,
      ],
    };
  }

  function drawChart(canvas, analysis, context) {
    drawSeriesChart(canvas, analysis.rows, context, [
      { key: "lateralGap", label: "lateral gap", color: "#0d6efd" },
      { key: "aToward", label: "A lateral toward", color: "#dc3545" },
      { key: "bToward", label: "B lateral toward", color: "#198754" },
      { key: "distance", label: "distance", color: "#6f42c1", dash: [4, 3] },
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
    const valueRange = Math.max(1, maxValue - minValue);
    const firstTime = rows[0].time;
    const lastTime = rows[rows.length - 1].time;
    const xForTime = (time) => pad.left + ((time - firstTime) / Math.max(0.001, lastTime - firstTime)) * plotWidth;
    const yForValue = (value) => pad.top + plotHeight - ((value - minValue) / valueRange) * plotHeight;
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

  window.RctDecisionModules["unsafe-lateral-movement"] = {
    mount(root, context) {
      const chart = root.querySelector(".rct-unsafe-lateral-chart");
      const metrics = root.querySelector(".rct-unsafe-lateral-metrics");
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
        drawChart(chart, analysis, context);
      };
      if ("ResizeObserver" in window) {
        new ResizeObserver(() => render(currentFrames)).observe(chart);
      }
      return render;
    },
  };
}());
