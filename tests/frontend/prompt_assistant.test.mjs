import assert from "node:assert/strict";
import test from "node:test";

import {
  PROMPT_ASSISTANT_ID,
  formatBytes,
  installPromptAssistant,
  parseSelection,
  selectionSummary,
  setAllFiles,
  setFile,
  setSkill,
} from "../../web/prompt_assistant.mjs";

class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.style = {};
    this.textContent = "";
    this.value = "";
    this.disabled = false;
    this.checked = false;
    this.hidden = false;
  }

  append(...children) {
    this.children.push(...children);
  }

  prepend(...children) {
    this.children.unshift(...children);
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
}

const documentStub = { createElement: (tagName) => new Element(tagName) };

function descendants(element) {
  return [element, ...element.children.flatMap(descendants)];
}

function byRole(element, role, id) {
  return descendants(element).find(
    (item) => item.dataset.role === role && (id === undefined || item.dataset.id === id || item.dataset.name === id),
  );
}

function allByRole(element, role) {
  return descendants(element).filter((item) => item.dataset.role === role);
}

const CATALOG = {
  roots: [
    { path: "/home/u/.agents/skills", available: true },
    { path: "C:/Users/u/.agents/skills", available: false },
  ],
  skills: [
    {
      name: "scenario-maker-sdxl",
      root: "/home/u/.agents/skills",
      available: true,
      skill_size: 2048,
      files: [
        { path: "references/models/sdxl.md", size: 1024 },
        { path: "references/routing.md", size: 512 },
      ],
    },
    { name: "scenario-maker-wan", root: "/home/u/.agents/skills", available: true, skill_size: 100, files: [] },
    { name: "scenario-maker-pony", root: null, available: false, skill_size: 0, files: [] },
  ],
  warnings: [],
  limits: { total: 262144, file: 524288 },
};

function graphNode({ skills = "", model = "server default", fetchSkills, fetchModels } = {}) {
  const inputEl = new Element("textarea");
  inputEl.value = skills;
  const skillsWidget = {
    name: "skills",
    value: skills,
    inputEl,
    callback(next) {
      this.callbackValues = [...(this.callbackValues ?? []), next];
    },
  };
  const widgets = [
    { name: "master_prompt", value: "m" },
    { name: "request", value: "r" },
    skillsWidget,
    { name: "model", value: model, options: { values: ["server default"] } },
    { name: "vram_policy", value: "share" },
    { name: "seed", value: 0 },
  ];
  const node = {
    id: 7,
    comfyClass: PROMPT_ASSISTANT_ID,
    widgets,
    inputs: [
      { name: "master_prompt", link: null },
      { name: "request", link: null },
      { name: "skills", link: null },
    ],
    properties: {},
    size: [400, 300],
    addDOMWidget(name, type, element, options) {
      const widget = { name, type, element, options, serialize: options.serialize };
      widgets.push(widget);
      return widget;
    },
    computeSize() {
      return [400, 300];
    },
    setSize(size) {
      this.size = size;
    },
    setDirtyCanvas() {
      this.dirty = (this.dirty ?? 0) + 1;
    },
    onSerialize() {
      this.serializedCount = (this.serializedCount ?? 0) + 1;
    },
  };
  const options = {
    document: documentStub,
    fetchSkills: fetchSkills ?? (async () => CATALOG),
    fetchModels: fetchModels ?? (async () => ({ mode: "router", models: [{ id: "a", status: "loaded" }, { id: "b", status: "unloaded" }] })),
    nodeOutputs: () => node.outputs,
  };
  return { node, skillsWidget, options };
}

