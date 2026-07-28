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
