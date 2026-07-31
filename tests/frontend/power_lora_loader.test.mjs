import assert from "node:assert/strict";
import test from "node:test";

import {
  ALL_LORAS,
  chooserChoices,
  folderChoices,
  installPowerLoraLoader,
} from "../../web/power_lora_loader.mjs";

const LORAS = [
  "characters/anime/hero.safetensors",
  "characters/photo.safetensors",
  "styles/ink.safetensors",
];
const SEPARATE_STRENGTHS = "Separate Model and Clip strength";

function fakeNode({
  loras = LORAS,
  folder = "characters",
  properties = {},
  comfyClass = "LFGG_PowerLoraLoaderFolder",
} = {}) {
  let folderCallbacks = 0;
  let addCallbacks = 0;
  let serializations = 0;
  const widgets = [
    {
      name: "folder",
      value: folder,
      options: { values: folderChoices(loras) },
      callback() {
        folderCallbacks += 1;
      },
    },
    {
      name: "lora_to_add",
      value: loras[0],
      options: { values: [...loras] },
      callback() {
        addCallbacks += 1;
      },
    },
  ];
  return {
    comfyClass,
    constructor: class FakeNode {},
    widgets,
    properties: { ...properties },
    pos: [100, 50],
    size: [320, 500],
    addCustomWidget(widget) {
      this.widgets.push(widget);
      return widget;
    },
    computeSize() {
      return [
        this.size[0],
        40 +
          this.widgets.reduce(
            (height, widget) =>
              height + (widget.computeSize?.(this.size[0])?.[1] ?? 20),
            0,
          ),
      ];
    },
    setSize(size) {
      this.size = size;
    },
    setDirtyCanvas() {
      this.dirty = (this.dirty ?? 0) + 1;
    },
    onSerialize() {
      serializations += 1;
    },
    folderCallbacks: () => folderCallbacks,
    addCallbacks: () => addCallbacks,
    serializations: () => serializations,
  };
}

function pointerAt(node, x, button = 0) {
  return {
    eDown: {
      button,
      canvasX: node.pos[0] + x,
      canvasY: node.pos[1],
    },
  };
}

test("filters recursively and shortens visible labels", () => {
  assert.deepEqual(folderChoices(LORAS), [
    ALL_LORAS,
    "characters",
    "characters/anime",
    "styles",
  ]);
  assert.deepEqual(
    chooserChoices(
      [
        "characters/anime/hero.safetensors",
        "characters/photo.safetensors",
      ],
      "characters",
    ),
    [
      {
        label: "anime/hero.safetensors",
        value: "characters/anime/hero.safetensors",
      },
      {
        label: "photo.safetensors",
        value: "characters/photo.safetensors",
      },
    ],
  );
});

test("supports all, nested, default, and empty folder choices", () => {
  assert.deepEqual(
    chooserChoices(LORAS, ALL_LORAS).map(({ label, value }) => [label, value]),
    LORAS.map((name) => [name, name]),
  );
  assert.deepEqual(chooserChoices(LORAS, "characters/anime"), [
    {
      label: "hero.safetensors",
      value: "characters/anime/hero.safetensors",
    },
  ]);
  assert.deepEqual(folderChoices([]), [ALL_LORAS]);

  const node = fakeNode({ folder: null });
  const controls = installPowerLoraLoader(node);
  assert.equal(controls.folder.value, "characters");

  const empty = fakeNode({ loras: [], folder: null });
  const emptyControls = installPowerLoraLoader(empty);
  assert.equal(emptyControls.folder.value, ALL_LORAS);
  assert.deepEqual(emptyControls.addWidget.options.values, []);
});

test("changing folders preserves existing rows and composes callbacks", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");

  controls.setFolder("styles");

  assert.deepEqual(controls.rows.map((row) => row.lora), [
    "characters/anime/hero.safetensors",
  ]);
  assert.deepEqual(controls.addWidget.options.values, [
    "styles/ink.safetensors",
  ]);
  assert.equal(
    controls.addWidget.options.getOptionLabel("styles/ink.safetensors"),
    "ink.safetensors",
  );
  assert.equal(node.folderCallbacks(), 1);

  controls.addWidget.callback("styles/ink.safetensors");
  assert.equal(node.addCallbacks(), 1);
});

