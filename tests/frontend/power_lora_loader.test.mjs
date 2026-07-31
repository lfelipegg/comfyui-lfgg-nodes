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
    widgets,
    properties: { ...properties },
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
    strength_clip: 1,
  };

  assert.deepEqual(controls.rowWidgets[0].serializeValue(), serializedRow);
  assert.equal(controls.headerWidget.serialize, false);
  assert.equal(controls.footerWidget.serialize, false);

  const serialized = {
    widgets_values: ["characters", LORAS[0], serializedRow],
  };
  node.onSerialize(serialized);

  assert.equal(node.serializations(), 1);
  assert.deepEqual(node.properties.lfgg_lora_rows, [serializedRow]);
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
    properties: { lfgg_lora_rows: savedRows },
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

test("ignores unrelated node classes", () => {
  assert.equal(
    installPowerLoraLoader(fakeNode({ comfyClass: "OtherNode" })),
    undefined,
  );
});
