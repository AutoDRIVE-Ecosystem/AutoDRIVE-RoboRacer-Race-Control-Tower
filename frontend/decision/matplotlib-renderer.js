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


def _apply_grid_and_labels(ax, layout, axis_name):
    x_title = _axis_title(layout.get("xaxis"))
    y_title = _axis_title(layout.get(axis_name))
    if x_title:
        ax.set_xlabel(x_title)
    if y_title:
        ax.set_ylabel(y_title)
    ax.grid(True, color="#b0b0b0", linewidth=0.8)


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
        color = _css_color(line.get("color"), "#6c757d")
        style = {"dash": "--", "dot": "--", "dashdot": "-."}.get(line.get("dash"), "-")
        width = _finite(line.get("width")) or 1.0
        label = shape.get("name")
        if not label:
            label = "collision count" if line.get("dash") == "dashdot" else "minimum distance"
        for index, ax in enumerate(axes):
            ax.axvline(x0, color=color, linestyle=style, linewidth=max(width, 1.6), label=label if index == 0 else None)


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
        _draw_trace(axis_for_trace.get(trace.get("yaxis") or "y", axes[0]), trace, paper_style)

    _draw_shape_lines(axes, layout)
    _draw_annotations(fig, axes, layout)
    _apply_grid_and_labels(axes[0], layout, "yaxis")
    if has_y2:
        _apply_grid_and_labels(axes[1], layout, "yaxis2")
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