test("selection helpers edit only the skills text", () => {
  assert.deepEqual(parseSelection(" a \n\nb/references/x.md\r\n"), [
    { skill: "a", file: null, raw: "a" },
    { skill: "b", file: "references/x.md", raw: "b/references/x.md" },
  ]);
  assert.equal(setSkill("", "a", true), "a");
  assert.equal(setSkill("a", "a", true), "a");
  assert.equal(setSkill("a\nb\na/x.md", "a", false), "b");
  assert.equal(setFile("a", "a", "x.md", true), "a\na/x.md");
  assert.equal(setFile("a\na/x.md\na/x.md", "a", "x.md", false), "a");
  assert.equal(setAllFiles("hand-edited", "a", ["x.md", "y.md"], true), "hand-edited\na/x.md\na/y.md");
  assert.equal(formatBytes(512), "512 B");
  assert.equal(formatBytes(1536), "1.5 KiB");
  assert.equal(formatBytes(262144), "256 KiB");
  assert.deepEqual(
    selectionSummary("scenario-maker-sdxl/references/routing.md\nscenario-maker-pony\nmystery\nscenario-maker-sdxl/nope.md", CATALOG),
    { skills: 3, files: 2, bytes: 2560, unknown: ["scenario-maker-pony", "mystery", "scenario-maker-sdxl/nope.md"] },
  );
});

const LINKED_CATALOG = {
  ...CATALOG,
  skills: [
    {
      ...CATALOG.skills[0],
      files: [
        { path: "references/models/sdxl.md", size: 1024, linked: true },
        { path: "references/routing.md", size: 512, linked: false },
      ],
    },
  ],
};

test("linked references count with their skill and stay locked in the picker", async () => {
  assert.deepEqual(selectionSummary("scenario-maker-sdxl", LINKED_CATALOG), {
    skills: 1, files: 1, bytes: 3072, unknown: [],
  });
  assert.deepEqual(
    selectionSummary("scenario-maker-sdxl/references/models/sdxl.md\nscenario-maker-sdxl/references/routing.md", LINKED_CATALOG),
    { skills: 1, files: 2, bytes: 3584, unknown: [] },
  );

  const { skillsWidget, node, options } = graphNode({ skills: "scenario-maker-sdxl", fetchSkills: async () => LINKED_CATALOG });
  const widget = installPromptAssistant(node, options);
  await widget.lfggReady;
  byRole(widget.element, "disclosure").dispatch("click");
  byRole(widget.element, "files-toggle", "scenario-maker-sdxl").dispatch("click");
  const linkedBox = byRole(widget.element, "file-toggle", "scenario-maker-sdxl/references/models/sdxl.md");
  assert.equal(linkedBox.checked, true);
  assert.equal(linkedBox.disabled, true);
  assert.equal(byRole(widget.element, "file-toggle", "scenario-maker-sdxl/references/routing.md").checked, false);
  byRole(widget.element, "all-files", "scenario-maker-sdxl").dispatch("click");
  assert.equal(skillsWidget.value, "scenario-maker-sdxl\nscenario-maker-sdxl/references/routing.md");
  assert.match(byRole(widget.element, "summary").textContent, /^1 skill · 2 references · ≈ 3\.5 KiB of 256 KiB$/);
});

test("installs a compact picker after the skills widget plus a nonserialized report", async () => {
  const { node, skillsWidget, options } = graphNode();
  const widget = installPromptAssistant(node, options);
  assert.equal(installPromptAssistant(node, options), widget);
  assert.equal(node.widgets.indexOf(widget), node.widgets.indexOf(skillsWidget) + 1);
  assert.equal(widget.serialize, false);
  assert.equal(node.widgets.at(-1), widget.lfggReport);
  assert.equal(widget.lfggReport.serialize, false);
  assert.equal(byRole(widget.element, "disclosure").textContent, "Expand");
  assert.equal(byRole(widget.element, "skill-list").hidden, true);
  assert.equal(byRole(widget.element, "summary").textContent, "Loading skills…");
  assert.equal(descendants(widget.element).filter(({ className }) => className === "lfgg-identity").length, 1);
  const report = byRole(widget.lfggReport.element, "report");
  assert.equal(report.textContent, "Run to generate a prompt");
  assert.equal(report.role, "region");
  assert.match(report.style.fontFamily, /monospace/);
  assert.equal(report.style.userSelect, "text");

  await widget.lfggReady;
  assert.equal(byRole(widget.element, "summary").textContent, "0 skills · 0 references · ≈ 0 B of 256 KiB");
  assert.equal(byRole(widget.element, "skills-status").textContent, "2 available · 1 missing");

  const serialized = { widgets_values: ["m", "r", "", "x", "server default", "share", 0, "y"] };
  node.onSerialize(serialized);
  assert.deepEqual(serialized.widgets_values, ["m", "r", "", "server default", "share", 0]);
  assert.equal(node.serializedCount, 1);
});

