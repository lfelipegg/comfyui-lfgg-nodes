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
  const report = document.createElement("pre");
  Object.assign(root.style, {
    width: "100%",
    height: "180px",
    minWidth: "0",
    padding: "8px",
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
    height: "100%",
    margin: "0",
    overflow: "auto",
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    fontSize: "12px",
    lineHeight: "1.4",
    userSelect: "text",
    boxSizing: "border-box",
  });
  root.append(report);

  let lastReport;
  const render = (stale = false) => {
    report.dataset.stale = String(stale);
    report.textContent = stale
      ? `[stale — latest successful report]\n${lastReport}`
      : (lastReport ?? INITIAL_REPORT);
  };

  const originalExecutionStart = node.onExecutionStart;
  node.onExecutionStart = function (...args) {
    const result = originalExecutionStart?.apply(this, args);
    if (lastReport !== undefined) render(true);
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function (message) {
    const result = originalExecuted?.apply(this, arguments);
    const next = message?.report?.[0];
    if (typeof next === "string") {
      lastReport = next;
      render();
    }
    return result;
  };

  const widget = node.addDOMWidget(
    "lfgg_value_inspector",
    "lfgg_value_inspector",
    root,
    { serialize: false, getMinHeight: () => 180 },
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
  node.setSize?.([
    Math.max(node.size?.[0] ?? 0, 360),
    Math.max(node.size?.[1] ?? 0, 240),
  ]);
  node[installed] = widget;
  return widget;
}
