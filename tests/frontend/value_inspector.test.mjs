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

test("installs one fixed, scrollable, nonserialized report panel", () => {
  const node = graphNode();
  const widget = installValueInspector(node, { document: documentStub });
  const report = widget.element.children[0];

  assert.equal(
    installValueInspector(node, { document: documentStub }),
    widget,
  );
  assert.equal(node.widgets.length, 2);
  assert.equal(widget.serialize, false);
  assert.equal(widget.options.serialize, false);
  assert.equal(widget.options.getMinHeight(), 180);
  assert.equal(widget.element.style.height, "180px");
  assert.equal(report.style.overflow, "auto");
  assert.match(report.style.fontFamily, /monospace/);
  assert.equal(report.tabIndex, 0);
  assert.equal(report.role, "region");
  assert.equal(report["aria-label"], "Value inspector report");
  assert.equal(report["aria-live"], undefined);
  assert.equal(report.textContent, "Run to inspect a value");
  assert.deepEqual(node.size, [360, 240]);

  const serialized = { widgets_values: [1, "must not persist"] };
  node.onSerialize(serialized);
  assert.deepEqual(serialized.widgets_values, [1]);
  assert.equal(node.serialized, 1);
});

test("uses textContent and retains a stale successful report until replacement", () => {
  const node = graphNode();
  const widget = installValueInspector(node, { document: documentStub });
  const report = widget.element.children[0];

  node.onExecutionStart();
  assert.equal(report.textContent, "Run to inspect a value");
  assert.equal(node.started, 1);

  node.onExecuted({ report: ["value: <script>alert(1)</script>"] });
  assert.equal(report.textContent, "value: <script>alert(1)</script>");
  assert.equal(report.dataset.stale, "false");
  assert.equal(node.executed, 1);

  node.onExecutionStart();
  assert.equal(
    report.textContent,
    "[stale — latest successful report]\nvalue: <script>alert(1)</script>",
  );
  assert.equal(report.dataset.stale, "true");

  node.onExecuted({});
  assert.equal(report.dataset.stale, "true");
  node.onExecuted({ report: ["value: 7"] });
  assert.equal(report.textContent, "value: 7");
  assert.equal(report.dataset.stale, "false");
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
