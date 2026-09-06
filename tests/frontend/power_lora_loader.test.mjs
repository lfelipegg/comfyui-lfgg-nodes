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
  size = [320, 500],
  wrapCustomWidgets = false,
} = {}) {
  let folderCallbacks = 0;
  let addCallbacks = 0;
  let serializations = 0;
  let sizeChanges = 0;
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
    size: [...size],
    addCustomWidget(widget) {
      const concrete = wrapCustomWidgets
        ? Object.assign(Object.create({ concreteWidget: true }), widget, {
            store: {},
          })
        : widget;
      concrete.drawRequests = 0;
      concrete.triggerDraw = () => {
        concrete.drawRequests += 1;
      };
      this.widgets.push(concrete);
      return concrete;
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
    setSize(nextSize) {
      sizeChanges += 1;
      this.size = nextSize;
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
    sizeChanges: () => sizeChanges,
  };
}

function drawingContext(characterWidth = 7) {
  const text = [];
  const fills = [];
  const strokes = [];
  return {
    text,
    fills,
    strokes,
    measureText(value) {
      return { width: Array.from(String(value)).length * characterWidth };
    },
    fillText(value, x, y, maxWidth) {
      text.push({ value, x, y, maxWidth });
    },
    fillRect(x, y, width, height) {
      fills.push({ x, y, width, height });
    },
    strokeRect(x, y, width, height) {
      strokes.push({ x, y, width, height });
    },
  };
}

function drawWidget(widget, node, { reportedWidth = node.size[0], y = 0, characterWidth = 7 } = {}) {
  const context = drawingContext(characterWidth);
  widget.draw(context, node, reportedWidth, y);
  return context;
}

function pointerAt(node, x, y = 0, button = 0) {
  return {
    eDown: {
      button,
      canvasX: node.pos[0] + x,
      canvasY: node.pos[1] + y,
    },
  };
}

function clickVisible(widget, node, visible, button = 0) {
  if (visible.x < 6 || visible.x > (widget.width || node.size[0]) - 6) return false;
  const pointer = pointerAt(node, visible.x, visible.y, button);
  const captured = widget.onPointerDown(pointer, node);
  if (captured) pointer.onClick(pointer.eDown);
  return captured;
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
  assert.ok(controls.rowWidgets[0].computeSize()[1] >= 40);
  assert.equal(node.size[1], 500);
});

test("visible row targets toggle and open separate strength prompts", () => {
  const node = fakeNode({ size: [300, 500] });
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  node.onPropertyChanged(SEPARATE_STRENGTHS, true);
  const rowWidget = controls.rowWidgets[0];
  const rowDrawing = drawWidget(rowWidget, node, { y: 48 });
  const headerDrawing = drawWidget(controls.headerWidget, node, { y: 8 });
  const checkbox = rowDrawing.strokes.find(
    ({ width, height }) => width === 13 && height === 13,
  );
  const values = rowDrawing.text
    .filter(({ value }) => value === "1.00")
    .sort((left, right) => left.x - right.x);
  const toggleAll = headerDrawing.text.find(
    ({ value }) => value === "Toggle all",
  );
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
    assert.equal(
      clickVisible(rowWidget, node, {
        x: checkbox.x + checkbox.width / 2,
        y: checkbox.y + checkbox.height / 2,
      }),
      true,
    );
    assert.equal(controls.rows[0].on, false);

    assert.equal(
      clickVisible(controls.headerWidget, node, toggleAll),
      true,
    );
    assert.equal(controls.rows[0].on, true);

    assert.equal(clickVisible(rowWidget, node, values[0]), true);
    assert.deepEqual(prompts[0], { label: "Model strength", value: "1" });
    assert.equal(controls.rows[0].strengthModel, 0.25);

    assert.equal(clickVisible(rowWidget, node, values[1]), true);
    assert.deepEqual(prompts[1], { label: "CLIP strength", value: "1" });
    assert.equal(controls.rows[0].strengthClip, 0.25);
  } finally {
    globalThis.LGraphCanvas = previousCanvas;
  }
});

