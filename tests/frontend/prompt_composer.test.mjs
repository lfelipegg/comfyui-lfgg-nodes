import assert from "node:assert/strict";
import test from "node:test";

import { installPromptComposer } from "../../web/prompt_composer.mjs";

class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.style = {};
    this.value = "";
    this.disabled = false;
    this.selectionStart = 0;
    this.selectionEnd = 0;
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  addEventListener(name, callback) {
    (this.listeners[name] ??= []).push(callback);
  }

  dispatch(name) {
    for (const callback of this.listeners[name] ?? []) callback({ target: this });
  }

  setAttribute(name, value) {
    this[name] = String(value);
  }

  setSelectionRange(start, end) {
    this.selectionStart = start;
    this.selectionEnd = end;
  }

  focus() {
    this.focused = true;
  }
}

const documentStub = {
  createElement: (tagName) => new Element(tagName),
};

function descendants(element) {
  return [element, ...element.children.flatMap(descendants)];
}

function graphNode(value = "front END") {
  const inputEl = new Element("textarea");
  inputEl.value = value;
  inputEl.selectionStart = 6;
  inputEl.selectionEnd = 9;
  const prompt = {
    name: "prompt_template",
    value,
    inputEl,
    callback(next) {
      this.callbackValue = next;
    },
  };
  const seed = { name: "seed", value: 0 };
  const widgets = [prompt, seed];
  return {
    comfyClass: "LFGG_PromptComposer",
    widgets,
    size: [300, 200],
    addDOMWidget(name, type, element, options) {
      const added = { name, type, element, options, serialize: options.serialize };
      widgets.push(added);
      return added;
    },
    setSize(size) {
      this.size = size;
    },
    setDirtyCanvas() {
      this.dirty = true;
    },
  };
}

function byRole(widget, role) {
  return descendants(widget.element).find(({ dataset }) => dataset.role === role);
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}

test("installs idempotent nonserialized selectors with disabled catalog entries", async () => {
  const node = graphNode();
  const catalog = {
    ok: true,
    wildcards: [
      { name: "animals/pets", disabled: false },
      { name: "empty", disabled: true },
    ],
    styles: [
      { name: "--- Styles ---", disabled: true },
      { name: "Cinematic", disabled: false },
    ],
  };
  const widget = installPromptComposer(node, {
    document: documentStub,
    fetchLibraries: async () => catalog,
  });
  await widget.lfggReady;

  assert.equal(installPromptComposer(node, {
    document: documentStub,
    fetchLibraries: async () => catalog,
  }), widget);
  assert.equal(widget.serialize, false);
  assert.equal(widget.options.serialize, false);
  assert.equal(node.widgets.length, 3);
  assert.deepEqual(node.widgets.map(({ name }) => name), [
    "prompt_template",
    "lfgg_prompt_composer",
    "seed",
  ]);
  assert.deepEqual(
    byRole(widget, "wildcards").children.map(({ textContent, disabled }) => ({
      textContent,
      disabled,
    })),
    [
      { textContent: "Add wildcard…", disabled: true },
      { textContent: "animals/pets", disabled: false },
      { textContent: "empty", disabled: true },
    ],
  );
  assert.equal(byRole(widget, "styles").children[1].disabled, true);

  const serialized = { widgets_values: ["front END", null, 0] };
  node.onSerialize(serialized);
  assert.deepEqual(serialized.widgets_values, ["front END", 0]);
});

test("constrains library controls to a compact node-width layout", async () => {
  const node = graphNode();
  const widget = installPromptComposer(node, {
    document: documentStub,
    fetchLibraries: async () => ({
      ok: true,
      wildcards: [{ name: "a/very/long/nested/wildcard/name", disabled: false }],
      styles: [{ name: "A very long style name", disabled: false }],
    }),
  });
  await widget.lfggReady;

  assert.equal(widget.element.style.display, "grid");
  assert.equal(widget.element.style.width, "100%");
  assert.equal(widget.element.style.minWidth, "0");
  assert.equal(widget.element.style.boxSizing, "border-box");
  assert.equal(byRole(widget, "selectors").style.gridTemplateColumns, "repeat(2, minmax(0, 1fr))");
  for (const role of ["wildcards", "styles"]) {
    const select = byRole(widget, role);
    assert.equal(select.style.width, "100%");
    assert.equal(select.style.minWidth, "0");
    assert.equal(select.style.maxWidth, "100%");
  }
  assert.equal(byRole(widget, "actions").style.display, "flex");
  assert.equal(byRole(widget, "status").style.textOverflow, "ellipsis");
  assert.equal(byRole(widget, "status").textContent, "1 wildcard · 1 style");
  assert.equal(widget.options.getMinHeight(), 104);
  assert.equal(widget.options.getMaxHeight(), 104);
  assert.deepEqual(node.size, [360, 330]);
});

