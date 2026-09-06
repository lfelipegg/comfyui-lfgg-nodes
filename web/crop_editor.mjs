import { fitRatio, greatestCommonDivisor } from "./ratio_preview.mjs";
import { UI, canvasTheme, drawIdentity, fitText, resolvedWidth, setWidgetHidden } from "./node_ui.mjs";
import { createEditorView, omitPresentationValues } from "./editor_view.mjs";

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
const CROP_PREVIEW_INSET = UI.inset;
const installedCropEditor = Symbol("lfggCropEditor");
const cropInputNames = new Set(["crop_x", "crop_y", "crop_width", "crop_height"]);

export function buildInputViewUrl(value) {
  const normalized = String(value).replace(/\s+\[input\]$/, "").replaceAll("\\", "/");
  const slash = normalized.lastIndexOf("/");
  const query = new URLSearchParams({
    filename: normalized.slice(slash + 1),
    subfolder: slash < 0 ? "" : normalized.slice(0, slash),
    type: "input",
  });
  return `/view?${query}`;
}

function composeCallback(widget, update) {
  const original = widget.callback;
  widget.callback = function (...args) {
    const result = original?.apply(this, args);
    update();
    return result;
  };
}

function previewHeight(width, source, expanded) {
  const available = Math.max(1, width - CROP_PREVIEW_INSET * 2);
  const proportional = source ? available * source.height / source.width : 120;
  return Math.max(96, Math.min(expanded ? 360 : 200, proportional)) + 52;
}