test("picker edits the skills text, preserves hand edits, and estimates size", async () => {
  const { node, skillsWidget, options } = graphNode({ skills: "custom-line" });
  const widget = installPromptAssistant(node, options);
  await widget.lfggReady;
  byRole(widget.element, "disclosure").dispatch("click");
  assert.equal(node.properties.lfgg_editor_expanded, true);
  assert.equal(byRole(widget.element, "disclosure")["aria-expanded"], "true");
  assert.equal(byRole(widget.element, "skill-list").hidden, false);
  assert.deepEqual(allByRole(widget.element, "skill").map((item) => item.dataset.name), [
    "scenario-maker-sdxl", "scenario-maker-wan", "scenario-maker-pony",
  ]);
  const pony = byRole(widget.element, "skill-toggle", "scenario-maker-pony");
  assert.equal(pony.disabled, true);
  assert.match(byRole(byRole(widget.element, "skill", "scenario-maker-pony"), "skill-hint").textContent, /unavailable · roots searched: \/home\/u\/.agents\/skills, C:\/Users\/u\/.agents\/skills/);
  assert.match(byRole(widget.element, "missing-roots").textContent, /C:\/Users\/u\/.agents\/skills/);

  const sdxl = byRole(widget.element, "skill-toggle", "scenario-maker-sdxl");
  sdxl.checked = true;
  sdxl.dispatch("change");
  assert.equal(skillsWidget.value, "custom-line\nscenario-maker-sdxl");
  assert.deepEqual(skillsWidget.callbackValues, ["custom-line\nscenario-maker-sdxl"]);
  assert.equal(skillsWidget.inputEl.value, skillsWidget.value);
  assert.match(byRole(widget.element, "summary").textContent, /^2 skills · 0 references · ≈ 2\.0 KiB of 256 KiB · unresolved: custom-line$/);

  byRole(widget.element, "files-toggle", "scenario-maker-sdxl").dispatch("click");
  const fileToggles = allByRole(widget.element, "file-toggle");
  assert.deepEqual(fileToggles.map((item) => item.dataset.id), [
    "scenario-maker-sdxl/references/models/sdxl.md",
    "scenario-maker-sdxl/references/routing.md",
  ]);
  fileToggles[1].checked = true;
  fileToggles[1].dispatch("change");
  assert.equal(skillsWidget.value, "custom-line\nscenario-maker-sdxl\nscenario-maker-sdxl/references/routing.md");
  byRole(widget.element, "all-files", "scenario-maker-sdxl").dispatch("click");
  assert.equal(
    skillsWidget.value,
    "custom-line\nscenario-maker-sdxl\nscenario-maker-sdxl/references/routing.md\nscenario-maker-sdxl/references/models/sdxl.md",
  );
  assert.match(byRole(widget.element, "summary").textContent, /2 references · ≈ 3\.5 KiB/);
  assert.equal(byRole(widget.element, "file-toggle", "scenario-maker-sdxl/references/models/sdxl.md").checked, true);

  const toggle = byRole(widget.element, "skill-toggle", "scenario-maker-sdxl");
  toggle.checked = false;
  toggle.dispatch("change");
  assert.equal(skillsWidget.value, "custom-line");

  skillsWidget.inputEl.value = "scenario-maker-wan";
  skillsWidget.inputEl.dispatch("input");
  assert.equal(skillsWidget.value, "scenario-maker-wan");
  assert.equal(byRole(widget.element, "skill-toggle", "scenario-maker-wan").checked, true);
});

