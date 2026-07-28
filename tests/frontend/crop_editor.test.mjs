import assert from "node:assert/strict";
import test from "node:test";

import {
  fitPreviewImage,
  buildInputViewUrl,
  initializeFrame,
  installCropEditor,
  moveFrame,
  normalizeTypedFrame,
  resizeFrame,
  resolveStaticInt,
} from "../../web/crop_editor.mjs";

test("initializes the largest centered exact frame", () => {
  assert.deepEqual(initializeFrame(1920, 1080, 4, 5), {
    x: 528,
    y: 0,
    width: 864,
    height: 1080,
    ratioWidth: 4,
    ratioHeight: 5,
  });
});

test("puts odd unused source pixels on the right and bottom", () => {
  assert.deepEqual(initializeFrame(4, 4, 3, 2), {
    x: 0,
    y: 1,
    width: 3,
    height: 2,
    ratioWidth: 3,
    ratioHeight: 2,
  });
});

test("contains the source image in a bounded preview", () => {
  assert.deepEqual(
    fitPreviewImage(1920, 1080, { x: 8, y: 10, width: 320, height: 360 }),
    { x: 8, y: 100, width: 320, height: 180 },
  );
});

test("moves and clamps in source pixels", () => {
  assert.deepEqual(
    moveFrame({ x: 10, y: 10, width: 40, height: 20 }, 100, -100, 80, 60),
    { x: 40, y: 0, width: 40, height: 20 },
  );
});

test("normalizes typed width to the nearest positive reduced-ratio scale", () => {
  assert.deepEqual(
    normalizeTypedFrame(
      { x: 0, y: 0, width: 1, height: 1 },
      25,
      0,
      0,
      100,
      100,
      1920,
      1080,
    ),
    { x: 0, y: 0, width: 32, height: 18, ratioWidth: 16, ratioHeight: 9 },
  );
});

test("normalizes typed coordinates after clamping typed size", () => {
  assert.deepEqual(
    normalizeTypedFrame(
      { x: 95, y: 95, width: 10, height: 10 },
      200,
      95,
      95,
      100,
      100,
      1,
      1,
    ),
    { x: 0, y: 0, width: 100, height: 100, ratioWidth: 1, ratioHeight: 1 },
  );
});

test("resizes every corner around its opposite fixed anchor", () => {
  const frame = { x: 20, y: 20, width: 40, height: 20 };
  assert.deepEqual(resizeFrame(frame, "top-left", 10, 15, 100, 100, 2, 1), {
    x: 10,
    y: 15,
    width: 50,
    height: 25,
  });
  assert.deepEqual(resizeFrame(frame, "top-right", 70, 15, 100, 100, 2, 1), {
    x: 20,
    y: 15,
    width: 50,
    height: 25,
  });
  assert.deepEqual(resizeFrame(frame, "bottom-left", 10, 45, 100, 100, 2, 1), {
    x: 10,
    y: 20,
    width: 50,
    height: 25,
  });
  assert.deepEqual(resizeFrame(frame, "bottom-right", 70, 45, 100, 100, 2, 1), {
    x: 20,
    y: 20,
    width: 50,
    height: 25,
  });
});

test("clamps each corner resize at the source boundary", () => {
  const frame = { x: 20, y: 20, width: 40, height: 20 };
  assert.deepEqual(resizeFrame(frame, "top-left", -20, -20, 80, 60, 2, 1), {
    x: 0,
    y: 10,
    width: 60,
    height: 30,
  });
  assert.deepEqual(resizeFrame(frame, "top-right", 120, -20, 80, 60, 2, 1), {
    x: 20,
    y: 10,
    width: 60,
    height: 30,
  });
  assert.deepEqual(resizeFrame(frame, "bottom-left", -20, 100, 80, 60, 2, 1), {
    x: 0,
    y: 20,
    width: 60,
    height: 30,
  });
  assert.deepEqual(resizeFrame(frame, "bottom-right", 120, 100, 80, 60, 2, 1), {
    x: 20,
    y: 20,
    width: 60,
    height: 30,
  });
});

test("rejects an out-of-bounds frame before resizing", () => {
  assert.deepEqual(
    resizeFrame(
      { x: 90, y: 10, width: 20, height: 20 },
      "bottom-right",
      100,
      40,
      100,
      100,
      1,
      1,
    ),
    { kind: "invalid" },
  );
});

