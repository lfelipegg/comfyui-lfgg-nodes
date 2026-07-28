import assert from "node:assert/strict";
import test from "node:test";

import {
  fitRatio,
  installRatioPreview,
  previewState,
} from "../../web/ratio_preview.mjs";

function fakeNode() {
  let callbackCalls = 0;
  const callbackValues = [];
  let connectionCalls = 0;
  const widgets = [
    {
      name: "aspect_ratio",
      value: "16:9",
      callback(value) {
        callbackCalls += 1;
        callbackValues.push(value);
      },
    },
    { name: "long_side", value: 1024 },
    { name: "divisible_by", value: 8 },
    { name: "custom_ratio_width", value: 3 },
    { name: "custom_ratio_height", value: 4 },
  ];
  return {
    comfyClass: "LFGG_DimensionsByAspectRatio",
    widgets,
    inputs: [],
    size: [320, 100],
    addCustomWidget(widget) {
      this.widgets.push(widget);
      return widget;
    },
    computeSize() {
      return [
        this.size[0],
        30 +
          this.widgets.reduce(
            (height, widget) =>
              height +
              (widget.hidden ? 0 : (widget.computeSize?.(this.size[0])[1] ?? 20)),
            0,
          ),
      ];
    },
    setSize(size) {
      this.size = size;
    },
    setDirtyCanvas() {},
    onConnectionsChange() {
      connectionCalls += 1;
    },
    callbackCalls: () => callbackCalls,
    callbackValues,
    connectionCalls: () => connectionCalls,
  };
}

function recordingContext() {
  const calls = [];
  return {
    calls,
    save() {},
    restore() {},
    beginPath() {},
    roundRect(...args) {
      calls.push(["roundRect", ...args]);
    },
    fill() {
      calls.push(["fill"]);
    },
    stroke() {
      calls.push(["stroke"]);
    },
    clip() {
      calls.push(["clip"]);
    },
    moveTo(...args) {
      calls.push(["moveTo", ...args]);
    },
    lineTo(...args) {
      calls.push(["lineTo", ...args]);
    },
    fillText(...args) {
      calls.push(["fillText", ...args]);
    },
    measureText(text) {
      return { width: text.length * 7 };
    },
  };
}

test("simplifies a custom ratio and identifies its orientation", () => {
  assert.deepEqual(previewState("Custom", 1920, 1080), {
    kind: "ratio",
    width: 16,
    height: 9,
    label: "16:9",
    orientation: "Landscape",
  });
});

test("uses the selected preset ratio", () => {
  assert.deepEqual(previewState("9:16", 1, 1), {
    kind: "ratio",
    width: 9,
    height: 16,
    label: "9:16",
    orientation: "Portrait",
  });
});

test("identifies a square ratio", () => {
  assert.equal(previewState("1:1", 3, 4).orientation, "Square");
});

test("reports an invalid custom ratio without throwing", () => {
  assert.deepEqual(previewState("Custom", 0, 4), {
    kind: "invalid",
    label: "Invalid ratio",
  });
});

test("reports a dynamic ratio instead of stale geometry", () => {
  assert.deepEqual(previewState("16:9", 1, 1, true), {
    kind: "dynamic",
    label: "Dynamic ratio",
  });
});

test("contains ratios within the available preview bounds", () => {
  assert.deepEqual(fitRatio(16, 9, { x: 10, y: 20, width: 160, height: 120 }), {
    x: 10,
    y: 35,
    width: 160,
    height: 90,
  });
  assert.deepEqual(fitRatio(9, 16, { x: 10, y: 20, width: 160, height: 120 }), {
    x: 56.25,
    y: 20,
    width: 67.5,
    height: 120,
  });
});