test("asynchronous native entry preserves strengths on cancellation", async () => {
  const previous = globalThis.comfyAPI;
  let respond;
  globalThis.comfyAPI = { app: { app: { extensionManager: { dialog: {
    prompt: () => new Promise(resolve => { respond = resolve; }),
  } } } } };
  try {
    const node = fakeNode();
    const controls = installPowerLoraLoader(node);
    controls.add("characters/anime/hero.safetensors");
    const widget = controls.rowWidgets[0];
    const value = drawWidget(widget, node).text.find(({ value }) => value === "1.00");
    clickVisible(widget, node, value);
    respond(null);
    await Promise.resolve();
    assert.equal(widget.serializeValue().strength_model, 1);
    assert.equal(widget.serializeValue().strength_clip, 1);

    clickVisible(widget, node, value);
    respond("0.25");
    await Promise.resolve();
    assert.equal(widget.serializeValue().strength_model, 0.25);
    assert.equal(widget.serializeValue().strength_clip, 0.25);
  } finally {
    globalThis.comfyAPI = previous;
  }
});

test("right-clicks and visible gaps do not capture or mutate a row", () => {
  const node = fakeNode({ size: [300, 500] });
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  node.onPropertyChanged(SEPARATE_STRENGTHS, true);
  const rowWidget = controls.rowWidgets[0];
  const drawing = drawWidget(rowWidget, node, { y: 48 });
  const menuTarget = drawing.text.find(({ value }) => value === "⋮");
  const leftArrows = drawing.text
    .filter(({ value }) => value === "◀")
    .sort((left, right) => left.x - right.x);
  const rightArrows = drawing.text
    .filter(({ value }) => value === "▶")
    .sort((left, right) => left.x - right.x);
  const before = controls.rowWidgets[0].serializeValue();

  assert.equal(clickVisible(rowWidget, node, menuTarget, 2), false);
  const gap = pointerAt(
    node,
    (rightArrows[0].x + leftArrows[1].x) / 2,
    rightArrows[0].y,
  );
  assert.equal(rowWidget.onPointerDown(gap, node), false);
  assert.equal(gap.onClick, undefined);
  assert.deepEqual(controls.rowWidgets[0].serializeValue(), before);
});

test("opens row LoRA choices in the native themed context menu", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  const rowWidget = controls.rowWidgets[0];
  const drawing = drawWidget(rowWidget, node, { y: 32 });
  const filename = drawing.text.find(
    ({ value }) => value === "hero.safetensors",
  );
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
    assert.equal(clickVisible(rowWidget, node, filename), true);
    assert.equal(menus.length, 1);
    assert.deepEqual(
      menus[0].items.map(({ content }) => content),
      ["anime/hero.safetensors", "photo.safetensors"],
    );
    menus[0].options.callback(menus[0].items[1]);
    assert.equal(
      controls.rows[0].lora,
      "characters/photo.safetensors",
    );
  } finally {
    globalThis.LiteGraph = previousLiteGraph;
  }
});

test("opens folder and add selectors as searchable combo menus", () => {
  const loras = [
    "a/one.safetensors",
    "b/two.safetensors",
    "c/three.safetensors",
    "d/four.safetensors",
    "e/five.safetensors",
  ];
  const node = fakeNode({ loras, folder: ALL_LORAS });
  const controls = installPowerLoraLoader(node);
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
    const folderPointer = pointerAt(node, 160);
    assert.equal(controls.folder.onPointerDown(folderPointer, node), true);
    folderPointer.onClick(folderPointer.eDown);
    assert.equal(menus[0].items.length, 6);
    assert.equal(menus[0].options.className, "dark", "enable ComfyUI's native list filter");
    menus[0].options.callback(menus[0].items[2]);
    assert.equal(controls.folder.value, "b");

    controls.setFolder(ALL_LORAS);
    const addPointer = pointerAt(node, 160);
    assert.equal(controls.addWidget.onPointerDown(addPointer, node), true);
    addPointer.onClick(addPointer.eDown);
    assert.equal(menus[1].items.length, 5);
    assert.equal(menus[1].options.className, "dark", "enable ComfyUI's native list filter");
    menus[1].options.callback(menus[1].items[4]);
    assert.equal(controls.addWidget.value, "e/five.safetensors");

    assert.equal(
      controls.folder.onPointerDown(pointerAt(node, 20), node),
      false,
    );
    assert.equal(
      controls.addWidget.onPointerDown(pointerAt(node, 300), node),
      false,
    );
  } finally {
    globalThis.LiteGraph = previousLiteGraph;
  }
});


