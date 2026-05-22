(function registerSharedRacingIncidentDecisionModule() {
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
        const samplePoint = samples[index].vehicles[vehicleId];
        samplePoint.velocity = velocityAt(samples, index, vehicleId);
        if (!Number.isFinite(samplePoint.headingYaw) && samplePoint.velocity && length(samplePoint.velocity) > 0.05) {
          samplePoint.headingYaw = Math.atan2(samplePoint.velocity.y, samplePoint.velocity.x);
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

  function basis(pointValue, fallbackTarget) {
    let heading = pointValue.headingYaw;
    if (!Number.isFinite(heading) && pointValue.velocity && length(pointValue.velocity) > 0.05) {
      heading = Math.atan2(pointValue.velocity.y, pointValue.velocity.x);
    }
    if (!Number.isFinite(heading)) {
      heading = Math.atan2(fallbackTarget.y - pointValue.y, fallbackTarget.x - pointValue.x);
    }
    const forward = { x: Math.cos(heading), y: Math.sin(heading) };
    return { forward, right: { x: -forward.y, y: forward.x } };
  }

  function contributionCandidate(samples, vehicleId, otherId) {
    if (samples.length < 2) {
      return null;
    }
    const last = samples[samples.length - 1];
    const vehicle = last.vehicles[vehicleId];
    const other = last.vehicles[otherId];
    const vehicleBasis = basis(vehicle, other);
    const dx = other.x - vehicle.x;
    const dy = other.y - vehicle.y;
    const longitudinal = dx * vehicleBasis.forward.x + dy * vehicleBasis.forward.y;
    const lateral = dx * vehicleBasis.right.x + dy * vehicleBasis.right.y;
    const lateralGap = Math.abs(lateral);
    const vehicleVelocity = vehicle.velocity || { x: 0, y: 0 };
    const otherVelocity = other.velocity || { x: 0, y: 0 };
    const relativeVelocity = { x: vehicleVelocity.x - otherVelocity.x, y: vehicleVelocity.y - otherVelocity.y };
    const closing = relativeVelocity.x * vehicleBasis.forward.x + relativeVelocity.y * vehicleBasis.forward.y;
    const lateralToward = lateral === 0 ? 0 : (vehicleVelocity.x * vehicleBasis.right.x + vehicleVelocity.y * vehicleBasis.right.y) * Math.sign(lateral);
    const first = samples.find((sample) => sample.time >= last.time - 2.0) || samples[0];
    const approach = distance(first.vehicles[vehicleId], first.vehicles[otherId]) - distance(vehicle, other);

    let score = 0;
    if (closing > 0.15 && longitudinal > -0.4) {
      score += 0.28;
    } else if (closing > 0.05) {
      score += 0.12;
    }
    if (lateralToward > 0.12) {
      score += 0.26;
    } else if (lateralToward > 0.04) {
      score += 0.12;
    }
    if (approach > 0.3) {
      score += 0.2;
    } else if (approach > 0.1) {
      score += 0.1;
    }
    if (lateralGap < 1.2) {
      score += 0.16;
    }
    if (distance(vehicle, other) < 2.2) {
      score += 0.1;
    }

    return {
      vehicleId,
      otherId,
      score: Math.min(1, score),
      closing,
      lateralToward,
      lateralGap,
      approach,
      distance: distance(vehicle, other),
    };
  }

  function analyze(frames, context) {
    const { formatNumber } = context;
    const samples = samplesFromFrames(frames);
    if (samples.length < 2) {
      return { rows: [], opinion: "Opinion: Waiting for enough A/B position history.", metrics: [] };
    }

    const a = contributionCandidate(samples, 1, 2);
    const b = contributionCandidate(samples, 2, 1);
    if (!a || !b) {
      return { rows: [], opinion: "Opinion: Shared racing incident cannot be evaluated from this log.", metrics: [] };
    }
    const average = (a.score + b.score) / 2;
    const delta = Math.abs(a.score - b.score);
    const sharedScore = Math.max(0, average - delta * 0.65);
    let decision = "Shared racing incident unlikely";
    if (sharedScore >= 0.62) {
      decision = "Shared racing incident likely";
    } else if (sharedScore >= 0.42) {
      decision = "Shared racing incident possible";
    }

    const rows = samples.map((sample, index) => {
      const partial = samples.slice(0, index + 1);
      const candidateA = contributionCandidate(partial, 1, 2);
      const candidateB = contributionCandidate(partial, 2, 1);
      return {
        time: sample.time,
        distance: distance(sample.vehicles[1], sample.vehicles[2]),
        aScore: candidateA ? candidateA.score * 100 : null,
        bScore: candidateB ? candidateB.score * 100 : null,
        sharedScore: candidateA && candidateB ? Math.max(0, ((candidateA.score + candidateB.score) / 2 - Math.abs(candidateA.score - candidateB.score) * 0.65)) * 100 : null,
      };
    });

    return {
      rows,
      opinion: `Opinion: ${decision}; ${sharedScore >= 0.42 ? "shared/no primary penalty recommended" : "one-sided responsibility remains possible"}. Confidence ${Math.round(sharedScore * 100)}%. A contribution ${formatNumber(a.score * 100, 0)}%, B contribution ${formatNumber(b.score * 100, 0)}%, delta ${formatNumber(delta * 100, 0)}%.`,
      metrics: [
        `A contribution ${formatNumber(a.score * 100, 0)}%`,
        `B contribution ${formatNumber(b.score * 100, 0)}%`,
        `Shared score ${formatNumber(sharedScore * 100, 0)}%`,
        `Final distance ${formatNumber(a.distance, 2)}m`,
      ],
    };
  }

  function draw(canvas, analysis, context) {
    drawSeriesChart(canvas, analysis.rows, context, [
      { key: "aScore", label: "A contribution", color: "#dc3545" },
      { key: "bScore", label: "B contribution", color: "#198754" },
      { key: "sharedScore", label: "shared score", color: "#0d6efd" },
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

  window.RctDecisionModules["shared-racing-incident"] = {
    mount(root, context) {
      const chart = root.querySelector(".rct-shared-incident-chart");
      const metrics = root.querySelector(".rct-shared-incident-metrics");
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