test("edits rows and keeps unique sequential prompt keys", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  controls.add("characters/photo.safetensors");
  controls.add("characters/anime/hero.safetensors");
  assert.deepEqual(controls.rowWidgets.map((widget) => widget.name), [
    "lora_1",
    "lora_2",
    "lora_3",
  ]);

  controls.replace(0, "characters/photo.safetensors");
  controls.setEnabled(1, false);
  node.onPropertyChanged(SEPARATE_STRENGTHS, true);
  controls.setStrength(0, "model", 200);
  controls.setStrength(0, "clip", -200);
  controls.setStrength(0, "model", Number.POSITIVE_INFINITY);
  assert.deepEqual(controls.rows[0], {
    on: true,
    lora: "characters/photo.safetensors",
    strengthModel: 100,
    strengthClip: -100,
  });
  assert.equal(controls.rows[1].on, false);

  controls.toggleAll();
  assert.ok(controls.rows.every((row) => row.on));
  controls.toggleAll();
  assert.ok(controls.rows.every((row) => !row.on));

  controls.remove(1);
  assert.deepEqual(controls.rowWidgets.map((widget) => widget.name), [
    "lora_1",
    "lora_2",
  ]);
  assert.equal(controls.rowWidgets[0].computeSize()[1], 24);
  assert.equal(node.size[1], 500);
});

test("handles ComfyUI pointer clicks for toggles and strength prompts", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  const rowWidget = controls.rowWidgets[0];
  const prompts = [];
  const previousCanvas = globalThis.LGraphCanvas;
  globalThis.LGraphCanvas = {
    active_canvas: {
      prompt(label, value, apply) {
        prompts.push({ label, value });
        apply("0.25");
      },
    },
  };

  try {
    node.onPropertyChanged(SEPARATE_STRENGTHS, true);
    const toggle = pointerAt(node, 12);
    assert.equal(rowWidget.onPointerDown(toggle, node), true);
    toggle.onClick(toggle.eDown);
    assert.equal(controls.rows[0].on, false);

    const toggleAll = pointerAt(node, 12);
    assert.equal(controls.headerWidget.onPointerDown(toggleAll, node), true);
    toggleAll.onClick(toggleAll.eDown);
    assert.equal(controls.rows[0].on, true);

    const model = pointerAt(node, 170);
    assert.equal(rowWidget.onPointerDown(model, node), true);
    model.onClick(model.eDown);
    assert.deepEqual(prompts[0], { label: "Model strength", value: "1" });
    assert.equal(controls.rows[0].strengthModel, 0.25);

    const clip = pointerAt(node, 254);
    assert.equal(rowWidget.onPointerDown(clip, node), true);
    clip.onClick(clip.eDown);
    assert.deepEqual(prompts[1], { label: "CLIP strength", value: "1" });
    assert.equal(controls.rows[0].strengthClip, 0.25);
  } finally {
    globalThis.LGraphCanvas = previousCanvas;
  }
});

test("does not capture right-clicks on row controls", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  const pointer = pointerAt(node, 254, 2);

  assert.equal(controls.rowWidgets[0].onPointerDown(pointer, node), false);
  assert.equal(pointer.onClick, undefined);
});

test("opens row LoRA choices as a searchable combo menu", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  const menus = [];
  const previousLiteGraph = globalThis.LiteGraph;
  globalThis.LiteGraph = {
    ContextMenu: class {
      constructor(items, options) {
        menus.push({ items, options });
      }
    },
  };

  try {
    const pointer = pointerAt(node, 80);
    controls.rowWidgets[0].onPointerDown(pointer, node);
    pointer.onClick(pointer.eDown);

    assert.equal(menus.length, 1);
    assert.equal(menus[0].options.className, "dark");
    assert.deepEqual(
      menus[0].items.map(({ content }) => content),
      ["anime/hero.safetensors", "photo.safetensors"],
    );
    assert.equal(
      menus[0].options.callback(menus[0].items[1]),
      undefined,
    );
    assert.equal(
      controls.rows[0].lora,
      "characters/photo.safetensors",
    );
  } finally {
    globalThis.LiteGraph = previousLiteGraph;
  }
});

test("adds an off-by-default setting that controls separate strengths", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  let labels = [];
  const context = {
    fillText(text) {
      labels.push(text);
    },
  };

  controls.headerWidget.draw(context, node, node.size[0], 0);
  controls.rowWidgets[0].draw(context, node, node.size[0], 24);

  assert.deepEqual(node.constructor[`@${SEPARATE_STRENGTHS}`], {
    type: "boolean",
  });
  assert.equal(node.properties[SEPARATE_STRENGTHS], false);
  assert.ok(labels.includes("Strength"));
  assert.ok(!labels.includes("Model strength"));
  assert.ok(!labels.includes("CLIP strength"));
  assert.equal(labels.filter((label) => label === "◀").length, 1);
  assert.equal(labels.filter((label) => label === "▶").length, 1);
  assert.equal(labels.filter((label) => label === "1.00").length, 1);

  node.onPropertyChanged(SEPARATE_STRENGTHS, true);
  labels = [];
  controls.headerWidget.draw(context, node, node.size[0], 0);
  controls.rowWidgets[0].draw(context, node, node.size[0], 24);

  assert.ok(labels.includes("Model strength"));
  assert.ok(labels.includes("CLIP strength"));
  assert.equal(labels.filter((label) => label === "◀").length, 2);
  assert.equal(labels.filter((label) => label === "▶").length, 2);
  assert.equal(labels.filter((label) => label === "1.00").length, 2);
  assert.ok(!labels.includes("M 1"));
  assert.ok(!labels.includes("C 1"));
});