function cropBounds(width, y, height) {
  return {
    x: CROP_PREVIEW_INSET,
    y: y + CROP_PREVIEW_INSET,
    width: Math.max(1, width - CROP_PREVIEW_INSET * 2),
    height: height - 52,
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
  ctx.strokeStyle = "#111111";
  ctx.lineWidth = 4;
  ctx.strokeRect(rectangle.x, rectangle.y, rectangle.width, rectangle.height);
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.strokeRect(rectangle.x, rectangle.y, rectangle.width, rectangle.height);
  if (lowQuality) return rectangle;

  const handleSize = 12;
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
  return rectangle;
}

function pointInRectangle(point, rectangle) {
  return point.x >= rectangle.x && point.x <= rectangle.x + rectangle.width &&
    point.y >= rectangle.y && point.y <= rectangle.y + rectangle.height;
}

function cornerAtPoint(point, rectangle) {
  const halfTarget = 20;
  const midpointX = rectangle.x + rectangle.width / 2;
  const midpointY = rectangle.y + rectangle.height / 2;
  const moveHalfWidth = 8;
  const moveHalfHeight = 8;
  if (pointInRectangle(point, {
    x: midpointX - moveHalfWidth,
    y: midpointY - moveHalfHeight,
    width: moveHalfWidth * 2,
    height: moveHalfHeight * 2,
  })) {
    return "move";
  }
  const horizontal = point.x < midpointX ? "left" : "right";
  const vertical = point.y < midpointY ? "top" : "bottom";
  const cornerX = horizontal === "left"
    ? rectangle.x
    : rectangle.x + rectangle.width;
  const cornerY = vertical === "top"
    ? rectangle.y
    : rectangle.y + rectangle.height;
  const target = {
    x: horizontal === "left"
      ? cornerX - halfTarget
      : Math.max(midpointX, cornerX - halfTarget),
    y: vertical === "top"
      ? cornerY - halfTarget
      : Math.max(midpointY, cornerY - halfTarget),
    width: horizontal === "left"
      ? Math.min(midpointX, cornerX + halfTarget) - (cornerX - halfTarget)
      : cornerX + halfTarget - Math.max(midpointX, cornerX - halfTarget),
    height: vertical === "top"
      ? Math.min(midpointY, cornerY + halfTarget) - (cornerY - halfTarget)
      : cornerY + halfTarget - Math.max(midpointY, cornerY - halfTarget),
  };
  return pointInRectangle(point, target)
    ? `${vertical}-${horizontal}`
    : undefined;
}

export function installCropEditor(
  node,
  {
    createImage = () => new Image(),
    buildViewUrl = (value) => value,
    getGraph = () => undefined,
    isConfiguring = () => false,
    events,
  } = {},
) {
  if (node?.comfyClass !== CROP_NODE_ID) return undefined;
  if (node[installedCropEditor]) {
    node[installedCropEditor].isConfiguring = isConfiguring;
    node[installedCropEditor].refresh();
    node[installedCropEditor].update(false);
    node[installedCropEditor].view.restore();
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
  if (typeof node.addWidget !== "function" || typeof node.addCustomWidget !== "function") return undefined;
  node.hideOutputImages = true;
  const background = node.onDrawBackground;
  node.onDrawBackground = function (...args) {
    // Legacy preview creation does not honor hideOutputImages.
    if (this.imgs?.length) this.imgs = undefined;
    return background?.apply(this, args);
  };
  cropHeight.disabled = true;
  cropHeight.readonly = true;
  cropHeight.options ??= {};
  cropHeight.options.read_only = true;

  const controller = {
    source: undefined,
    frame: undefined,
    image: undefined,
    imageState: { kind: "loading", label: "Loading selected image…" },
    executionRatio: undefined,
    loadRequest: 0,
    observedStaticRatio: undefined,
    isConfiguring,
  };
  let disclosure;
  let redrawPending = false;
  const redraw = () => {
    node.setDirtyCanvas?.(true, true);
    if (redrawPending) return;
    redrawPending = true;
    queueMicrotask(() => {
      redrawPending = false;
      controller.widget?.triggerDraw?.();
    });
  };
  const showView = (expanded) => {
    for (const widget of [cropX, cropY, cropWidth, cropHeight]) {
      setWidgetHidden(node, widget, !expanded && controller.imageState.kind !== "error");
    }
    disclosure.label = expanded ? "Hide crop controls" : "Edit crop";
    if (controller.widget) {
      controller.widget.computedHeight = height();
      controller.widget.label = controller.imageState.label || "Crop preview";
    }
    redraw();
  };
  const view = createEditorView(node, { isConfiguring: () => controller.isConfiguring(), changed: showView });
  controller.view = view;
  const height = (width = node.size[0]) => previewHeight(width, controller.source, view.expanded);
  const staticRatioKey = () => {
    const width = resolveStaticInt(node, "ratio_width", getGraph());
    const height = resolveStaticInt(node, "ratio_height", getGraph());
    const part = (resolved) => resolved.kind === "value"
      ? `value:${resolved.value}`
      : resolved.kind;
    return `${part(width)}|${part(height)}`;
  };
  const rememberStaticRatio = () => {
    controller.observedStaticRatio = staticRatioKey();
  };
  const currentRatio = () => {
    const width = resolveStaticInt(node, "ratio_width", getGraph());
    const height = resolveStaticInt(node, "ratio_height", getGraph());
    if (width.kind === "unresolved" || height.kind === "unresolved") {
      return controller.executionRatio
        ? { kind: "value", ...controller.executionRatio }
        : { kind: "dynamic" };
    }
    if (width.kind !== "value" || height.kind !== "value" || width.value < 1 || height.value < 1) return invalid;
    return { kind: "value", width: width.value, height: height.value };
  };
  const setEditing = (enabled) => {
    for (const widget of [cropX, cropY, cropWidth]) {
      widget.disabled = !enabled || controller.imageState.kind !== "ready";
      widget.options ??= {};
      widget.options.read_only = widget.disabled;
    }
    cropHeight.disabled = true;
  };
  const sync = (frame) => {
    controller.frame = frame;
    cropX.value = frame.x;
    cropY.value = frame.y;
    cropWidth.value = frame.width;
    cropHeight.value = frame.height;
    redraw();
  };
  const reset = () => {
    controller.pendingCrop = undefined;
    const resolved = currentRatio();
    setEditing(resolved.kind === "value");
    if (!controller.source || resolved.kind !== "value") {
      controller.frame = undefined;
      redraw();
      return;
    }
    const frame = initializeFrame(controller.source.width, controller.source.height, resolved.width, resolved.height);
    if (frame.kind) {
      controller.frame = undefined;
      return;
    }
    sync(frame);
  };
  const observeStaticRatio = () => {
    const observed = staticRatioKey();
    if (controller.observedStaticRatio === undefined) {
      controller.observedStaticRatio = observed;
      return;
    }
    if (observed === controller.observedStaticRatio) return;
    controller.observedStaticRatio = observed;
    controller.executionRatio = undefined;
    reset();
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
  const loadSelectedImage = (restorePersisted) => {
    const request = ++controller.loadRequest;
    controller.executionRatio = undefined;
    controller.pendingCrop = undefined;
    controller.source = undefined;
    controller.frame = undefined;
    controller.image = undefined;
    controller.imageState = { kind: "loading", label: "Loading selected image…" };
    setEditing(false);
    showView(view.expanded);
    node.imgs = [];
    const loaded = createImage();
    loaded.onerror = () => {
      if (request !== controller.loadRequest || controller.imageState.kind !== "loading") return;
      controller.imageState = {
        kind: "error",
        label: "Image unavailable\nReselect or upload the image.",
      };
      showView(view.expanded);
      view.fit();
      redraw();
    };
    loaded.onload = () => {
      if (request !== controller.loadRequest || controller.imageState.kind !== "loading") return;
      const width = loaded.naturalWidth ?? loaded.width;
      const height = loaded.naturalHeight ?? loaded.height;
      if (!positiveInteger(width) || !positiveInteger(height)) {
        loaded.onerror();
        return;
      }
      controller.image = loaded;
      controller.imageState = { kind: "ready" };
      controller.source = { width, height };
      showView(view.expanded);
      view.fit(true);
      const pendingCrop = controller.pendingCrop;
      controller.pendingCrop = undefined;
      if (applyExecutionCrop(pendingCrop)) return;
      const resolved = currentRatio();
      const frame = {
        x: Number(cropX.value),
        y: Number(cropY.value),
        width: Number(cropWidth.value),
        height: Number(cropHeight.value),
      };
      if (
        restorePersisted &&
        resolved.kind === "value" &&
        validFrame(frame) &&
        frame.x + frame.width <= width &&
        frame.y + frame.height <= height &&
        frame.width * resolved.height === frame.height * resolved.width
      ) {
        setEditing(true);
        sync(frame);
      } else {
        reset();
      }
    };
    try {
      loaded.src = buildViewUrl(image.value);
    } catch {
      loaded.onerror();
    }
  };
  let preview = {
    type: "lfgg_crop_editor",
    name: "lfgg_crop_editor",
    serialize: false,
    options: { serialize: false },
    computeSize: (width) => [0, height(Math.max(width || 0, node.size[0]))],
    getState: () => {
      if (controller.imageState.kind !== "ready") return controller.imageState;
      const resolved = currentRatio();
      if (resolved.kind === "dynamic") return { kind: "dynamic", label: "Run to resolve connected ratio" };
      if (resolved.kind !== "value") return { ...invalid, label: "Enter a positive integer ratio" };
      return controller.frame ? { kind: "ready" } : { ...doesNotFit, label: "Ratio does not fit source image" };
    },
    draw(ctx, _node, _width, y, _height, lowQuality) {
      observeStaticRatio();
      const width = resolvedWidth(node, _width, controller.widget.y === 0 && y === 1);
      controller.widget.width = width;
      const totalHeight = height(width);
      const bounds = cropBounds(width, y, totalHeight);
      const theme = canvasTheme();
      const captionY = bounds.y + bounds.height + 20;
      drawIdentity(ctx, UI.inset, captionY - 6, theme.background);
      ctx.font = `${UI.fontSize}px sans-serif`;
      ctx.fillStyle = theme.text;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      const caption = controller.frame
        ? `${controller.frame.width} × ${controller.frame.height} source pixels`
        : controller.source ? preview.getState().label : "Crop preview";
      ctx.fillText(fitText(ctx, caption, bounds.width - 16), UI.inset + 11, captionY);
      if (controller.imageState.kind !== "ready") {
        const bounds = cropBounds(width, y, totalHeight);
        ctx.fillStyle = (globalThis.LiteGraph ?? {}).WIDGET_TEXT_COLOR ?? "#eeeeee";
        ctx.font = "12px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        controller.imageState.label.split("\n").forEach((line, index) => {
          ctx.fillText(line, bounds.x + bounds.width / 2, bounds.y + bounds.height / 2 + index * 18);
        });
        return;
      }
      if (!controller.image || !controller.source) return;
      controller.drawY = y;
      controller.drawWidth = width;
      const contained = fitPreviewImage(controller.source.width, controller.source.height, bounds);
      if (contained.kind) return;
      ctx.drawImage(controller.image, contained.x, contained.y, contained.width, contained.height);
      if (!controller.frame) return;
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
    onPointerDown(event, pointerNode, canvas) {
      if (event.eDown?.button != null && event.eDown.button !== 0) return false;
      const localPoint = (pointerEvent) => event.element && event.element !== canvas?.canvas
        ? { x: pointerEvent.offsetX, y: pointerEvent.offsetY }
        : { x: pointerEvent.canvasX - pointerNode.pos[0], y: pointerEvent.canvasY - pointerNode.pos[1] };
      if (!event.eDown) return false;
      const position = localPoint(event.eDown);
      if (!Number.isFinite(position.x) || !Number.isFinite(position.y)) return false;
      if (!controller.source || !controller.frame || currentRatio().kind !== "value") return false;
      const contained = fitPreviewImage(
        controller.source.width,
        controller.source.height,
        cropBounds(controller.drawWidth ?? node.size[0], controller.drawY ?? 0, height(controller.drawWidth)),
      );
      if (contained.kind) return false;
      const display = {
        x: contained.x + controller.frame.x * contained.width / controller.source.width,
        y: contained.y + controller.frame.y * contained.height / controller.source.height,
        width: controller.frame.width * contained.width / controller.source.width,
        height: controller.frame.height * contained.height / controller.source.height,
      };
      const target = cornerAtPoint(position, display);
      if (!target && !pointInRectangle(position, display)) return false;
      const corner = target === "move" ? undefined : target;
      const start = { ...controller.frame };
      const sourcePoint = (point) => ({
        x: (point.x - contained.x) * controller.source.width / contained.width,
        y: (point.y - contained.y) * controller.source.height / contained.height,
      });
      const startPoint = sourcePoint(position);
      event.onDragStart = () => {};
      event.onDrag = (pointerEvent) => {
        const pointer = sourcePoint(localPoint(pointerEvent));
        const resolved = currentRatio();
        const next = corner
          ? resizeFrame(start, corner, pointer.x, pointer.y, controller.source.width, controller.source.height, resolved.width, resolved.height)
          : moveFrame(start, pointer.x - startPoint.x, pointer.y - startPoint.y, controller.source.width, controller.source.height);
        if (!next.kind) sync(next);
      };
      event.onDragEnd = event.onDrag;
      return true;
    },
  };
  controller.update = (shrink) => {
    observeStaticRatio();
    view.fit(shrink);
  };
  preview = node.addCustomWidget(preview);
  controller.widget = preview;
  node.widgets.splice(node.widgets.indexOf(preview), 1);
  node.widgets.splice(node.widgets.indexOf(image) + 1, 0, preview);
  disclosure = node.addWidget("button", "Edit crop", null, () => view.setExpanded(!view.expanded), { serialize: false });
  disclosure.serialize = false;
  disclosure.options ??= {};
  disclosure.options.serialize = false;
  view.restore();
  node[installedCropEditor] = controller;

  composeCallback(image, () => loadSelectedImage(false));
  for (const widget of [ratioWidth, ratioHeight]) {
    composeCallback(widget, () => {
      controller.executionRatio = undefined;
      rememberStaticRatio();
      reset();
    });
  }
  for (const widget of [cropX, cropY, cropWidth]) composeCallback(widget, normalize);
  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function (...args) {
    const result = originalConnectionsChange?.apply(this, args);
    controller.executionRatio = undefined;
    rememberStaticRatio();
    reset();
    return result;
  };
  const originalConnectInput = node.onConnectInput;
  node.onConnectInput = function (inputIndex, ...args) {
    const input = this.inputs?.[inputIndex];
    const result = originalConnectInput?.apply(this, [inputIndex, ...args]);
    if (cropInputNames.has(input?.name)) return false;
    return result;
  };
  const applyExecutionCrop = (crop) => {
    if (!controller.source || !crop || ![crop.ratio_width, crop.ratio_height, crop.x, crop.y, crop.width, crop.height].every(Number.isInteger)) return false;
    if (crop.ratio_width < 1 || crop.ratio_height < 1 || crop.width < 1 || crop.height < 1 || crop.x < 0 || crop.y < 0 || crop.width > controller.source.width || crop.height > controller.source.height || crop.x + crop.width > controller.source.width || crop.y + crop.height > controller.source.height) return false;
    ratioWidth.value = crop.ratio_width;
    ratioHeight.value = crop.ratio_height;
    controller.executionRatio = { width: crop.ratio_width, height: crop.ratio_height };
    rememberStaticRatio();
    setEditing(true);
    const frame = normalizeTypedFrame(controller.frame, crop.width, crop.x, crop.y, controller.source.width, controller.source.height, crop.ratio_width, crop.ratio_height);
    if (!frame.kind) sync(frame);
    return !frame.kind;
  };
  const originalExecuted = node.onExecuted;
  node.onExecuted = function (message) {
    const result = originalExecuted?.apply(this, arguments);
    const crop = message?.crop?.[0];
    if (controller.imageState.kind === "loading") controller.pendingCrop = crop;
    else applyExecutionCrop(crop);
    return result;
  };
  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    omitPresentationValues(node, serialized, [preview, disclosure]);
    return result;
  };
  controller.refresh = () => {
    rememberStaticRatio();
    loadSelectedImage(true);
  };
  const graphChanged = () => {
    if (node.graph === getGraph() && !controller.isConfiguring()) controller.update(false);
  };
  events?.addEventListener("graphChanged", graphChanged);
  const removed = node.onRemoved;
  node.onRemoved = function (...args) {
    events?.removeEventListener("graphChanged", graphChanged);
    controller.loadRequest += 1;
    return removed?.apply(this, args);
  };
  controller.update(false);
  controller.refresh();
  return preview;
}
