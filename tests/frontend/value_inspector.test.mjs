import assert from "node:assert/strict";
import test from "node:test";

import {
  VALUE_INSPECTOR_ID,
  installValueInspector,
} from "../../web/value_inspector.mjs";

class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.textContent = "";
  }

  append(...children) {
    this.children.push(...children);
  }

  setAttribute(name, value) {
    this[name] = String(value);
  }
}

function descendants(element) {
  return [element, ...element.children.flatMap(descendants)];
}

function byRole(widget, role) {
  return descendants(widget.element).find(({ dataset }) => dataset.role === role);
}

const documentStub = {
  createElement: (tagName) => new Element(tagName),
};

function graphNode() {
  const widgets = [{ name: "existing", value: 1 }];
  return {
    comfyClass: VALUE_INSPECTOR_ID,
    widgets,
    size: [200, 100],
    onExecutionStart() {
      this.started = (this.started ?? 0) + 1;
    },
    onExecuted() {
      this.executed = (this.executed ?? 0) + 1;
    },
    onExecutionError() {
      this.failed = (this.failed ?? 0) + 1;
    },
    onSerialize() {
      this.serialized = (this.serialized ?? 0) + 1;
    },
    addDOMWidget(name, type, element, options) {
      const widget = { name, type, element, options };
      widgets.push(widget);
      return widget;
    },
    setSize(size) {
      this.size = size;
    },
  };
}

test("installs one compact, selectable, nonserialized report surface", () => {
  const node = graphNode();
  const widget = installValueInspector(node, { document: documentStub });
  const report = byRole(widget, "report");
  const status = byRole(widget, "status");

  assert.equal(
    installValueInspector(node, { document: documentStub }),
    widget,
  );
  assert.equal(node.widgets.length, 2);
  assert.equal(widget.serialize, false);
  assert.equal(widget.options.serialize, false);
  assert.ok(widget.options.getMinHeight() < 180);
  assert.equal(report.style.overflow, "auto");
  assert.match(report.style.fontFamily, /monospace/);
  assert.equal(report.style.userSelect, "text");
  assert.equal(report.tabIndex, 0);
  assert.equal(report.role, "region");
  assert.equal(report["aria-label"], "Value inspector report");
  assert.equal(report["aria-live"], undefined);
  assert.equal(report.textContent, "Run to inspect a value");
  assert.equal(status.role, "status");
  assert.equal(status["aria-live"], "polite");
  assert.equal(status.dataset.state, "waiting");
  assert.deepEqual(node.size, [200, 100]);
  assert.equal(
    descendants(widget.element).filter(({ className }) =>
      className === "lfgg-identity").length,
    1,
  );

  const serialized = { widgets_values: [1, "must not persist"] };
  node.onSerialize(serialized);
  assert.deepEqual(serialized.widgets_values, [1]);
  assert.equal(node.serialized, 1);
});

test("retains report text while separate status tracks waiting, current and stale", () => {
  const node = graphNode();
  const widget = installValueInspector(node, { document: documentStub });
  const report = byRole(widget, "report");
  const status = byRole(widget, "status");

  node.onExecutionStart();
  assert.equal(report.textContent, "Run to inspect a value");
  assert.equal(status.dataset.state, "waiting");
  assert.equal(node.started, 1);

  node.onExecuted({ report: ["value: <script>alert(1)</script>"] });
  assert.equal(report.textContent, "value: <script>alert(1)</script>");
  assert.equal(report.dataset.stale, "false");
  assert.equal(status.dataset.state, "current");
  assert.equal(node.executed, 1);

  node.onExecutionStart();
  assert.equal(report.textContent, "value: <script>alert(1)</script>");
  assert.equal(report.dataset.stale, "true");
  assert.equal(status.dataset.state, "stale");

  node.onExecuted({});
  assert.equal(report.textContent, "value: <script>alert(1)</script>");
  assert.equal(status.dataset.state, "stale");

  node.onExecutionError(new Error("failed"));
  assert.equal(report.textContent, "value: <script>alert(1)</script>");
  assert.equal(status.dataset.state, "stale");
  assert.equal(node.failed, 1);

  node.onExecuted({ report: ["value: 7"] });
  assert.equal(report.textContent, "value: 7");
  assert.equal(report.dataset.stale, "false");
  assert.equal(status.dataset.state, "current");
});

test("ignores other backend node classes", () => {
  const node = graphNode();
  node.comfyClass = "Other_Node";

  assert.equal(
    installValueInspector(node, { document: documentStub }),
    undefined,
  );
  assert.equal(node.widgets.length, 1);
});
