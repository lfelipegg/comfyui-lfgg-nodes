import { fitRatio, greatestCommonDivisor } from "./ratio_preview.mjs";

const invalid = { kind: "invalid" };
const doesNotFit = { kind: "ratio-does-not-fit" };

function positiveInteger(value) {
  return Number.isInteger(value) && value > 0;
}

function ratio(sourceWidth, sourceHeight, ratioWidth, ratioHeight) {
  if (
    !positiveInteger(sourceWidth) ||
    !positiveInteger(sourceHeight) ||
    !positiveInteger(ratioWidth) ||
    !positiveInteger(ratioHeight)
  ) {
    return undefined;
  }
  const divisor = greatestCommonDivisor(ratioWidth, ratioHeight);
  const width = ratioWidth / divisor;
  const height = ratioHeight / divisor;
  const maximumScale = Math.min(
    Math.floor(sourceWidth / width),
    Math.floor(sourceHeight / height),
  );
  return maximumScale ? { width, height, maximumScale } : null;
}

function validFrame(frame) {
  return [frame?.x, frame?.y, frame?.width, frame?.height].every(Number.isInteger) &&
    frame.x >= 0 && frame.y >= 0 && frame.width > 0 && frame.height > 0;
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

export function fitPreviewImage(sourceWidth, sourceHeight, bounds) {
  if (
    !positiveInteger(sourceWidth) ||
    !positiveInteger(sourceHeight) ||
    !bounds ||
    ![bounds.x, bounds.y, bounds.width, bounds.height].every(Number.isFinite) ||
    bounds.width <= 0 ||
    bounds.height <= 0
  ) {
    return invalid;
  }
  return fitRatio(sourceWidth, sourceHeight, bounds);
}

export function initializeFrame(sourceWidth, sourceHeight, ratioWidth, ratioHeight) {
  const reduced = ratio(sourceWidth, sourceHeight, ratioWidth, ratioHeight);
  if (reduced === undefined) return invalid;
  if (reduced === null) return doesNotFit;
  const width = reduced.width * reduced.maximumScale;
  const height = reduced.height * reduced.maximumScale;
  return {
    x: Math.floor((sourceWidth - width) / 2),
    y: Math.floor((sourceHeight - height) / 2),
    width,
    height,
    ratioWidth: reduced.width,
    ratioHeight: reduced.height,
  };
}

export function moveFrame(frame, deltaX, deltaY, sourceWidth, sourceHeight) {
  if (
    !validFrame(frame) ||
    !positiveInteger(sourceWidth) ||
    !positiveInteger(sourceHeight) ||
    !Number.isFinite(deltaX) ||
    !Number.isFinite(deltaY) ||
    frame.width > sourceWidth ||
    frame.height > sourceHeight
  ) {
    return invalid;
  }
  return {
    x: clamp(Math.round(frame.x + deltaX), 0, sourceWidth - frame.width),
    y: clamp(Math.round(frame.y + deltaY), 0, sourceHeight - frame.height),
    width: frame.width,
    height: frame.height,
  };
}

export function normalizeTypedFrame(
  frame,
  typedWidth,
  typedX,
  typedY,
  sourceWidth,
  sourceHeight,
  ratioWidth,
  ratioHeight,
) {
  const reduced = ratio(sourceWidth, sourceHeight, ratioWidth, ratioHeight);
  if (reduced === undefined || !Number.isFinite(typedWidth)) return invalid;
  if (reduced === null) return doesNotFit;
  const scale = clamp(
    Math.max(1, Math.round(typedWidth / reduced.width)),
    1,
    reduced.maximumScale,
  );
  const width = scale * reduced.width;
  const height = scale * reduced.height;
  if (!Number.isFinite(typedX) || !Number.isFinite(typedY)) return invalid;
  return {
    x: clamp(Math.round(typedX), 0, sourceWidth - width),
    y: clamp(Math.round(typedY), 0, sourceHeight - height),
    width,
    height,
    ratioWidth: reduced.width,
    ratioHeight: reduced.height,
  };
}

export function resizeFrame(
  frame,
  corner,
  pointerX,
  pointerY,
  sourceWidth,
  sourceHeight,
  ratioWidth,
  ratioHeight,
) {
  if (!validFrame(frame) || !Number.isFinite(pointerX) || !Number.isFinite(pointerY)) {
    return invalid;
  }
  const reduced = ratio(sourceWidth, sourceHeight, ratioWidth, ratioHeight);
  if (reduced === undefined) return invalid;
  if (reduced === null) return doesNotFit;
  if (frame.x + frame.width > sourceWidth || frame.y + frame.height > sourceHeight) {
    return invalid;
  }
  const corners = {
    "top-left": [frame.x + frame.width, frame.y + frame.height, -1, -1],
    "top-right": [frame.x, frame.y + frame.height, 1, -1],
    "bottom-left": [frame.x + frame.width, frame.y, -1, 1],
    "bottom-right": [frame.x, frame.y, 1, 1],
  };
  const definition = corners[corner];
  if (!definition) return invalid;
  const [anchorX, anchorY, xDirection, yDirection] = definition;
  const xScale = ((pointerX - anchorX) * xDirection) / reduced.width;
  const yScale = ((pointerY - anchorY) * yDirection) / reduced.height;
  const requestedScale = Math.max(1, Math.round(Math.min(xScale, yScale)));
  const availableX = xDirection < 0 ? anchorX : sourceWidth - anchorX;
  const availableY = yDirection < 0 ? anchorY : sourceHeight - anchorY;
  const maximumScale = Math.min(
    Math.floor(availableX / reduced.width),
    Math.floor(availableY / reduced.height),
  );
  if (maximumScale < 1) return doesNotFit;
  const scale = Math.min(requestedScale, maximumScale);
  const width = scale * reduced.width;
  const height = scale * reduced.height;
  return {
    x: xDirection < 0 ? anchorX - width : anchorX,
    y: yDirection < 0 ? anchorY - height : anchorY,
    width,
    height,
  };
}

function graphLink(graph, linkId) {
  return graph?.links?.[linkId] ?? graph?.links?.get?.(linkId);
}

function originId(link) {
  return Array.isArray(link) ? link[0] : link?.origin_id;
}

function nodeById(graph, id) {
  return graph?.getNodeById?.(id) ?? graph?._nodes_by_id?.[id];
}

function staticInteger(value) {
  return Number.isInteger(value)
    ? { kind: "value", value }
    : { kind: "invalid" };
}

export function resolveStaticInt(node, name, graph) {
  const input = node?.inputs?.find((candidate) => candidate.name === name);
  if (!input || input.link == null) {
    const widget = node?.widgets?.find((candidate) => candidate.name === name);
    return widget ? staticInteger(widget.value) : { kind: "unresolved" };
  }

  let linkId = input.link;
  const visited = new Set();
  while (linkId != null) {
    const origin = nodeById(graph, originId(graphLink(graph, linkId)));
    if (!origin || visited.has(origin.id)) return { kind: "unresolved" };
    visited.add(origin.id);
    if (origin.type === "PrimitiveNode") {
      const widget = origin.widgets?.find(
        (candidate) => typeof candidate.value === "number",
      );
      return widget ? staticInteger(widget.value) : { kind: "unresolved" };
    }
    if (origin.type !== "Reroute") return { kind: "unresolved" };
    linkId = origin.inputs?.[0]?.link;
  }
  return { kind: "unresolved" };
}

const CROP_NODE_ID = "LFGG_LoadAndCropImage";
const CROP_PREVIEW_HEIGHT = 360;
const CROP_PREVIEW_INSET = 8;
const installedCropEditor = Symbol("lfggCropEditor");
const cropInputNames = new Set(["crop_x", "crop_y", "crop_width", "crop_height"]);

function composeCallback(widget, update) {
  const original = widget.callback;
  widget.callback = function (...args) {
    const result = original?.apply(this, args);
    update();
    return result;
  };
}

function resizeNode(node, allowShrink) {
  const [, minimumHeight] = node.computeSize();
  node.setSize([
    node.size[0],
    allowShrink ? minimumHeight : Math.max(node.size[1], minimumHeight),
  ]);
}

function cropBounds(width, y) {
  return {
    x: CROP_PREVIEW_INSET,
    y: y + CROP_PREVIEW_INSET,
    width: Math.max(1, width - CROP_PREVIEW_INSET * 2),
    height: CROP_PREVIEW_HEIGHT - CROP_PREVIEW_INSET * 2,
  };
}

function drawFrame(ctx, imageBounds, frame, sourceWidth, sourceHeight, lowQuality) {
  const scaleX = imageBounds.width / sourceWidth;
  const scaleY = imageBounds.height / sourceHeight;
  const rectangle = {
    x: imageBounds.x + frame.x * scaleX,
    y: imageBounds.y + frame.y * scaleY,
    width: frame.width * scaleX,
    height: frame.height * scaleY,
  };
  const theme = globalThis.LiteGraph ?? {};
  const border = theme.WIDGET_OUTLINE_COLOR ?? theme.NODE_BOX_OUTLINE_COLOR ?? "#a0a0a0";
  const dim = theme.WIDGET_BGCOLOR ?? "#202020";
  ctx.fillStyle = dim;
  ctx.globalAlpha = 0.62;
  ctx.fillRect(imageBounds.x, imageBounds.y, imageBounds.width, rectangle.y - imageBounds.y);
  ctx.fillRect(imageBounds.x, rectangle.y, rectangle.x - imageBounds.x, rectangle.height);
  ctx.fillRect(rectangle.x + rectangle.width, rectangle.y, imageBounds.x + imageBounds.width - rectangle.x - rectangle.width, rectangle.height);
  ctx.fillRect(imageBounds.x, rectangle.y + rectangle.height, imageBounds.width, imageBounds.y + imageBounds.height - rectangle.y - rectangle.height);
  ctx.globalAlpha = 1;
  ctx.strokeStyle = border;
  ctx.lineWidth = 2;
  ctx.strokeRect(rectangle.x, rectangle.y, rectangle.width, rectangle.height);
  if (lowQuality) return rectangle;

  const handleSize = Math.min(12, rectangle.width / 2, rectangle.height / 2);
  ctx.fillStyle = border;
  for (const [x, y] of [
    [rectangle.x, rectangle.y],
    [rectangle.x + rectangle.width, rectangle.y],
    [rectangle.x, rectangle.y + rectangle.height],
    [rectangle.x + rectangle.width, rectangle.y + rectangle.height],
  ]) {
    ctx.beginPath();
    ctx.rect?.(x - handleSize / 2, y - handleSize / 2, handleSize, handleSize);
    ctx.fill();
  }
  ctx.fillStyle = theme.WIDGET_TEXT_COLOR ?? "#eeeeee";
  ctx.font = "12px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(`${frame.width} × ${frame.height}`, rectangle.x + rectangle.width / 2, rectangle.y + rectangle.height / 2);
  return rectangle;
}

function pointInRectangle(point, rectangle) {
  return point.x >= rectangle.x && point.x <= rectangle.x + rectangle.width &&
    point.y >= rectangle.y && point.y <= rectangle.y + rectangle.height;
}

export function installCropEditor(
  node,
  {
    createImage = () => new Image(),
    buildViewUrl = (value) => value,
    getGraph = () => undefined,
    isConfiguring = () => false,
  } = {},
) {
  if (node?.comfyClass !== CROP_NODE_ID) return undefined;
  if (node[installedCropEditor]) {
    node[installedCropEditor].isConfiguring = isConfiguring;
    node[installedCropEditor].update(false);
    return node[installedCropEditor].widget;
  }
  const byName = (name) => node.widgets?.find((widget) => widget.name === name);
  const image = byName("image");
  const ratioWidth = byName("ratio_width");
  const ratioHeight = byName("ratio_height");
  const cropX = byName("crop_x");
  const cropY = byName("crop_y");
  const cropWidth = byName("crop_width");
  const cropHeight = byName("crop_height");
  if (![image, ratioWidth, ratioHeight, cropX, cropY, cropWidth, cropHeight].every(Boolean)) {
    return undefined;
  }
  cropHeight.disabled = true;
  cropHeight.readonly = true;

  const controller = { source: undefined, frame: undefined, image: undefined, isConfiguring };
  const currentRatio = () => {
    const width = resolveStaticInt(node, "ratio_width", getGraph());
    const height = resolveStaticInt(node, "ratio_height", getGraph());
    if (width.kind === "unresolved" || height.kind === "unresolved") return { kind: "dynamic" };
    if (width.kind !== "value" || height.kind !== "value" || width.value < 1 || height.value < 1) return invalid;
    return { kind: "value", width: width.value, height: height.value };
  };
  const setEditing = (enabled) => {
    for (const widget of [cropX, cropY, cropWidth]) widget.disabled = !enabled;
    cropHeight.disabled = true;
  };
  const sync = (frame) => {
    controller.frame = frame;
    cropX.value = frame.x;
    cropY.value = frame.y;
    cropWidth.value = frame.width;
    cropHeight.value = frame.height;
    node.setDirtyCanvas?.(true, true);
  };
  const reset = () => {
    const resolved = currentRatio();
    setEditing(resolved.kind === "value");
    if (!controller.source || resolved.kind !== "value") {
      controller.frame = undefined;
      node.setDirtyCanvas?.(true, true);
      return;
    }
    const frame = initializeFrame(controller.source.width, controller.source.height, resolved.width, resolved.height);
    if (frame.kind) {
      controller.frame = undefined;
      return;
    }
    sync(frame);
  };
  const normalize = () => {
    const resolved = currentRatio();
    if (!controller.source || resolved.kind !== "value") return reset();
    const frame = normalizeTypedFrame(
      controller.frame,
      Number(cropWidth.value),
      Number(cropX.value),
      Number(cropY.value),
      controller.source.width,
      controller.source.height,
      resolved.width,
      resolved.height,
    );
    if (!frame.kind) sync(frame);
  };
  const preview = {
    type: "lfgg_crop_editor",
    name: "lfgg_crop_editor",
    serialize: false,
    options: { serialize: false },
    computeSize: () => [0, CROP_PREVIEW_HEIGHT],
    getState: () => {
      const resolved = currentRatio();
      if (resolved.kind === "dynamic") return { kind: "dynamic", label: "Run to resolve connected ratio" };
      return resolved.kind === "value" ? { kind: "ready" } : invalid;
    },
    draw(ctx, _node, width, y, _height, lowQuality) {
      if (!controller.image || !controller.source || !controller.frame) return;
      controller.drawY = y;
      controller.drawWidth = width;
      const contained = fitPreviewImage(controller.source.width, controller.source.height, cropBounds(width, y));
      if (contained.kind) return;
      ctx.drawImage(controller.image, contained.x, contained.y, contained.width, contained.height);
      ctx.save?.();
      ctx.beginPath?.();
      ctx.rect?.(contained.x, contained.y, contained.width, contained.height);
      ctx.strokeStyle = (globalThis.LiteGraph ?? {}).WIDGET_OUTLINE_COLOR ?? "#808080";
      ctx.globalAlpha = 0.45;
      ctx.stroke?.();
      ctx.globalAlpha = 1;
      drawFrame(ctx, contained, controller.frame, controller.source.width, controller.source.height, lowQuality);
      ctx.restore?.();
    },
    onPointerDown(event, position) {
      if (!controller.source || !controller.frame || currentRatio().kind !== "value") return false;
      const contained = fitPreviewImage(
        controller.source.width,
        controller.source.height,
        cropBounds(controller.drawWidth ?? node.size[0], controller.drawY ?? 0),
      );
      if (contained.kind) return false;
      const display = {
        x: contained.x + controller.frame.x * contained.width / controller.source.width,
        y: contained.y + controller.frame.y * contained.height / controller.source.height,
        width: controller.frame.width * contained.width / controller.source.width,
        height: controller.frame.height * contained.height / controller.source.height,
      };
      const target = Math.min(40, display.width / 2, display.height / 2);
      const corners = {
        "top-left": { x: display.x - target / 2, y: display.y - target / 2, width: target, height: target },
        "top-right": { x: display.x + display.width - target / 2, y: display.y - target / 2, width: target, height: target },
        "bottom-left": { x: display.x - target / 2, y: display.y + display.height - target / 2, width: target, height: target },
        "bottom-right": { x: display.x + display.width - target / 2, y: display.y + display.height - target / 2, width: target, height: target },
      };
      const corner = Object.entries(corners).find(([, targetBounds]) => pointInRectangle(position, targetBounds))?.[0];
      if (!corner && !pointInRectangle(position, display)) return false;
      const start = { ...controller.frame };
      const sourcePoint = (point) => ({
        x: (point.x - contained.x) * controller.source.width / contained.width,
        y: (point.y - contained.y) * controller.source.height / contained.height,
      });
      const startPoint = sourcePoint(position);
      event.onDragStart?.(() => {});
      event.onDrag?.((point) => {
        const pointer = sourcePoint(point);
        const resolved = currentRatio();
        const next = corner
          ? resizeFrame(start, corner, pointer.x, pointer.y, controller.source.width, controller.source.height, resolved.width, resolved.height)
          : moveFrame(start, pointer.x - startPoint.x, pointer.y - startPoint.y, controller.source.width, controller.source.height);
        if (!next.kind) sync(next);
      });
      event.onDragEnd?.(() => {});
      event.finally?.(() => node.setDirtyCanvas?.(true, true));
      return true;
    },
  };
  controller.widget = preview;
  controller.update = (shrink) => resizeNode(node, shrink && !controller.isConfiguring());
  node.addCustomWidget(preview);
  node.widgets.splice(node.widgets.indexOf(preview), 1);
  node.widgets.splice(node.widgets.indexOf(image) + 1, 0, preview);
  node[installedCropEditor] = controller;

  composeCallback(image, () => {
    node.imgs = [];
    const loaded = createImage();
    controller.image = loaded;
    loaded.onload = () => {
      const width = loaded.naturalWidth ?? loaded.width;
      const height = loaded.naturalHeight ?? loaded.height;
      if (positiveInteger(width) && positiveInteger(height)) {
        controller.source = { width, height };
        reset();
      }
    };
    loaded.src = buildViewUrl(image.value);
  });
  for (const widget of [ratioWidth, ratioHeight]) composeCallback(widget, reset);
  for (const widget of [cropX, cropY, cropWidth]) composeCallback(widget, normalize);
  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function (...args) {
    const result = originalConnectionsChange?.apply(this, args);
    reset();
    return result;
  };
  const originalConnectInput = node.onConnectInput;
  node.onConnectInput = function (inputIndex, ...args) {
    const input = this.inputs?.[inputIndex];
    if (cropInputNames.has(input?.name)) return false;
    return originalConnectInput?.apply(this, [inputIndex, ...args]);
  };
  const originalExecuted = node.onExecuted;
  node.onExecuted = function (message) {
    const result = originalExecuted?.apply(this, arguments);
    const crop = message?.crop?.[0];
    if (!controller.source || !crop || ![crop.ratio_width, crop.ratio_height, crop.x, crop.y, crop.width, crop.height].every(Number.isInteger)) return result;
    if (crop.ratio_width < 1 || crop.ratio_height < 1 || crop.width < 1 || crop.height < 1 || crop.x < 0 || crop.y < 0 || crop.width > controller.source.width || crop.height > controller.source.height) return result;
    ratioWidth.value = crop.ratio_width;
    ratioHeight.value = crop.ratio_height;
    const frame = normalizeTypedFrame(controller.frame, crop.width, crop.x, crop.y, controller.source.width, controller.source.height, crop.ratio_width, crop.ratio_height);
    if (!frame.kind) sync(frame);
    return result;
  };
  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    if (Array.isArray(serialized.widgets_values) && serialized.widgets_values.length === node.widgets.length) {
      serialized.widgets_values.splice(node.widgets.indexOf(preview), 1);
    }
    return result;
  };
  controller.update(false);
  return preview;
}