test("strength arrows adjust by 0.05 and keep direct entry", () => {
  const node = fakeNode({ size: [300, 500] });
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  const rowWidget = controls.rowWidgets[0];

  let drawing = drawWidget(rowWidget, node, { y: 24 });
  let leftArrows = drawing.text.filter(({ value }) => value === "◀");
  let rightArrows = drawing.text.filter(({ value }) => value === "▶");
  assert.equal(clickVisible(rowWidget, node, leftArrows[0]), true);
  assert.equal(controls.rows[0].strengthModel, 0.95);
  assert.equal(controls.rows[0].strengthClip, 0.95);
  assert.equal(clickVisible(rowWidget, node, rightArrows[0]), true);
  assert.equal(controls.rows[0].strengthModel, 1);
  assert.equal(controls.rows[0].strengthClip, 1);

  node.onPropertyChanged(SEPARATE_STRENGTHS, true);
  drawing = drawWidget(rowWidget, node, { y: 24 });
  leftArrows = drawing.text
    .filter(({ value }) => value === "◀")
    .sort((left, right) => left.x - right.x);
  rightArrows = drawing.text
    .filter(({ value }) => value === "▶")
    .sort((left, right) => left.x - right.x);
  assert.equal(clickVisible(rowWidget, node, leftArrows[0]), true);
  assert.equal(controls.rows[0].strengthModel, 0.95);
  assert.equal(clickVisible(rowWidget, node, rightArrows[0]), true);
  assert.equal(controls.rows[0].strengthModel, 1);
  assert.equal(clickVisible(rowWidget, node, leftArrows[1]), true);
  assert.equal(controls.rows[0].strengthClip, 0.95);
  assert.equal(clickVisible(rowWidget, node, rightArrows[1]), true);
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

test("uses a checkbox state and keeps disabled row values readable", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  const rowWidget = controls.rowWidgets[0];

  let drawing = drawWidget(rowWidget, node, { y: 24 });
  assert.ok(
    drawing.strokes.some(
      ({ width, height }) => width === 13 && height === 13,
    ),
  );
  assert.ok(drawing.text.some(({ value }) => value === "✓"));

  controls.setEnabled(0, false);
  drawing = drawWidget(rowWidget, node, { y: 24 });
  assert.equal(drawing.text.some(({ value }) => value === "✓"), false);
  assert.ok(
    drawing.text.some(({ value }) => value === "hero.safetensors"),
  );
  assert.ok(drawing.text.some(({ value }) => value === "1.00"));
  assert.deepEqual(rowWidget.serializeValue(), {
    on: false,
    lora: "characters/anime/hero.safetensors",
    strength_model: 1,
    strength_clip: 1,
  });
  const disabledStrength = drawing.text.find(
    ({ value }) => value === "1.00",
  );
  const disabledName = drawing.text.find(
    ({ value }) => value === "hero.safetensors",
  );
  assert.equal(clickVisible(rowWidget, node, disabledStrength), false);
  assert.equal(clickVisible(rowWidget, node, disabledName), false);

  const checkbox = drawing.strokes.find(
    ({ width, height }) => width === 13 && height === 13,
  );
  clickVisible(rowWidget, node, {
    x: checkbox.x + checkbox.width / 2,
    y: checkbox.y + checkbox.height / 2,
  });
  assert.equal(controls.rows[0].on, true);
});

test("disambiguates duplicate basenames and exposes the full stored path", () => {
  const loras = [
    "characters/anime/shared.safetensors",
    "characters/photo/shared.safetensors",
  ];
  const node = fakeNode({ loras, size: [600, 500] });
  const controls = installPowerLoraLoader(node);
  controls.add(loras[0]);
  controls.add(loras[1]);

  const first = drawWidget(controls.rowWidgets[0], node, { y: 32 });
  const second = drawWidget(controls.rowWidgets[1], node, { y: 88 });
  assert.ok(first.text.some(({ value }) => value === "shared.safetensors"));
  assert.ok(
    first.text.some(({ value }) => value === "characters/anime"),
  );
  assert.ok(
    second.text.some(({ value }) => value === "characters/photo"),
  );

  const prompts = [];
  const previousCanvas = globalThis.LGraphCanvas;
  globalThis.LGraphCanvas = {
    active_canvas: {
      prompt(label, value) {
        prompts.push({ label, value });
      },
    },
  };
  try {
    const options = [];
    node.getExtraMenuOptions({}, options);
    options
      .find(item => item?.content === "Show LoRA 1 full path")
      .callback();
    assert.deepEqual(prompts, [
      { label: "Full LoRA path", value: loras[0] },
    ]);
    assert.deepEqual(controls.rows.map(({ lora }) => lora), loras);
  } finally {
    globalThis.LGraphCanvas = previousCanvas;
  }
});

test("shows folder context for a restored row outside the active folder", () => {
  const saved = {
    on: true,
    lora: "styles/ink.safetensors",
    strength_model: 0.5,
    strength_clip: 0.5,
  };
  const node = fakeNode({
    folder: "characters",
    properties: { lfgg_lora_rows: [saved] },
    size: [600, 500],
  });
  const controls = installPowerLoraLoader(node, { restore: true });
  const drawing = drawWidget(controls.rowWidgets[0], node, { y: 32 });

  assert.ok(drawing.text.some(({ value }) => value === "ink.safetensors"));
  assert.ok(drawing.text.some(({ value }) => value === "styles"));
  assert.deepEqual(controls.rowWidgets[0].serializeValue(), saved);
});

test("native node menu routes all row operations through the same state", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  controls.add("characters/photo.safetensors");
  const replacementMenus = [];
  let promptValue = "0.4";
  const previousLiteGraph = globalThis.LiteGraph;
  const previousCanvas = globalThis.LGraphCanvas;
  globalThis.LiteGraph = {
    ContextMenu: class {
      constructor(items, options) {
        replacementMenus.push({ items, options });
      }
    },
  };
  globalThis.LGraphCanvas = {
    active_canvas: {
      prompt(_label, _value, apply) {
        apply(promptValue);
      },
    },
  };
  const options = () => {
    const entries = [];
    node.getExtraMenuOptions({}, entries);
    return entries;
  };
  const action = (content) =>
    options().find((entry) => entry?.content === content);

  try {
    action("Add selected LoRA").callback();
    assert.equal(controls.rows.length, 3);

    action("Toggle all LoRAs").callback();
    assert.ok(controls.rows.every((row) => !row.on));
    action("Enable LoRA 1").callback();
    assert.equal(controls.rows[0].on, true);

    action("Set LoRA 1 strength").callback();
    assert.equal(controls.rows[0].strengthModel, 0.4);
    assert.equal(controls.rows[0].strengthClip, 0.4);

    node.onPropertyChanged(SEPARATE_STRENGTHS, true);
    promptValue = "0.25";
    action("Set LoRA 1 CLIP strength").callback();
    assert.equal(controls.rows[0].strengthModel, 0.4);
    assert.equal(controls.rows[0].strengthClip, 0.25);

    action("Replace LoRA 1").callback();
    const replacement = replacementMenus.at(-1);
    replacement.options.callback(replacement.items[1]);
    assert.equal(controls.rows[0].lora, "characters/photo.safetensors");

    const moved = controls.rows[0];
    action("Move LoRA 1 down").callback();
    assert.equal(controls.rows[1], moved);
    action("Remove LoRA 2").callback();
    assert.equal(controls.rows.includes(moved), false);
  } finally {
    globalThis.LiteGraph = previousLiteGraph;
    globalThis.LGraphCanvas = previousCanvas;
  }
});

