// SPDX-License-Identifier: BSD-3-Clause

(function () {
  "use strict";

  const PYODIDE_INDEX_URL = "vendor/pyodide/";
  const PYODIDE_SCRIPT_URL = `${PYODIDE_INDEX_URL}pyodide.js`;
  const MATPLOTLIB_PACKAGE_FILES = [
    "numpy-2.2.5-cp313-cp313-pyemscripten_2025_0_wasm32.whl",
    "contourpy-1.3.1-cp313-cp313-pyemscripten_2025_0_wasm32.whl",
    "cycler-0.12.1-py3-none-any.whl",
    "six-1.17.0-py2.py3-none-any.whl",
    "fonttools-4.56.0-py3-none-any.whl",
    "kiwisolver-1.4.8-cp313-cp313-pyemscripten_2025_0_wasm32.whl",
    "packaging-26.2-py3-none-any.whl",
    "pillow-11.3.0-cp313-cp313-pyemscripten_2025_0_wasm32.whl",
    "pyparsing-3.2.1-py3-none-any.whl",
    "python_dateutil-2.9.0.post0-py2.py3-none-any.whl",
    "pytz-2025.2-py2.py3-none-any.whl",
    "matplotlib-3.8.4-cp313-cp313-pyemscripten_2025_0_wasm32.whl",
  ];

  let pyodideScriptPromise = null;
  let matplotlibPromise = null;

  const PYTHON_RENDERER = `
import io
import json
import math
import re

import matplotlib
matplotlib.use("svg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
plt.style.use("default")
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "black",
    "savefig.facecolor": "white",
})


def _finite(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _css_color(value, fallback="#1565c0"):
    if not isinstance(value, str) or not value:
        return fallback
    text = value.strip()
    if text.startswith("rgba(") and text.endswith(")"):
        parts = [part.strip() for part in text[5:-1].split(",")]
        if len(parts) == 4:
            try:
                return (
                    float(parts[0]) / 255.0,
                    float(parts[1]) / 255.0,
                    float(parts[2]) / 255.0,
                    float(parts[3]),
                )
            except ValueError:
                return fallback
    if text.startswith("rgb(") and text.endswith(")"):
        parts = [part.strip() for part in text[4:-1].split(",")]
        if len(parts) == 3:
            try:
                return (
                    float(parts[0]) / 255.0,
                    float(parts[1]) / 255.0,
                    float(parts[2]) / 255.0,
                )
            except ValueError:
                return fallback
    return text


def _axis_title(axis):
    if not isinstance(axis, dict):
        return ""
    title = axis.get("title")
    if isinstance(title, dict):
        return str(title.get("text") or "")
    return str(title or "")


def _clean_graph_title(text):
    title = str(text or "")
    return re.sub(r"^(?:G)?\d+[A-Z]?\.\s*", "", title)


def _trace_points(trace):
    xs = trace.get("x") if isinstance(trace.get("x"), list) else []
    ys = trace.get("y") if isinstance(trace.get("y"), list) else []
    points = []
    for x_value, y_value in zip(xs, ys):
        x = _finite(x_value)
        y = _finite(y_value)
        if x is not None and y is not None:
            points.append((x, y))
    if not points:
        return [], []
    return [point[0] for point in points], [point[1] for point in points]


def _trace_bar_points(trace):
    xs = trace.get("x") if isinstance(trace.get("x"), list) else []
    ys = trace.get("y") if isinstance(trace.get("y"), list) else []
    points = []
    for index, (x_value, y_value) in enumerate(zip(xs, ys)):
        x = _finite(x_value)
        y = _finite(y_value)
        if y is not None:
            points.append((x if x is not None else index, str(x_value), y))
    return points, [str(value) for value in xs]


def _trace_bar_width(trace, fallback=0.2):
    width = trace.get("width")
    if isinstance(width, list):
        for value in width:
            parsed = _finite(value)
            if parsed is not None:
                return parsed
        return fallback
    parsed = _finite(width)
    return parsed if parsed is not None else fallback


def _apply_grid_and_labels(ax, layout, axis_name):
    xaxis = layout.get("xaxis") if isinstance(layout.get("xaxis"), dict) else {}
    x_title = _axis_title(layout.get("xaxis"))
    y_title = _axis_title(layout.get(axis_name))
    if x_title:
        ax.set_xlabel(x_title)
    if y_title:
        ax.set_ylabel(y_title)
    ax.grid(True, axis="y", color="#b0b0b0", linewidth=0.8)
    if xaxis.get("showgrid", True) is not False:
        ax.grid(True, axis="x", color="#b0b0b0", linewidth=0.8)


def _apply_x_ticks_and_range(ax, layout):
    xaxis = layout.get("xaxis") if isinstance(layout.get("xaxis"), dict) else {}
    tickvals = xaxis.get("tickvals") if isinstance(xaxis.get("tickvals"), list) else []
    ticktext = xaxis.get("ticktext") if isinstance(xaxis.get("ticktext"), list) else []
    ticks = []
    labels = []
    for index, value in enumerate(tickvals):
        parsed = _finite(value)
        if parsed is None:
            continue
        ticks.append(parsed)
        labels.append(str(ticktext[index] if index < len(ticktext) else value))
    if ticks:
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels, rotation=25, ha="right")
    axis_range = xaxis.get("range") if isinstance(xaxis.get("range"), list) else []
    if len(axis_range) >= 2:
        left = _finite(axis_range[0])
        right = _finite(axis_range[1])
        if left is not None and right is not None:
            ax.set_xlim(left, right)
    dtick = _finite(xaxis.get("dtick"))
    if dtick is not None and dtick > 0:
        ax.xaxis.set_major_locator(MultipleLocator(dtick))


def _draw_shape_lines(axes, layout):
    for shape in layout.get("shapes") or []:
        if not isinstance(shape, dict) or shape.get("type") != "line":
            continue
        x0 = _finite(shape.get("x0"))
        x1 = _finite(shape.get("x1"))
        if x0 is None or x1 is None or abs(x0 - x1) > 1e-9:
            continue
        line = shape.get("line") if isinstance(shape.get("line"), dict) else {}
        if abs(x0) <= 1e-9 and line.get("color") == "#6c757d":
            continue
        y0 = _finite(shape.get("y0"))
        y1 = _finite(shape.get("y1"))
        is_axis_separator = (
            shape.get("yref") == "paper"
            and y0 is not None
            and y1 is not None
            and abs(y0) <= 1e-9
            and abs(y1 - 1) <= 1e-9
            and not shape.get("name")
            and not line.get("dash")
        )
        color = _css_color(line.get("color"), "#6c757d")
        style = {"dash": "--", "dot": "--", "dashdot": "-."}.get(line.get("dash"), "-")
        width = _finite(line.get("width")) or 1.0
        label = shape.get("name")
        if is_axis_separator:
            label = None
        elif not label:
            label = "collision count" if line.get("dash") == "dashdot" else "minimum distance"
        for index, ax in enumerate(axes):
            ax.axvline(
                x0,
                color=color,
                linestyle=style,
                linewidth=width if is_axis_separator else max(width, 1.6),
                label=label if index == 0 else None,
                zorder=0 if is_axis_separator or shape.get("layer") == "below" else 3,
            )


def _draw_annotations(fig, axes, layout):
    annotations = layout.get("annotations") or []
    if not isinstance(annotations, list):
        return
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        text = _clean_graph_title(annotation.get("text"))
        if not text:
            continue
        y = _finite(annotation.get("y"))
        ax = axes[0] if y is None or y >= 0.5 else axes[-1]
        ax.set_title(text, fontsize=10, pad=8)


def _paper_trace_name(name):
    if name in ("A speed", "Vehicle A", "A acceleration proxy", "A yaw rate", "A jerk proxy"):
        return "RoboRacer 1"
    if name in ("B speed", "Vehicle B", "B acceleration proxy", "B yaw rate", "B jerk proxy"):
        return "RoboRacer 2"
    return name.replace("A ", "RoboRacer 1 ").replace("B ", "RoboRacer 2 ")


def _draw_trace(ax, trace, paper_style):
    mode = str(trace.get("mode") or "lines")
    name = _paper_trace_name(str(trace.get("name") or ""))
    xs, ys = _trace_points(trace)
    if not xs:
        text_values = trace.get("text") if isinstance(trace.get("text"), list) else []
        label = str(text_values[0] if text_values else "No chart data")
        ax.text(0.5, 0.5, label, transform=ax.transAxes, ha="center", va="center", color="#6c757d")
        return
    line = trace.get("line") if isinstance(trace.get("line"), dict) else {}
    marker = trace.get("marker") if isinstance(trace.get("marker"), dict) else {}
    color = None if paper_style else _css_color(line.get("color") or marker.get("color"), "#1565c0")
    if paper_style and "markers" in mode and "lines" not in mode:
        color = _css_color(marker.get("color"), "#1565c0")
    width = None if paper_style else (_finite(line.get("width")) or 2.0)
    marker_size = _finite(marker.get("size")) or 5.0
    marker_symbol = "x" if marker.get("symbol") == "x" else "o"
    if "lines" in mode:
        kwargs = {"label": name or None}
        if width is not None:
            kwargs["linewidth"] = width
        if color is not None:
            kwargs["color"] = color
        ax.plot(xs, ys, **kwargs)
    if "markers" in mode:
        kwargs = {"s": marker_size * marker_size, "marker": marker_symbol, "label": None if "lines" in mode else name or None}
        if color is not None:
            kwargs["color"] = color
        ax.scatter(xs, ys, **kwargs)


def _draw_bar_trace(ax, trace):
    name = _paper_trace_name(str(trace.get("name") or ""))
    orientation = str(trace.get("orientation") or "v")
    marker = trace.get("marker") if isinstance(trace.get("marker"), dict) else {}
    marker_line = marker.get("line") if isinstance(marker.get("line"), dict) else {}
    color = _css_color(marker.get("color"), "#606060")
    edgecolor = _css_color(marker_line.get("color"), "#000000")
    parsed_line_width = _finite(marker_line.get("width"))
    line_width = parsed_line_width if parsed_line_width is not None else 0.6
    if orientation == "h":
        xs = trace.get("x") if isinstance(trace.get("x"), list) else []
        ys = trace.get("y") if isinstance(trace.get("y"), list) else []
        values = []
        labels = []
        for x_value, y_value in zip(xs, ys):
            parsed = _finite(x_value)
            if parsed is None:
                continue
            values.append(parsed)
            labels.append(str(y_value))
        if not values:
            return
        bars = ax.barh(
            labels,
            values,
            color=color,
            edgecolor=edgecolor,
            linewidth=line_width,
            label=name or None,
            zorder=2,
        )
        if not ax.yaxis_inverted():
            ax.invert_yaxis()
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_width(),
                bar.get_y() + bar.get_height() / 2,
                f" {value:g}",
                va="center",
                ha="left",
                fontsize=9,
            )
        return
    points, labels = _trace_bar_points(trace)
    if not points:
        return
    width = _trace_bar_width(trace, 0.2)
    offset = _finite(trace.get("offset")) or 0.0
    bars = ax.bar(
        [x + offset for x, _, _ in points],
        [y for _, _, y in points],
        width=width,
        color=color,
        edgecolor=edgecolor,
        linewidth=line_width,
        label=name or None,
        zorder=2,
    )
    text_position = str(trace.get("textposition") or "")
    if text_position == "outside":
        for bar, (_, _, value) in zip(bars, points):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{value:g}",
                va="bottom",
                ha="center",
                fontsize=9,
            )


def rct_render_matplotlib_plot(payload_json):
    payload = json.loads(payload_json)
    layout = payload.get("layout") if isinstance(payload.get("layout"), dict) else {}
    traces = payload.get("traces") if isinstance(payload.get("traces"), list) else []
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    render = payload.get("render") if isinstance(payload.get("render"), dict) else {}
    paper_style = render.get("style") == "paper"
    has_y2 = any(isinstance(trace, dict) and trace.get("yaxis") == "y2" for trace in traces)

    if has_y2:
        fig, (upper_ax, lower_ax) = plt.subplots(
            2,
            1,
            sharex=True,
            gridspec_kw={"height_ratios": [1, 1], "hspace": 0.32},
        )
        axes = [upper_ax, lower_ax]
        axis_for_trace = {"y": upper_ax, "y2": lower_ax}
    else:
        fig, ax = plt.subplots()
        axes = [ax]
        axis_for_trace = {"y": ax, "y2": ax}

    for trace in traces:
        if not isinstance(trace, dict):
            continue
        ax = axis_for_trace.get(trace.get("yaxis") or "y", axes[0])
        if trace.get("type") == "bar":
            _draw_bar_trace(ax, trace)
            continue
        _draw_trace(ax, trace, paper_style)

    _draw_shape_lines(axes, layout)
    _draw_annotations(fig, axes, layout)
    _apply_grid_and_labels(axes[0], layout, "yaxis")
    _apply_x_ticks_and_range(axes[0], layout)
    if has_y2:
        _apply_grid_and_labels(axes[1], layout, "yaxis2")
        _apply_x_ticks_and_range(axes[1], layout)
    title = _clean_graph_title(metadata.get("title"))
    if title and not has_y2:
        axes[0].set_title(title, pad=10)
    x_label = str(metadata.get("x_axis_title") or "")
    y_label = str(metadata.get("y_axis_title") or "")
    if x_label:
        axes[-1].set_xlabel(x_label)
    if y_label and not has_y2:
        axes[0].set_ylabel(y_label)

    if isinstance(layout.get("yaxis"), dict) and layout["yaxis"].get("scaleanchor") == "x":
        axes[0].set_aspect("equal", adjustable="datalim")

    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(loc="best", frameon=True)

    fig.tight_layout()
    output = io.StringIO()
    fig.savefig(output, format="svg", transparent=False)
    plt.close(fig)
    return output.getvalue()
`;

  function loadPyodideScript() {
    if (pyodideScriptPromise) {
      return pyodideScriptPromise;
    }
    pyodideScriptPromise = new Promise((resolve, reject) => {
      if (typeof window.loadPyodide === "function") {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = PYODIDE_SCRIPT_URL;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load local Pyodide bundle"));
      document.head.appendChild(script);
    });
    return pyodideScriptPromise;
  }

  async function matplotlibImportable(pyodide) {
    try {
      await pyodide.runPythonAsync("import matplotlib; import matplotlib.pyplot");
      return true;
    } catch (error) {
      return false;
    }
  }

  async function ensureMatplotlibInstalled(pyodide) {
    await pyodide.loadPackage("matplotlib");
    if (await matplotlibImportable(pyodide)) {
      return;
    }
    const wheelUrls = MATPLOTLIB_PACKAGE_FILES.map((fileName) => `${PYODIDE_INDEX_URL}${fileName}`);
    await pyodide.loadPackage(wheelUrls);
    if (!(await matplotlibImportable(pyodide))) {
      throw new Error("Pyodide matplotlib package loaded but import still failed");
    }
  }

  async function loadMatplotlib() {
    if (matplotlibPromise) {
      return matplotlibPromise;
    }
    matplotlibPromise = (async () => {
      await loadPyodideScript();
      const pyodide = await window.loadPyodide({
        indexURL: PYODIDE_INDEX_URL,
        lockFileURL: `${PYODIDE_INDEX_URL}pyodide-lock.json`,
        packageBaseUrl: PYODIDE_INDEX_URL,
      });
      await ensureMatplotlibInstalled(pyodide);
      await pyodide.runPythonAsync(PYTHON_RENDERER);
      return pyodide;
    })().catch((error) => {
      matplotlibPromise = null;
      throw error;
    });
    return matplotlibPromise;
  }

  async function render(container, payload) {
    const token = Symbol("rct-matplotlib-render");
    container._rctMatplotlibRenderToken = token;
    container.textContent = matplotlibPromise ? "Rendering matplotlib chart..." : "Initializing Pyodide matplotlib...";
    container.style.aspectRatio = "";
    container.style.height = "";
    container.style.minHeight = "";
    container.style.maxWidth = "";
    const pyodide = await loadMatplotlib();
    if (!container.isConnected || container._rctMatplotlibRenderToken !== token) {
      return;
    }
    const renderPayload = {
      traces: payload.traces,
      layout: payload.layout,
      render: {
        style: "paper",
      },
      metadata: payload.metadata || {},
    };
    const svg = await renderSvg(renderPayload);
    if (!container.isConnected || container._rctMatplotlibRenderToken !== token) {
      return;
    }
    const blobUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    const image = document.createElement("img");
    image.className = "rct-matplotlib-plot-image";
    image.alt = "Matplotlib chart";
    image.src = blobUrl;
    image.onload = () => URL.revokeObjectURL(blobUrl);
    container.replaceChildren(image);
  }

  async function renderSvg(payload) {
    const pyodide = await loadMatplotlib();
    pyodide.globals.set("_rct_plot_payload_json", JSON.stringify(payload));
    return pyodide.runPython("rct_render_matplotlib_plot(_rct_plot_payload_json)");
  }

  window.RCTMatplotlibRenderer = {
    load: loadMatplotlib,
    render,
    renderSvg,
  };
})();