test("reload restores disclosure, report, and locks connected inputs", async () => {
  const { node, skillsWidget, options } = graphNode({ skills: "scenario-maker-wan" });
  node.properties.lfgg_editor_expanded = true;
  node.outputs = { 7: { text: ["restored prompt"] } };
  node.inputs[2].link = 42;
  node.inputs[1].link = 43;
  const widget = installPromptAssistant(node, options);
  await widget.lfggReady;
  node.onConfigure({});

  assert.equal(byRole(widget.element, "skill-list").hidden, false);
  assert.equal(byRole(widget.element, "disclosure").textContent, "Collapse");
  assert.equal(byRole(widget.lfggReport.element, "report").textContent, "restored prompt");
  assert.equal(byRole(widget.lfggReport.element, "report-status").dataset.state, "current");
  assert.equal(byRole(widget.element, "locks").textContent, "Connected upstream: request, skills. Disconnect to edit here.");
  const wan = byRole(widget.element, "skill-toggle", "scenario-maker-wan");
  assert.equal(wan.checked, true);
  assert.equal(wan.disabled, true);
  wan.checked = false;
  wan.dispatch("change");
  assert.equal(skillsWidget.value, "scenario-maker-wan");

  node.inputs[2].link = null;
  node.inputs[1].link = null;
  node.onConnectionsChange();
  assert.equal(byRole(widget.element, "locks").hidden, true);
  assert.equal(byRole(widget.element, "skill-toggle", "scenario-maker-wan").disabled, false);

  const serialized = { widgets_values: ["m", "r", "scenario-maker-wan", "server default", "share", 0] };
  node.onSerialize(serialized);
  assert.deepEqual(serialized.widgets_values, ["m", "r", "scenario-maker-wan", "server default", "share", 0]);
  assert.equal(node.properties.lfgg_editor_expanded, true);
});

test("model refresh preserves a missing saved id and reports failures", async () => {
  let fail = false;
  const { node, options } = graphNode({
    model: "old-model",
    fetchModels: async () => {
      if (fail) throw new Error("Models are unavailable: cannot reach");
      return { mode: "single", models: [{ id: "a", status: "loaded" }] };
    },
  });
  const widget = installPromptAssistant(node, options);
  const modelWidget = node.widgets.find(({ name }) => name === "model");
  const status = byRole(widget.element, "model-status");
  assert.equal(status.dataset.missing, "true");
  assert.match(status.textContent, /saved model "old-model" is not listed/);

  byRole(widget.element, "refresh-models").dispatch("click");
  await widget.lfggModelsReady;
  assert.deepEqual(modelWidget.options.values, ["server default", "a"]);
  assert.equal(modelWidget.value, "old-model");
  assert.match(status.textContent, /^1 model · single-model mode · loaded: a · saved model "old-model" is not listed/);

  modelWidget.value = "a";
  fail = true;
  byRole(widget.element, "refresh-models").dispatch("click");
  await widget.lfggModelsReady;
  assert.deepEqual(modelWidget.options.values, ["server default", "a"]);
  assert.equal(status.textContent, "Models are unavailable: cannot reach");
  assert.equal(byRole(widget.element, "refresh-models").disabled, false);
});

test("skills refresh failure keeps the previous catalog and report tracks execution", async () => {
  let calls = 0;
  const { node, options } = graphNode({
    fetchSkills: async () => {
      calls += 1;
      if (calls > 1) throw new Error("Skills are unavailable: no config");
      return CATALOG;
    },
  });
  const widget = installPromptAssistant(node, options);
  await widget.lfggReady;
  byRole(widget.element, "refresh-skills").dispatch("click");
  await widget.lfggReady;
  assert.equal(byRole(widget.element, "skills-status").textContent, "Skills are unavailable: no config · showing previous skills.");
  assert.match(byRole(widget.element, "summary").textContent, /^0 skills/);

  const report = byRole(widget.lfggReport.element, "report");
  const reportStatus = byRole(widget.lfggReport.element, "report-status");
  node.onExecutionStart();
  assert.equal(reportStatus.dataset.state, "waiting");
  node.onExecuted({ text: ["a prompt"] });
  assert.equal(report.textContent, "a prompt");
  assert.equal(report.dataset.stale, "false");
  node.onExecutionStart();
  assert.equal(report.dataset.stale, "true");
  assert.equal(reportStatus.dataset.state, "stale");
  node.onExecutionError(new Error("x"));
  assert.equal(report.textContent, "a prompt");
  node.onExecuted({});
  assert.equal(reportStatus.dataset.state, "stale");
});

test("ignores other node classes and missing fetchers", () => {
  const { node, options } = graphNode();
  node.comfyClass = "Other";
  assert.equal(installPromptAssistant(node, options), undefined);
  assert.equal(node.widgets.length, 6);
  node.comfyClass = PROMPT_ASSISTANT_ID;
  assert.equal(installPromptAssistant(node, { document: documentStub }), undefined);
});