test("reduces ratios before fitting and reports invalid states", () => {
  assert.deepEqual(initializeFrame(1920, 1080, 1920, 1080), {
    x: 0,
    y: 0,
    width: 1920,
    height: 1080,
    ratioWidth: 16,
    ratioHeight: 9,
  });
  assert.deepEqual(initializeFrame(100, 100, 101, 1), {
    kind: "ratio-does-not-fit",
  });
  assert.deepEqual(initializeFrame(100, 100, 0, 1), { kind: "invalid" });
  assert.deepEqual(fitPreviewImage(0, 100, { x: 0, y: 0, width: 1, height: 1 }), {
    kind: "invalid",
  });
});

function graphWith(origin, nodes = [origin]) {
  return {
    links: { 1: [origin.id, 0, 99, 0, "INT"] },
    getNodeById(id) {
      return nodes.find((node) => node.id === id);
    },
  };
}

test("resolves an unlinked local integer widget", () => {
  assert.deepEqual(
    resolveStaticInt({ widgets: [{ name: "ratio_width", value: 4 }] }, "ratio_width"),
    { kind: "value", value: 4 },
  );
});

test("resolves a primitive integer through reroutes", () => {
  const primitive = { id: 1, type: "PrimitiveNode", widgets: [{ value: 4 }] };
  const rerouteA = { id: 2, type: "Reroute", inputs: [{ link: 1 }] };
  const rerouteB = { id: 3, type: "Reroute", inputs: [{ link: 2 }] };
  const graph = {
    links: {
      1: [1, 0, 2, 0, "INT"],
      2: [2, 0, 3, 0, "INT"],
      3: [3, 0, 99, 0, "INT"],
    },
    getNodeById(id) {
      return [primitive, rerouteA, rerouteB].find((node) => node.id === id);
    },
  };
  assert.deepEqual(
    resolveStaticInt({ inputs: [{ name: "ratio_width", link: 3 }] }, "ratio_width", graph),
    { kind: "value", value: 4 },
  );
});

test("does not guess arbitrary computed origins", () => {
  const computed = { id: 1, type: "Math", widgets: [{ value: 4 }] };
  assert.deepEqual(
    resolveStaticInt(
      { inputs: [{ name: "ratio_width", link: 1 }] },
      "ratio_width",
      graphWith(computed),
    ),
    { kind: "unresolved" },
  );
});

test("stops reroute cycles and rejects invalid widget values", () => {
  const reroute = { id: 1, type: "Reroute", inputs: [{ link: 1 }] };
  const graph = {
    links: { 1: [1, 0, 1, 0, "INT"] },
    getNodeById() {
      return reroute;
    },
  };
  assert.deepEqual(
    resolveStaticInt({ inputs: [{ name: "ratio_width", link: 1 }] }, "ratio_width", graph),
    { kind: "unresolved" },
  );
  assert.deepEqual(
    resolveStaticInt({ widgets: [{ name: "ratio_width", value: 1.5 }] }, "ratio_width"),
    { kind: "invalid" },
  );
});

function cropNode() {
  const callbackValues = [];
  const widgets = [
    { name: "image", value: "portrait.png", callback(value) { callbackValues.push(["image", value]); } },
    { name: "ratio_width", value: 1, callback(value) { callbackValues.push(["ratio_width", value]); } },
    { name: "ratio_height", value: 1, callback(value) { callbackValues.push(["ratio_height", value]); } },
    { name: "crop_x", value: 0, callback(value) { callbackValues.push(["crop_x", value]); } },
    { name: "crop_y", value: 0, callback(value) { callbackValues.push(["crop_y", value]); } },
    { name: "crop_width", value: 0, callback(value) { callbackValues.push(["crop_width", value]); } },
    { name: "crop_height", value: 0, callback(value) { callbackValues.push(["crop_height", value]); } },
  ];
  return {
    comfyClass: "LFGG_LoadAndCropImage",
    widgets,
    inputs: widgets.slice(1).map(({ name }) => ({ name, link: null })),
    size: [320, 160],
    addCustomWidget(widget) { this.widgets.push(widget); return widget; },
    computeSize() { return [this.size[0], 40 + this.widgets.reduce((total, widget) => total + (widget.computeSize?.()[1] ?? 20), 0)]; },
    setSize(size) { this.size = size; },
    setDirtyCanvas() { this.dirty = (this.dirty ?? 0) + 1; },
    onConnectInput() { this.connected = (this.connected ?? 0) + 1; return "previous"; },
    onExecuted() { this.executed = (this.executed ?? 0) + 1; },
    callbackValues,
  };
}

function loadedImage(width = 400, height = 200) {
  return {
    naturalWidth: width,
    naturalHeight: height,
    set src(_value) { this.onload?.(); },
  };
}

