import { UI, initializeRoot } from "./node_ui.mjs";

export const VALUE_INSPECTOR_ID = "LFGG_ValueInspector";
export const VALUE_INSPECTOR_NAME = "LFGG Value Inspector";

const INITIAL_REPORT = "Run to inspect a value";
const installed = Symbol("lfggValueInspector");

export function installValueInspector(
  node,
  { document = globalThis.document } = {},
) {
  if (node.comfyClass !== VALUE_INSPECTOR_ID || node[installed] || !document) {
    return node[installed];
  }

  const root = document.createElement("div");
  const heading = document.createElement("div");
  const report = document.createElement("pre");
  const status = document.createElement("span");
  heading.dataset.role = "heading";
  heading.textContent = "Value report";
  Object.assign(heading.style, {
    display: "flex",
    alignItems: "center",
    minWidth: "0",
    fontSize: "14px",
    fontWeight: "600",
    lineHeight: "1.2",
  });
  Object.assign(root.style, {
    display: "grid",
    gridTemplateRows: "auto minmax(0, 1fr) auto",
    gap: `${UI.gap}px`,
    width: "100%",
    height: "100%",
    minWidth: "0",
    minHeight: "0",
    padding: `${UI.inset}px`,
    boxSizing: "border-box",
    overflow: "hidden",
  });
  report.dataset.role = "report";
  report.dataset.stale = "false";
  report.tabIndex = 0;
  report.setAttribute("role", "region");
  report.setAttribute("aria-label", "Value inspector report");
  report.textContent = INITIAL_REPORT;
  Object.assign(report.style, {
    width: "100%",
    minWidth: "0",
    minHeight: "0",
    margin: "0",
    overflow: "auto",
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    fontSize: `${UI.secondarySize}px`,
    lineHeight: "1.4",
    userSelect: "text",
    boxSizing: "border-box",
  });
  status.dataset.role = "status";
  status.dataset.state = "waiting";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  status.textContent = "Waiting for execution.";
  Object.assign(status.style, {
    minWidth: "0",
    overflowWrap: "anywhere",
  });
  root.append(heading, report, status);
  initializeRoot(node, root, document, heading);

  let lastReport;
  const render = (state, message) => {
    report.dataset.stale = String(state === "stale");
    report.textContent = lastReport ?? INITIAL_REPORT;
    status.dataset.state = state;
    status.textContent = message;
  };

  const originalExecutionStart = node.onExecutionStart;
  node.onExecutionStart = function (...args) {
    const result = originalExecutionStart?.apply(this, args);
    render(
      lastReport === undefined ? "waiting" : "stale",
      lastReport === undefined
        ? "Waiting for execution."
        : "Waiting for execution · showing previous report.",
    );
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function (message) {
    const result = originalExecuted?.apply(this, arguments);
    const next = message?.report?.[0];
    if (typeof next === "string") {
      lastReport = next;
      render("current", "Current report.");
    } else {
      render(
        lastReport === undefined ? "waiting" : "stale",
        lastReport === undefined
          ? "No report received."
          : "No current report received · showing previous report.",
      );
    }
    return result;
  };

  const originalExecutionError = node.onExecutionError;
  node.onExecutionError = function (...args) {
    const result = originalExecutionError?.apply(this, args);
    render(
      lastReport === undefined ? "waiting" : "stale",
      lastReport === undefined
        ? "Execution failed before a report was available."
        : "Execution failed · showing previous report.",
    );
    return result;
  };

  const widget = node.addDOMWidget(
    "lfgg_value_inspector",
    "lfgg_value_inspector",
    root,
    { serialize: false, getMinHeight: () => 104 },
  );
  widget.serialize = false;
  widget.options.serialize = false;
  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    const index = node.widgets?.indexOf(widget) ?? -1;
    if (
      index >= 0
      && Array.isArray(serialized.widgets_values)
      && serialized.widgets_values.length === node.widgets.length
    ) {
      serialized.widgets_values.splice(index, 1);
    }
    return result;
  };
  node[installed] = widget;
  return widget;
}