test("strength arrows adjust by 0.05 and keep direct entry", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  const rowWidget = controls.rowWidgets[0];

  const combinedDecrease = pointerAt(node, 210);
  rowWidget.onPointerDown(combinedDecrease, node);
  combinedDecrease.onClick(combinedDecrease.eDown);
  assert.equal(controls.rows[0].strengthModel, 0.95);
  assert.equal(controls.rows[0].strengthClip, 0.95);

  const combinedIncrease = pointerAt(node, 278);
  rowWidget.onPointerDown(combinedIncrease, node);
  combinedIncrease.onClick(combinedIncrease.eDown);
  assert.equal(controls.rows[0].strengthModel, 1);
  assert.equal(controls.rows[0].strengthClip, 1);

  node.onPropertyChanged(SEPARATE_STRENGTHS, true);
  const modelDecrease = pointerAt(node, 126);
  rowWidget.onPointerDown(modelDecrease, node);
  modelDecrease.onClick(modelDecrease.eDown);
  assert.equal(controls.rows[0].strengthModel, 0.95);

  const modelIncrease = pointerAt(node, 194);
  rowWidget.onPointerDown(modelIncrease, node);
  modelIncrease.onClick(modelIncrease.eDown);
  assert.equal(controls.rows[0].strengthModel, 1);

  const clipDecrease = pointerAt(node, 210);
  rowWidget.onPointerDown(clipDecrease, node);
  clipDecrease.onClick(clipDecrease.eDown);
  assert.equal(controls.rows[0].strengthClip, 0.95);

  const clipIncrease = pointerAt(node, 278);
  rowWidget.onPointerDown(clipIncrease, node);
  clipIncrease.onClick(clipIncrease.eDown);
  assert.equal(controls.rows[0].strengthClip, 1);
});

test("combines strengths by default and separates them when enabled", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");

  controls.setStrength(0, "model", 0.75);
  assert.equal(controls.rows[0].strengthModel, 0.75);
  assert.equal(controls.rows[0].strengthClip, 0.75);

  node.onPropertyChanged(SEPARATE_STRENGTHS, true);
  controls.setStrength(0, "clip", 0.25);
  assert.equal(controls.rows[0].strengthModel, 0.75);
  assert.equal(controls.rows[0].strengthClip, 0.25);

  node.onPropertyChanged(SEPARATE_STRENGTHS, false);
  assert.equal(controls.rows[0].strengthModel, 0.75);
  assert.equal(controls.rows[0].strengthClip, 0.75);
});

test("persists the separate-strength setting", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  node.onPropertyChanged(SEPARATE_STRENGTHS, true);
  const serialized = { widgets_values: [] };

  node.onSerialize(serialized);

  assert.equal(node.properties[SEPARATE_STRENGTHS], true);
  assert.equal(serialized.properties[SEPARATE_STRENGTHS], true);

  const restored = fakeNode({
    properties: {
      [SEPARATE_STRENGTHS]: true,
      lfgg_lora_rows: [],
    },
  });
  const restoredControls = installPowerLoraLoader(restored, { restore: true });
  assert.equal(restoredControls.separateStrengths, true);
});

test("migrates the saved linked-strength option", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  node.properties = {
    lfgg_link_strengths: false,
    lfgg_lora_rows: [],
  };

  installPowerLoraLoader(node, { restore: true });

  assert.equal(controls.separateStrengths, true);
  assert.equal(node.properties[SEPARATE_STRENGTHS], true);
  assert.equal("lfgg_link_strengths" in node.properties, false);
});

test("colors toggles and darkens disabled rows", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  const text = [];
  const fills = [];
  const context = {
    fillRect() {
      fills.push(this.fillStyle);
    },
    strokeRect() {},
    fillText(value) {
      text.push({ value, color: this.fillStyle });
    },
  };

  controls.rowWidgets[0].draw(context, node, node.size[0], 24);
  assert.ok(text.some(({ value, color }) => value === "●" && color === "#66bb6a"));

  controls.setEnabled(0, false);
  controls.rowWidgets[0].draw(context, node, node.size[0], 24);
  assert.ok(text.some(({ value, color }) => value === "●" && color === "#ef5350"));
  assert.ok(fills.includes("rgba(0, 0, 0, 0.35)"));
});