function cropContext() {
  const calls = [];
  return {
    calls,
    save() {}, restore() {}, beginPath() {}, stroke() {},
    fill() { calls.push(["handle"]); },
    drawImage(...args) { calls.push(["image", ...args]); },
    fillRect(...args) { calls.push(["dim", ...args]); },
    strokeRect(...args) { calls.push(["border", ...args]); },
    fillText(...args) { calls.push(["label", ...args]); },
  };
}

function dragEvent() {
  const callbacks = {};
  return {
    onDragStart(callback) { assert.equal(typeof callback, "function"); callbacks.start = callback; },
    onDrag(callback) { assert.equal(typeof callback, "function"); callbacks.drag = callback; },
    onDragEnd(callback) { assert.equal(typeof callback, "function"); callbacks.end = callback; },
    finally(callback) { assert.equal(typeof callback, "function"); callbacks.finally = callback; },
    move(position) { callbacks.start?.(); callbacks.drag?.(position); callbacks.end?.(); callbacks.finally?.(); },
  };
}

function installedCropNode(options = {}) {
  const node = cropNode();
  const preview = installCropEditor(node, {
    createImage: () => loadedImage(),
    buildViewUrl: (value) => `/view?filename=${value}`,
    getGraph: () => options.graph,
    isConfiguring: () => options.configuring ?? false,
  });
  return { node, preview };
}

function cropValues(node) {
  return ["crop_x", "crop_y", "crop_width", "crop_height"].map(
    (name) => node.widgets.find((widget) => widget.name === name).value,
  );
}

test("installs exactly one canvas after image and ignores other or incomplete nodes", () => {
  const { node, preview } = installedCropNode();
  assert.equal(node.widgets[1], preview);
  assert.equal(preview.serialize, false);
  assert.equal(preview.options.serialize, false);
  assert.deepEqual(preview.computeSize(), [0, 360]);
  assert.equal(node.widgets.find((widget) => widget.name === "crop_height").disabled, true);
  assert.equal(installCropEditor(node), preview);
  assert.equal(node.widgets.filter((widget) => widget.name === "lfgg_crop_editor").length, 1);
  assert.equal(installCropEditor({ comfyClass: "Other", widgets: [] }), undefined);
  assert.equal(installCropEditor({ comfyClass: "LFGG_LoadAndCropImage", widgets: [] }), undefined);
});

test("loads an image, initializes the crop, and preserves saved width and loading height", () => {
  const { node } = installedCropNode({ configuring: true });
  const image = node.widgets[0];
  image.callback(image.value);
  assert.deepEqual(cropValues(node), [100, 0, 200, 200]);
  assert.equal(node.size[0], 320);
  assert.ok(node.size[1] >= 160);
});

test("normalizes numeric edits once and resets for local, constant, and computed ratios", () => {
  const options = { graph: undefined };
  const { node, preview } = installedCropNode(options);
  node.widgets[0].callback("portrait.png");
  const width = node.widgets.find((widget) => widget.name === "crop_width");
  width.value = 137;
  width.callback(width.value);
  assert.deepEqual(cropValues(node), [100, 0, 137, 137]);
  assert.equal(node.callbackValues.filter(([name]) => name === "crop_width").length, 1);
  node.widgets.find((widget) => widget.name === "ratio_width").value = 2;
  node.widgets.find((widget) => widget.name === "ratio_width").callback(2);
  assert.deepEqual(cropValues(node), [0, 0, 400, 200]);
  options.graph = graphWith({ id: 1, type: "PrimitiveNode", widgets: [{ value: 2 }] });
  node.inputs.find((input) => input.name === "ratio_width").link = 1;
  node.onConnectionsChange?.();
  assert.deepEqual(cropValues(node), [0, 0, 400, 200]);
  node.inputs.find((input) => input.name === "ratio_height").link = 2;
  node.onConnectionsChange?.();
  assert.equal(preview.getState().label, "Run to resolve connected ratio");
});

test("applies execution crop data, composes connection rules, and serializes only persisted widgets", () => {
  const { node } = installedCropNode();
  node.widgets[0].callback("portrait.png");
  node.onExecuted({ crop: [{ ratio_width: 2, ratio_height: 1, x: 20, y: 0, width: 200, height: 100 }] });
  assert.deepEqual(["ratio_width", "ratio_height", "crop_x", "crop_y", "crop_width", "crop_height"].map((name) => node.widgets.find((widget) => widget.name === name).value), [2, 1, 20, 0, 200, 100]);
  assert.equal(node.executed, 1);
  assert.equal(node.onConnectInput(0, "INT", {}), "previous");
  assert.equal(node.connected, 1);
  assert.equal(node.onConnectInput(2, "INT", {}), false);
  assert.equal(node.connected, 2);
  const serialized = { widgets_values: ["portrait.png", null, 2, 1, 20, 0, 200, 100] };
  node.onSerialize(serialized);
  assert.deepEqual(serialized.widgets_values, ["portrait.png", 2, 1, 20, 0, 200, 100]);
});

