(function registerUnsafeRejoinDecisionModule() {
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
        samples[index].vehicles[vehicleId].velocity = velocityAt(samples, index, vehicleId);
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

  function vectorLength(vector) {
    return vector ? Math.hypot(vector.x, vector.y) : 0;
  }

  function distance(left, right) {
    return Math.hypot(right.x - left.x, right.y - left.y);
  }

  function rejoinCandidate(samples, moverId, otherId) {
    if (samples.length < 3) {
      return null;
    }
    const last = samples[samples.length - 1];
    const mover = last.vehicles[moverId];
    const other = last.vehicles[otherId];
    const first = samples.find((sample) => sample.time >= last.time - 2.5) || samples[0];
    const firstMover = first.vehicles[moverId];
    const firstOther = first.vehicles[otherId];
    const currentDistance = distance(mover, other);
    const previousDistance = distance(firstMover, firstOther);
    const approach = previousDistance - currentDistance;

    const otherVelocity = other.velocity || { x: other.x - firstOther.x, y: other.y - firstOther.y };
    const otherSpeed = Math.max(0.05, vectorLength(otherVelocity));
    const racingForward = { x: otherVelocity.x / otherSpeed, y: otherVelocity.y / otherSpeed };
    const racingRight = { x: -racingForward.y, y: racingForward.x };
    const firstOffset = (firstMover.x - firstOther.x) * racingRight.x + (firstMover.y - firstOther.y) * racingRight.y;
    const currentOffset = (mover.x - other.x) * racingRight.x + (mover.y - other.y) * racingRight.y;
    const returnDistance = Math.abs(firstOffset) - Math.abs(currentOffset);
    const moverVelocity = mover.velocity || { x: 0, y: 0 };
    const returnVelocity = -Math.sign(currentOffset || firstOffset || 1) * (moverVelocity.x * racingRight.x + moverVelocity.y * racingRight.y);

    let score = 0;
    if (Math.abs(firstOffset) > 2.0) {
      score += 0.22;
    } else if (Math.abs(firstOffset) > 1.2) {
      score += 0.12;
    }
    if (returnDistance > 0.7) {
      score += 0.28;
    } else if (returnDistance > 0.25) {
      score += 0.14;
    }
    if (returnVelocity > 0.25) {
      score += 0.2;
    } else if (returnVelocity > 0.08) {
      score += 0.1;
    }
    if (approach > 0.5) {
      score += 0.16;
    } else if (approach > 0.15) {
      score += 0.08;
    }
    if (currentDistance < 2.2) {
      score += 0.14;
    }

    return {
      moverId,
      otherId,
      score: Math.min(1, score),
      currentDistance,
      previousDistance,
      approach,
      firstOffset,
      currentOffset,
      returnDistance,
      returnVelocity,
    };
  }

  function label(candidates, moverId, formatNumber) {
    const candidate = candidates.find((item) => item.moverId === moverId);
    return candidate ? `${formatNumber(candidate.score * 100, 0)}%` : "-";
  }

  function analyze(frames, context) {
    const { displayRoboracerLabel, formatNumber } = context;
    const samples = samplesFromFrames(frames);
    if (samples.length < 3) {
      return { rows: [], opinion: "Opinion: Waiting for enough A/B position history.", metrics: [] };
    }
    const candidates = [
      rejoinCandidate(samples, 1, 2),
      rejoinCandidate(samples, 2, 1),
    ].filter(Boolean).sort((left, right) => right.score - left.score);
    const best = candidates[0];
    if (!best) {
      return { rows: [], opinion: "Opinion: Unsafe rejoin cannot be evaluated from this log.", metrics: [] };
    }

    const moverLabel = displayRoboracerLabel(best.moverId);
    const otherLabel = displayRoboracerLabel(best.otherId);
    let decision = "Unsafe rejoin unlikely";
    let penalty = "no clear penalty";
    if (best.score >= 0.7) {
      decision = "Unsafe rejoin likely";
      penalty = `primary penalty Vehicle ${moverLabel}`;
    } else if (best.score >= 0.5) {
      decision = "Unsafe rejoin possible";
      penalty = `possible penalty Vehicle ${moverLabel}`;
    }

    const rows = samples.map((sample, index) => {
      const partial = samples.slice(0, index + 1);
      const a = partial.length >= 3 ? rejoinCandidate(partial, 1, 2) : null;
      const b = partial.length >= 3 ? rejoinCandidate(partial, 2, 1) : null;
      return {
        time: sample.time,
        distance: distance(sample.vehicles[1], sample.vehicles[2]),
        aReturn: a ? a.returnDistance : null,
        bReturn: b ? b.returnDistance : null,
        approach: a ? a.approach : null,
      };
    });

    return {
      rows,
      opinion: `Opinion: ${decision}; ${penalty}. Confidence ${Math.round(best.score * 100)}%. Vehicle ${moverLabel} returned ${formatNumber(best.returnDistance, 2)}m toward Vehicle ${otherLabel}; final distance ${formatNumber(best.currentDistance, 2)}m. Track-boundary data is not available, so this is rejoin-like motion only.`,
      metrics: [
        `A rejoin score ${label(candidates, 1, formatNumber)}`,
        `B rejoin score ${label(candidates, 2, formatNumber)}`,
        `Initial offset ${formatNumber(Math.abs(best.firstOffset), 2)}m`,
        `Return speed ${formatNumber(best.returnVelocity, 2)}m/s`,
      ],
    };
  }

  function draw(canvas, analysis, context) {
    drawSeriesChart(canvas, analysis.rows, context, [
      { key: "distance", label: "distance", color: "#0d6efd" },
      { key: "aReturn", label: "A return", color: "#dc3545" },
      { key: "bReturn", label: "B return", color: "#198754" },
      { key: "approach", label: "approach", color: "#6f42c1", dash: [4, 3] },
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

  window.RctDecisionModules["unsafe-rejoin"] = {
    mount(root, context) {
      const chart = root.querySelector(".rct-unsafe-rejoin-chart");
      const metrics = root.querySelector(".rct-unsafe-rejoin-metrics");
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