test("reorder renumbers prompt widgets without changing row values", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  controls.add("characters/photo.safetensors");

  controls.move(1, -1);

  assert.deepEqual(controls.rows.map((row) => row.lora), [
    "characters/photo.safetensors",
    "characters/anime/hero.safetensors",
  ]);
  assert.deepEqual(controls.rowWidgets.map((widget) => widget.name), [
    "lora_1",
    "lora_2",
  ]);
});

test("serializes exact backend rows without positional workflow values", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  controls.setStrength(0, "model", 0.75);
  const serializedRow = {
    on: true,
    lora: "characters/anime/hero.safetensors",
    strength_model: 0.75,
    strength_clip: 0.75,
  };

  assert.deepEqual(controls.rowWidgets[0].serializeValue(), serializedRow);
  assert.equal(controls.headerWidget.serialize, false);
  assert.equal(controls.footerWidget.serialize, false);

  const serialized = {
    widgets_values: ["characters", LORAS[0], null, serializedRow, null],
  };
  node.onSerialize(serialized);

  assert.equal(node.serializations(), 1);
  assert.deepEqual(node.properties.lfgg_lora_rows, [serializedRow]);
  assert.deepEqual(serialized.properties.lfgg_lora_rows, [serializedRow]);
  assert.equal(serialized.properties[SEPARATE_STRENGTHS], false);
  assert.deepEqual(serialized.widgets_values, ["characters", LORAS[0]]);
});

test("restores ordered rows on the loaded-node install and stays idempotent", () => {
  const savedRows = [
    {
      on: false,
      lora: "characters/photo.safetensors",
      strength_model: 0.25,
      strength_clip: 0.5,
    },
    {
      on: true,
      lora: "styles/ink.safetensors",
      strength_model: 1,
      strength_clip: 0,
    },
  ];
  const node = fakeNode({
    properties: {
      [SEPARATE_STRENGTHS]: true,
      lfgg_lora_rows: savedRows,
    },
  });
  const controls = installPowerLoraLoader(node);
  assert.deepEqual(controls.rows, []);

  assert.equal(
    installPowerLoraLoader(node, { restore: true }),
    controls,
  );
  assert.deepEqual(
    controls.rowWidgets.map((widget) => widget.serializeValue()),
    savedRows,
  );
  assert.equal(
    installPowerLoraLoader(node, { restore: true }),
    controls,
  );
  assert.equal(controls.rowWidgets.length, 2);
  assert.equal(
    node.widgets.filter((widget) => widget.name === "lfgg_lora_header").length,
    1,
  );
  assert.deepEqual(node.constructor[`@${SEPARATE_STRENGTHS}`], {
    type: "boolean",
  });
});

test("preserves a missing saved folder and exposes no add choices", () => {
  const savedRows = [
    {
      on: true,
      lora: "missing/old.safetensors",
      strength_model: 1,
      strength_clip: 1,
    },
  ];
  const node = fakeNode({
    folder: "missing",
    properties: { lfgg_lora_rows: savedRows },
  });

  const controls = installPowerLoraLoader(node, { restore: true });

  assert.equal(controls.folder.value, "missing");
  assert.ok(controls.folder.options.values.includes("missing"));
  assert.equal(controls.folder.options.getOptionLabel("missing"), "missing (missing)");
  assert.deepEqual(controls.addWidget.options.values, []);
  assert.deepEqual(controls.rowWidgets[0].serializeValue(), savedRows[0]);
});

test("centers the add footer when ComfyUI reports zero custom width", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  const calls = [];
  const context = {
    fillText(...args) {
      calls.push(args);
    },
  };

  controls.footerWidget.draw(context, node, 0, 20);

  assert.deepEqual(calls[0], ["Add LoRA", node.size[0] / 2, 32]);
});

test("uses the current node width when custom widget widths are stale", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  node.size[0] = 400;
  const fills = [];
  const labels = [];
  const context = {
    fillRect(...args) {
      fills.push(args);
    },
    strokeRect() {},
    fillText(...args) {
      labels.push(args);
    },
  };

  controls.rowWidgets[0].draw(context, node, 320, 0);
  controls.headerWidget.draw(context, node, 320, 24);
  controls.footerWidget.draw(context, node, 320, 48);

  assert.deepEqual(fills[0], [10, 0, 380, 24]);
  assert.deepEqual(
    labels.find(([label]) => label === "Strength"),
    ["Strength", 324, 36],
  );
  assert.equal(
    labels.find(([label]) => label === "anime/hero.safetensors")[1],
    38,
  );
  assert.equal(labels.find(([label]) => label === "⋮")[1], 378);
  assert.deepEqual(
    labels.find(([label]) => label === "Add LoRA"),
    ["Add LoRA", 200, 60],
  );
});

test("ignores unrelated node classes", () => {
  assert.equal(
    installPowerLoraLoader(fakeNode({ comfyClass: "OtherNode" })),
    undefined,
  );
});