test("inserts wildcard and style tokens at the caret and replaces selected text", async () => {
  const node = graphNode();
  const widget = installPromptComposer(node, {
    document: documentStub,
    fetchLibraries: async () => ({
      ok: true,
      wildcards: [{ name: "animals/pets", disabled: false }],
      styles: [{ name: "Cinematic", disabled: false }],
    }),
  });
  await widget.lfggReady;

  const wildcard = byRole(widget, "wildcards");
  wildcard.value = "animals/pets";
  wildcard.dispatch("change");
  assert.equal(node.widgets[0].value, "front __animals/pets__, ");
  assert.equal(wildcard.value, "");

  const style = byRole(widget, "styles");
  style.value = "Cinematic";
  style.dispatch("change");
  assert.equal(
    node.widgets[0].value,
    "front __animals/pets__, [[style:Cinematic]], ",
  );
  assert.equal(node.widgets[0].callbackValue, node.widgets[0].value);
  assert.equal(node.widgets[0].inputEl.focused, true);
  assert.equal(node.dirty, true);
});

test("refresh disables duplicate requests and retains the last valid catalog on error", async () => {
  const node = graphNode();
  const next = deferred();
  let calls = 0;
  const widget = installPromptComposer(node, {
    document: documentStub,
    fetchLibraries: async () => {
      calls += 1;
      if (calls === 1) {
        return {
          ok: true,
          wildcards: [{ name: "first", disabled: false }],
          styles: [{ name: "Style", disabled: false }],
        };
      }
      return next.promise;
    },
  });
  await widget.lfggReady;
  const refresh = byRole(widget, "refresh");
  const wildcard = byRole(widget, "wildcards");

  refresh.dispatch("click");
  refresh.dispatch("click");
  assert.equal(refresh.disabled, true);
  assert.equal(calls, 2);
  next.reject(new Error("Invalid configuration"));
  await widget.lfggReady;

  assert.equal(refresh.disabled, false);
  assert.equal(wildcard.children[1].textContent, "first");
  assert.equal(byRole(widget, "status").textContent, "Invalid configuration");
});

test("invalid partial refresh preserves both last-valid selector lists", async () => {
  const node = graphNode();
  let calls = 0;
  const widget = installPromptComposer(node, {
    document: documentStub,
    fetchLibraries: async () => {
      calls += 1;
      return calls === 1
        ? {
          ok: true,
          wildcards: [{ name: "first-wildcard", disabled: false }],
          styles: [{ name: "first-style", disabled: false }],
        }
        : {
          ok: true,
          wildcards: [{ name: "new-wildcard", disabled: false }],
          styles: [{ name: "", disabled: false }],
        };
    },
  });
  await widget.lfggReady;
  byRole(widget, "refresh").dispatch("click");
  await widget.lfggReady;

  assert.equal(byRole(widget, "wildcards").children[1].textContent, "first-wildcard");
  assert.equal(byRole(widget, "styles").children[1].textContent, "first-style");
  assert.equal(
    byRole(widget, "status").textContent,
    "The prompt library response is invalid",
  );
});

test("initial refresh failure shows disabled explanatory entries", async () => {
  const node = graphNode();
  const widget = installPromptComposer(node, {
    document: documentStub,
    fetchLibraries: async () => {
      throw new Error("Missing configuration");
    },
  });
  await widget.lfggReady;

  const wildcard = byRole(widget, "wildcards");
  assert.equal(wildcard.children[0].textContent, "Wildcards unavailable");
  assert.equal(wildcard.children[0].disabled, true);
  assert.equal(byRole(widget, "status").textContent, "Missing configuration");
});