test("installs a derived preview and conditionally hides custom controls", () => {
  const node = fakeNode();
  const preview = installRatioPreview(node);
  const ratio = node.widgets.find((widget) => widget.name === "aspect_ratio");
  const customWidth = node.widgets.find(
    (widget) => widget.name === "custom_ratio_width",
  );
  const customHeight = node.widgets.find(
    (widget) => widget.name === "custom_ratio_height",
  );

  assert.equal(node.widgets[1], preview);
  assert.equal(preview.serialize, false);
  assert.equal(preview.options.serialize, false);
  assert.deepEqual(preview.computeSize(), [0, 120]);
  assert.equal(customWidth.hidden, true);
  assert.equal(customHeight.hidden, true);
  assert.equal(customWidth.value, 3);
  assert.equal(customHeight.value, 4);
  assert.equal(node.size[0], 320);

  ratio.value = "Custom";
  ratio.callback("Custom");
  assert.equal(node.callbackCalls(), 1);
  assert.equal(customWidth.hidden, false);
  assert.equal(customHeight.hidden, false);
  assert.equal(node.size[0], 320);

  ratio.value = "16:9";
  ratio.callback("16:9");
  assert.equal(customWidth.hidden, true);
  assert.equal(customHeight.hidden, true);

  node.inputs = [{ name: "aspect_ratio", link: 7 }];
  node.onConnectionsChange();
  assert.equal(node.connectionCalls(), 1);
  assert.equal(customWidth.hidden, false);
  assert.equal(customHeight.hidden, false);
  assert.deepEqual(preview.getState(), {
    kind: "dynamic",
    label: "Dynamic ratio",
  });

  ratio.value = "Custom";
  node.inputs = [{ name: "custom_ratio_width", link: 8 }];
  node.onConnectionsChange();
  assert.deepEqual(preview.getState(), {
    kind: "dynamic",
    label: "Dynamic ratio",
  });
});

test("draws a fixed panel grid behind the ratio shape at legible detail", () => {
  const node = fakeNode();
  const preview = installRatioPreview(node);
  const detailed = recordingContext();
  const lowQuality = recordingContext();

  preview.draw(detailed, node, 320, 10, 20, false);
  preview.draw(lowQuality, node, 320, 10, 20, true);

  const shape = detailed.calls.filter(([name]) => name === "roundRect")[1];
  const gridMoves = detailed.calls.filter(([name]) => name === "moveTo");
  const gridLines = detailed.calls.filter(([name]) => name === "lineTo");
  assert.equal(gridLines.length, 10);
  assert.ok(gridMoves[1][1] < shape[1]);
  assert.ok(gridLines[1][1] > shape[1] + shape[3]);
  const firstGridLine = detailed.calls.findIndex(
    ([name]) => name === "lineTo",
  );
  const gridStroke = detailed.calls.findIndex(
    ([name], index) => index > firstGridLine && name === "stroke",
  );
  const shapeFill = detailed.calls.findIndex(
    ([name], index) => index > gridStroke && name === "fill",
  );
  assert.ok(gridStroke < shapeFill);
  assert.equal(
    detailed.calls.filter(([name]) => name === "clip").length,
    0,
  );
  assert.equal(
    detailed.calls.filter(([name]) => name === "fillText").length,
    2,
  );
  assert.equal(
    lowQuality.calls.filter(([name]) => name === "lineTo").length,
    0,
  );
  assert.equal(
    lowQuality.calls.filter(([name]) => name === "fillText").length,
    0,
  );
});

test("draws the fixed grid behind an invalid ratio label", () => {
  const node = fakeNode();
  node.widgets.find((widget) => widget.name === "aspect_ratio").value = "Custom";
  node.widgets.find(
    (widget) => widget.name === "custom_ratio_width",
  ).value = 0;
  const preview = installRatioPreview(node);
  const context = recordingContext();

  preview.draw(context, node, 320, 10, 20, false);

  assert.ok(
    context.calls.some(
      ([name, text]) => name === "fillText" && text === "Invalid ratio",
    ),
  );
  assert.equal(
    context.calls.filter(([name]) => name === "lineTo").length,
    10,
  );
});

test("draws the fixed grid behind a dynamic ratio label", () => {
  const node = fakeNode();
  node.inputs = [{ name: "aspect_ratio", link: 7 }];
  const preview = installRatioPreview(node);
  const context = recordingContext();

  preview.draw(context, node, 320, 10, 20, false);

  assert.ok(
    context.calls.some(
      ([name, text]) => name === "fillText" && text === "Dynamic ratio",
    ),
  );
  assert.equal(
    context.calls.filter(([name]) => name === "lineTo").length,
    10,
  );
});

