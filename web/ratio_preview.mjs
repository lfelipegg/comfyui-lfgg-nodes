const NODE_ID = "LFGG_DimensionsByAspectRatio";
const PREVIEW_HEIGHT = 120;
const installedPreview = Symbol("lfggRatioPreview");
const PANEL_INSET = 8;
const PANEL_PADDING = 12;
const LABEL_HEIGHT = 32;
const CORNER_RADIUS = 6;

function greatestCommonDivisor(left, right) {
  while (right) {
    [left, right] = [right, left % right];
  }
  return left;
}

export function fitRatio(ratioWidth, ratioHeight, bounds) {
  const scale = Math.min(
    bounds.width / ratioWidth,
    bounds.height / ratioHeight,
  );
  const width = ratioWidth * scale;
  const height = ratioHeight * scale;
  return {
    x: bounds.x + (bounds.width - width) / 2,
    y: bounds.y + (bounds.height - height) / 2,
    width,
    height,
  };
}

function linked(node, name) {
  return node.inputs?.some((input) => input.name === name && input.link != null);
}

function resize(node, allowShrink) {
  const [, minimumHeight] = node.computeSize();
  node.setSize([
    node.size[0],
    allowShrink ? minimumHeight : Math.max(node.size[1], minimumHeight),
  ]);
}

function composeCallback(widget, update) {
  const original = widget.callback;
  widget.callback = function (...args) {
    const result = original?.apply(this, args);
    update(true);
    return result;
  };
}

function roundedRectangle(ctx, rectangle) {
  ctx.beginPath();
  ctx.roundRect(
    rectangle.x,
    rectangle.y,
    rectangle.width,
    rectangle.height,
    CORNER_RADIUS,
  );
}

function drawPreview(ctx, preview, width, y, lowQuality) {
  const state = preview.getState();
  const theme = globalThis.LiteGraph ?? {};
  const colors = {
    panel: theme.WIDGET_BGCOLOR ?? "#222222",
    outline: theme.WIDGET_OUTLINE_COLOR ?? "#666666",
    text: theme.WIDGET_TEXT_COLOR ?? "#dddddd",
  };
  const panel = {
    x: PANEL_INSET,
    y: y + 2,
    width: Math.max(1, width - PANEL_INSET * 2),
    height: PREVIEW_HEIGHT - 4,
  };

  if (!lowQuality) {
    ctx.save();
    roundedRectangle(ctx, panel);
    ctx.fillStyle = colors.panel;
    ctx.fill();
    ctx.strokeStyle = colors.outline;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
  }

  if (state.kind !== "ratio") {
    if (!lowQuality) {
      ctx.fillStyle = colors.text;
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(
        state.label,
        panel.x + panel.width / 2,
        panel.y + panel.height / 2,
      );
    }
    return;
  }

  const content = {
    x: panel.x + PANEL_PADDING,
    y: panel.y + PANEL_PADDING,
    width: Math.max(1, panel.width - PANEL_PADDING * 2),
    height: Math.max(1, panel.height - PANEL_PADDING * 2),
  };
  let shape = fitRatio(state.width, state.height, content);

  ctx.font = "600 14px sans-serif";
  const ratioLabelWidth = ctx.measureText(state.label).width;
  ctx.font = "12px sans-serif";
  const orientationWidth = ctx.measureText(state.orientation).width;
  const labelsFit =
    shape.width >= Math.max(ratioLabelWidth, orientationWidth) + 16 &&
    shape.height >= 40;
  if (!labelsFit) {
    shape = fitRatio(state.width, state.height, {
      ...content,
      height: Math.max(1, content.height - LABEL_HEIGHT),
    });
  }

  if (lowQuality) {
    roundedRectangle(ctx, shape);
    ctx.strokeStyle = colors.outline;
    ctx.lineWidth = 1;
    ctx.stroke();
    return;
  }

  ctx.save();
  roundedRectangle(ctx, shape);
  ctx.globalAlpha = 0.18;
  ctx.fillStyle = colors.outline;
  ctx.fill();
  ctx.clip();
  ctx.beginPath();
  for (let index = 1; index < 6; index += 1) {
    const x = shape.x + (shape.width * index) / 6;
    const gridY = shape.y + (shape.height * index) / 6;
    ctx.moveTo(x, shape.y);
    ctx.lineTo(x, shape.y + shape.height);
    ctx.moveTo(shape.x, gridY);
    ctx.lineTo(shape.x + shape.width, gridY);
  }
  ctx.globalAlpha = 0.35;
  ctx.strokeStyle = colors.outline;
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();

  roundedRectangle(ctx, shape);
  ctx.strokeStyle = colors.outline;
  ctx.lineWidth = 1;
  ctx.stroke();

  const centerX = labelsFit
    ? shape.x + shape.width / 2
    : panel.x + panel.width / 2;
  const ratioY = labelsFit
    ? shape.y + shape.height / 2 - 8
    : content.y + content.height - LABEL_HEIGHT / 2 - 6;
  ctx.fillStyle = colors.text;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = "600 14px sans-serif";
  ctx.fillText(state.label, centerX, ratioY);
  ctx.font = "12px sans-serif";
  ctx.globalAlpha = 0.75;
  ctx.fillText(state.orientation, centerX, ratioY + 17);
  ctx.globalAlpha = 1;
}