test("a retained renderer slot follows reordered and removed rows", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  controls.add("characters/photo.safetensors");
  const slot = controls.rowWidgets[0];
  const toggleDisplayedRow = (filename) => {
    const drawing = drawWidget(slot, node, { y: 32 });
    assert.ok(drawing.text.some(({ value }) => value === filename));
    const checkbox = drawing.strokes.find(({ width, height }) => width === height);
    assert.equal(clickVisible(slot, node, {
      x: checkbox.x + checkbox.width / 2,
      y: checkbox.y + checkbox.height / 2,
    }), true);
  };

  controls.move(1, -1);
  toggleDisplayedRow("photo.safetensors");
  assert.deepEqual(controls.rowWidgets.map(widget => {
    const row = widget.serializeValue();
    return [row.lora, row.on];
  }), [
    ["characters/photo.safetensors", false],
    ["characters/anime/hero.safetensors", true],
  ]);

  controls.remove(0);
  toggleDisplayedRow("hero.safetensors");
  assert.equal(slot.serializeValue().lora, "characters/anime/hero.safetensors");
  assert.equal(slot.serializeValue().on, false);
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
    wrapCustomWidgets: true,
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
  assert.ok(
    controls.rowWidgets.every(
      (widget) => widget.concreteWidget && node.widgets.includes(widget),
    ),
  );
  assert.ok(controls.headerWidget.concreteWidget);
  assert.ok(controls.footerWidget.concreteWidget);
  const drawing = drawWidget(controls.rowWidgets[0], node, { y: 32 });
  const checkbox = drawing.strokes.find(
    ({ width, height }) => width === 13 && height === 13,
  );
  clickVisible(controls.rowWidgets[0], node, {
    x: checkbox.x + checkbox.width / 2,
    y: checkbox.y + checkbox.height / 2,
  });
  assert.equal(controls.rows[0].on, true);
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

test("clicks the visible Add LoRA target when reported width is zero", () => {
  const node = fakeNode();
  const controls = installPowerLoraLoader(node);
  const drawing = drawWidget(controls.footerWidget, node, {
    reportedWidth: 0,
    y: 20,
  });
  const add = drawing.text.find(({ value }) => value === "Add LoRA");

  assert.equal(clickVisible(controls.footerWidget, node, add), true);
  assert.deepEqual(controls.rows.map(({ lora }) => lora), [LORAS[0]]);
});

test("measures basename ellipsis without compressing the stored path", () => {
  const path =
    "characters/a_very_long_portrait_detail_filename_v2.safetensors";
  const node = fakeNode({ loras: [path], size: [300, 500] });
  const controls = installPowerLoraLoader(node);
  controls.add(path);
  const drawing = drawWidget(controls.rowWidgets[0], node, {
    y: 24,
    characterWidth: 8,
  });
  const filename = drawing.text.find(({ value }) => value.endsWith("…"));

  assert.ok(filename);
  assert.equal(filename.maxWidth, undefined);
  assert.equal(controls.rows[0].lora, path);
  assert.equal(controls.rowWidgets[0].serializeValue().lora, path);
});

test("hits actual legacy and Nodes 2.0 targets across stale widths and resize", () => {
  const node = fakeNode({ size: [600, 500] });
  const controls = installPowerLoraLoader(node);
  controls.add("characters/anime/hero.safetensors");
  node.onPropertyChanged(SEPARATE_STRENGTHS, true);
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
    rowWidget.width = 300;
    let drawing = drawWidget(rowWidget, node, {
      reportedWidth: 300,
      y: 64,
    });
    assert.equal(rowWidget.computeSize(300)[1], 40);
    const wideModel = drawing.text
      .filter(({ value }) => value === "1.00")
      .sort((left, right) => left.x - right.x)[0];
    const rowDraws = rowWidget.drawRequests;
    assert.equal(clickVisible(rowWidget, node, wideModel), true);
    assert.equal(controls.rows[0].strengthModel, 0.25);
    assert.ok(rowWidget.drawRequests > rowDraws);
    assert.ok(controls.headerWidget.drawRequests > 0);
    assert.ok(controls.footerWidget.drawRequests > 0);

    node.size[0] = 300;
    drawing = drawWidget(rowWidget, node, {
      reportedWidth: 600,
      y: 64,
    });
    assert.equal(rowWidget.computeSize(600)[1], 80);
    const stackedClip = drawing.text.find(({ value }) => value === "1.00");
    assert.equal(clickVisible(rowWidget, node, stackedClip), true);
    assert.equal(controls.rows[0].strengthClip, 0.25);

    node.size[0] = 600;
    rowWidget.y = 0;
    drawing = drawWidget(rowWidget, node, {
      reportedWidth: 300,
      y: 1,
    });
    assert.equal(rowWidget.computeSize(300)[1], 80);
    const clipDecrease = drawing.text
      .filter(({ value }) => value === "◀")
      .sort((left, right) => left.x - right.x)[1];
    const widgetCanvas = {};
    const graphCanvas = {};
    const pointer = {
      element: widgetCanvas,
      eDown: {
        button: 0,
        offsetX: clipDecrease.x,
        offsetY: clipDecrease.y,
        canvasX: node.pos[0] + 500,
        canvasY: node.pos[1] + 500,
      },
    };
    assert.equal(
      rowWidget.onPointerDown(pointer, node, { canvas: graphCanvas }),
      true,
    );
    pointer.onClick(pointer.eDown);
    assert.equal(controls.rows[0].strengthClip, 0.2);
    assert.equal(node.size[1], 500);
    assert.equal(node.sizeChanges(), 0);
  } finally {
    globalThis.LGraphCanvas = previousCanvas;
  }
});

test("ignores unrelated node classes", () => {
  assert.equal(
    installPowerLoraLoader(fakeNode({ comfyClass: "OtherNode" })),
    undefined,
  );
});