test("draws image then four outside dims, border, handles, and label at normal quality", () => {
  const { node, preview } = installedCropNode();
  node.widgets[0].callback("portrait.png");
  const detailed = cropContext();
  const lowQuality = cropContext();
  preview.draw(detailed, node, 320, 20, 360, false);
  preview.draw(lowQuality, node, 320, 20, 360, true);
  assert.equal(detailed.calls[0][0], "image");
  assert.equal(detailed.calls.filter(([name]) => name === "dim").length, 4);
  assert.equal(detailed.calls.filter(([name]) => name === "border").length, 1);
  assert.equal(detailed.calls.filter(([name]) => name === "label").length, 1);
  assert.equal(detailed.calls.filter(([name]) => name === "handle").length, 4);
  assert.equal(detailed.calls.filter(([name]) => name === "dim").slice(-4).length, 4);
  assert.equal(lowQuality.calls.filter(([name]) => name === "label").length, 0);
  assert.equal(lowQuality.calls.filter(([name]) => name === "handle").length, 0);
  assert.equal(lowQuality.calls.filter(([name]) => name === "border").length, 1);
});

test("moves from the interior and resizes from every corner handle", () => {
  const { node, preview } = installedCropNode();
  node.widgets[0].callback("portrait.png");
  preview.draw(cropContext(), node, 320, 20, 360, false);
  const initial = cropValues(node);
  const move = dragEvent();
  assert.equal(preview.onPointerDown(move, { x: 160, y: 220 }), true);
  move.move({ x: 180, y: 220 });
  assert.notDeepEqual(cropValues(node), initial);
  for (const point of [{ x: 84, y: 140 }, { x: 236, y: 140 }, { x: 84, y: 292 }, { x: 236, y: 292 }]) {
    node.widgets[0].callback("portrait.png");
    preview.draw(cropContext(), node, 320, 20, 360, false);
    const drag = dragEvent();
    assert.equal(preview.onPointerDown(drag, point), true);
    drag.move({ x: 20, y: 120 });
  }
  assert.equal(preview.onPointerDown(dragEvent(), { x: 1, y: 1 }), false);
});

test("rejects execution crops that overflow the source right or bottom edge", () => {
  const { node } = installedCropNode();
  node.widgets[0].callback("portrait.png");
  const original = cropValues(node);
  node.onExecuted({ crop: [{ ratio_width: 1, ratio_height: 1, x: 201, y: 0, width: 200, height: 200 }] });
  node.onExecuted({ crop: [{ ratio_width: 1, ratio_height: 1, x: 0, y: 1, width: 200, height: 200 }] });
  assert.deepEqual(cropValues(node), original);
  assert.equal(node.executed, 2);
});

test("keeps execution-resolved dynamic ratios editable until the connection changes", () => {
  const options = { graph: graphWith({ id: 1, type: "Math", widgets: [{ value: 2 }] }) };
  const { node, preview } = installedCropNode(options);
  node.widgets[0].callback("portrait.png");
  node.inputs.find((input) => input.name === "ratio_width").link = 1;
  node.inputs.find((input) => input.name === "ratio_height").link = 1;
  node.onConnectionsChange();
  assert.equal(preview.getState().label, "Run to resolve connected ratio");
  assert.equal(node.widgets.find((widget) => widget.name === "crop_width").disabled, true);
  node.onExecuted({ crop: [{ ratio_width: 2, ratio_height: 1, x: 0, y: 0, width: 400, height: 200 }] });
  assert.equal(preview.getState().kind, "ready");
  assert.equal(node.widgets.find((widget) => widget.name === "crop_width").disabled, false);
  assert.equal(node.widgets.find((widget) => widget.name === "crop_height").disabled, true);
  node.onConnectionsChange();
  assert.equal(preview.getState().label, "Run to resolve connected ratio");
  assert.equal(node.widgets.find((widget) => widget.name === "crop_width").disabled, true);
});

test("normalizes annotated input names into a confined view query", () => {
  assert.equal(
    buildInputViewUrl("nested\\photo name.png [input]"),
    "/view?filename=photo+name.png&subfolder=nested&type=input",
  );
  assert.equal(
    buildInputViewUrl("photo.png [input] extra"),
    "/view?filename=photo.png+%5Binput%5D+extra&subfolder=&type=input",
  );
});
