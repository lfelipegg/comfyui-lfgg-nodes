import assert from "node:assert/strict";
import test from "node:test";

import {
  fitPreviewImage,
  initializeFrame,
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