export function installRatioPreview(
  node,
  { isConfiguring = () => false } = {},
) {
  if (node.comfyClass !== NODE_ID) {
    return undefined;
  }
  if (node[installedPreview]) {
    node[installedPreview].isConfiguring = isConfiguring;
    node[installedPreview].update(false);
    return node[installedPreview].widget;
  }

  const byName = (name) => node.widgets?.find((widget) => widget.name === name);
  const aspectRatio = byName("aspect_ratio");
  const customWidth = byName("custom_ratio_width");
  const customHeight = byName("custom_ratio_height");
  if (!aspectRatio || !customWidth || !customHeight) {
    return undefined;
  }

  const preview = {
    type: "lfgg_ratio_preview",
    name: "lfgg_ratio_preview",
    serialize: false,
    options: { serialize: false },
    computeSize: () => [0, PREVIEW_HEIGHT],
    draw: (ctx, _node, width, y, _height, lowQuality) =>
      drawPreview(ctx, preview, width, y, lowQuality),
    getState: () => {
      const aspectDynamic = linked(node, "aspect_ratio");
      const customDynamic =
        aspectRatio.value === "Custom" &&
        (linked(node, "custom_ratio_width") ||
          linked(node, "custom_ratio_height"));
      return previewState(
        aspectRatio.value,
        customWidth.value,
        customHeight.value,
        aspectDynamic || customDynamic,
      );
    },
  };
  node.addCustomWidget(preview);
  node.widgets.splice(node.widgets.indexOf(preview), 1);
  node.widgets.splice(node.widgets.indexOf(aspectRatio) + 1, 0, preview);

  const controller = {
    widget: preview,
    update: undefined,
    isConfiguring,
  };
  const update = (shrink) => {
    const showCustom =
      aspectRatio.value === "Custom" || linked(node, "aspect_ratio");
    customWidth.hidden = !showCustom;
    customHeight.hidden = !showCustom;
    resize(node, shrink && !controller.isConfiguring());
    node.setDirtyCanvas?.(true, true);
  };
  controller.update = update;
  node[installedPreview] = controller;

  for (const widget of [aspectRatio, customWidth, customHeight]) {
    composeCallback(widget, update);
  }
  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function (...args) {
    const result = originalConnectionsChange?.apply(this, args);
    update(true);
    return result;
  };
  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    // Frontend 1.45 leaves a positional hole for skipped mid-list widgets.
    if (
      Array.isArray(serialized.widgets_values) &&
      serialized.widgets_values.length === node.widgets.length
    ) {
      serialized.widgets_values.splice(node.widgets.indexOf(preview), 1);
    }
    return result;
  };

  update(false);
  return preview;
}

export function previewState(
  aspectRatio,
  customWidth,
  customHeight,
  dynamic = false,
) {
  if (dynamic) {
    return { kind: "dynamic", label: "Dynamic ratio" };
  }

  const [rawWidth, rawHeight] =
    aspectRatio === "Custom"
      ? [customWidth, customHeight]
      : String(aspectRatio).split(":").map(Number);
  if (
    !Number.isInteger(rawWidth) ||
    !Number.isInteger(rawHeight) ||
    rawWidth <= 0 ||
    rawHeight <= 0
  ) {
    return { kind: "invalid", label: "Invalid ratio" };
  }

  const divisor = greatestCommonDivisor(rawWidth, rawHeight);
  const width = rawWidth / divisor;
  const height = rawHeight / divisor;
  const orientation =
    width === height ? "Square" : width > height ? "Landscape" : "Portrait";
  return {
    kind: "ratio",
    width,
    height,
    label: `${width}:${height}`,
    orientation,
  };
}