test("shows descriptive selector labels while retaining raw values", () => {
  const node = fakeNode();
  installRatioPreview(node);
  const ratio = node.widgets.find((widget) => widget.name === "aspect_ratio");
  const expected = {
    "1:1": "1:1 — Square",
    "4:5": "4:5 — Social portrait",
    "5:4": "5:4 — Landscape print",
    "3:4": "3:4 — Portrait",
    "4:3": "4:3 — Standard landscape",
    "2:3": "2:3 — Poster",
    "3:2": "3:2 — Photography",
    "5:7": "5:7 — Portrait print",
    "7:5": "7:5 — Landscape print",
    "9:16": "9:16 — Vertical video",
    "16:9": "16:9 — Widescreen",
    "9:21": "9:21 — Phone wallpaper",
    "21:9": "21:9 — Ultrawide",
    Custom: "Custom — Custom ratio",
  };

  assert.deepEqual(
    Object.fromEntries(
      Object.keys(expected).map((value) => [
        value,
        ratio.options.getOptionLabel(value),
      ]),
    ),
    expected,
  );
  assert.equal(ratio.options.getOptionLabel("3:1"), "3:1");
  assert.equal(ratio.value, "16:9");

  ratio.value = "9:16";
  ratio.callback(ratio.value);
  assert.deepEqual(node.callbackValues, ["9:16"]);
  assert.equal(ratio.value, "9:16");
});

test("moves labels below a ratio shape when they cannot fit inside", () => {
  const node = fakeNode();
  const ratio = node.widgets.find((widget) => widget.name === "aspect_ratio");
  const customWidth = node.widgets.find(
    (widget) => widget.name === "custom_ratio_width",
  );
  const customHeight = node.widgets.find(
    (widget) => widget.name === "custom_ratio_height",
  );
  ratio.value = "Custom";
  customWidth.value = 100;
  customHeight.value = 1;
  const preview = installRatioPreview(node);
  const context = recordingContext();

  preview.draw(context, node, 320, 10, 20, false);

  const shape = context.calls.filter(([name]) => name === "roundRect")[1];
  const ratioLabel = context.calls.find(
    ([name, text]) => name === "fillText" && text === "100:1",
  );
  assert.ok(ratioLabel[3] > shape[2] + shape[4]);
});

test("keeps the existing five workflow widget values in their original order", () => {
  const node = fakeNode();
  node.onSerialize = (serialized) => {
    serialized.widgets_values[serialized.widgets_values.length - 1] = 99;
  };
  node.onConfigure = () => {
    node.widgets.find((widget) => widget.name === "aspect_ratio").value =
      "21:9";
  };
  installRatioPreview(node);
  const serialized = {
    widgets_values: ["16:9", null, 1024, 8, 3, 4],
  };

  node.onSerialize(serialized);
  assert.deepEqual(serialized.widgets_values, ["16:9", 1024, 8, 3, 99]);

  const alreadyCompact = {
    widgets_values: ["16:9", 1024, 8, 3, 4],
  };
  node.onSerialize(alreadyCompact);
  assert.deepEqual(alreadyCompact.widgets_values, ["16:9", 1024, 8, 3, 99]);

  node.onConfigure({ widgets_values: ["9:16", 768, 64, 5, 7] });
  assert.equal(
    node.widgets.find((widget) => widget.name === "aspect_ratio").value,
    "21:9",
  );
});

test("does not shrink saved node height while a workflow is configuring", () => {
  const node = fakeNode();
  let configuring = true;
  node.size = [320, 400];
  installRatioPreview(node, { isConfiguring: () => configuring });

  node.inputs = [{ name: "aspect_ratio", link: 7 }];
  node.onConnectionsChange();
  assert.deepEqual(node.size, [320, 400]);

  configuring = false;
  node.inputs = [];
  node.onConnectionsChange();
  assert.ok(node.size[1] < 400);
  assert.equal(node.size[0], 320);
});

test("reuses one preview and ignores incomplete or unrelated nodes", () => {
  const node = fakeNode();
  const preview = installRatioPreview(node);

  assert.equal(installRatioPreview(node), preview);
  assert.equal(
    node.widgets.filter((widget) => widget.name === "lfgg_ratio_preview")
      .length,
    1,
  );
  assert.equal(
    installRatioPreview({ comfyClass: "OtherNode", widgets: [] }),
    undefined,
  );
  assert.equal(
    installRatioPreview({
      comfyClass: "LFGG_DimensionsByAspectRatio",
      widgets: [],
    }),
    undefined,
  );
});
