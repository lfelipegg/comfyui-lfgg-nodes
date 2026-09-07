import { buildInputViewUrl } from "./crop_editor.mjs";
import { UI, initializeRoot, setWidgetHidden } from "./node_ui.mjs";
import { createEditorView, omitPresentationValues } from "./editor_view.mjs";

const VIDEO_CUTTER_ID = "LFGG_VideoCutter";
const THUMBNAIL_COUNT = 10;
const installed = Symbol("lfggVideoCutter");

function graphLink(graph, linkId) {
  return graph?.links?.[linkId] ?? graph?.links?.get?.(linkId);
}

function originId(link) {
  return Array.isArray(link) ? link[0] : link?.origin_id;
}

function nodeById(graph, id) {
  return graph?.getNodeById?.(id) ?? graph?._nodes_by_id?.[id];
}

function nodeType(node) {
  return node?.comfyClass ?? node?.type;
}

function linked(node, name) {
  return node?.inputs?.find((input) => input.name === name)?.link != null;
}

function validMetadata(value) {
  return value &&
    Number.isFinite(value.duration) && value.duration > 0 &&
    Number.isFinite(value.reported_fps) && value.reported_fps > 0 &&
    Number.isInteger(value.nominal_frame_count) && value.nominal_frame_count > 0;
}

function element(document, tag, properties = {}, ...children) {
  const result = document.createElement(tag);
  Object.assign(result, properties);
  result.append?.(...children);
  return result;
}

function composeCallback(widget, update) {
  const original = widget.callback;
  widget.callback = function (...args) {
    const result = original?.apply(this, args);
    update(...args);
    return result;
  };
}

export function formatTimecode(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "00:00:00.000";
  const milliseconds = Math.round(seconds * 1000);
  const hours = Math.floor(milliseconds / 3_600_000);
  const minutes = Math.floor(milliseconds / 60_000) % 60;
  const wholeSeconds = Math.floor(milliseconds / 1000) % 60;
  const remainder = milliseconds % 1000;
  return [hours, minutes, wholeSeconds]
    .map((part) => String(part).padStart(2, "0"))
    .join(":") + `.${String(remainder).padStart(3, "0")}`;
}

export function parseTimecode(value) {
  const match = /^(\d+):([0-5]\d):([0-5]\d)(?:\.(\d{1,3}))?$/.exec(String(value).trim());
  if (!match) return undefined;
  const milliseconds = Number((match[4] ?? "0").padEnd(3, "0"));
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + milliseconds / 1000;
}

export function resolveLoadVideoInput(node, graph) {
  let linkId = node?.inputs?.find((input) => input.name === "video")?.link;
  const visited = new Set();
  while (linkId != null) {
    const origin = nodeById(graph, originId(graphLink(graph, linkId)));
    if (!origin || visited.has(origin.id)) return undefined;
    visited.add(origin.id);
    if (nodeType(origin) === "LoadVideo") {
      const file = origin.widgets?.find((candidate) => candidate.name === "file")?.value;
      return typeof file === "string" && file ? file : undefined;
    }
    if (nodeType(origin) !== "Reroute") return undefined;
    linkId = origin.inputs?.[0]?.link;
  }
  return undefined;
}

export function buildVideoViewUrl(descriptor) {
  const query = new URLSearchParams({
    filename: descriptor?.filename ?? "",
    subfolder: descriptor?.subfolder ?? "",
    type: descriptor?.type ?? "temp",
  });
  return `/view?${query}`;
}

export function installVideoCutter(
  node,
  {
    document = globalThis.document,
    getGraph = () => undefined,
    buildViewUrl = buildInputViewUrl,
    buildOutputViewUrl = buildVideoViewUrl,
    fetchMetadata = async () => undefined,
    isConfiguring = () => false,
    events,
  } = {},
) {
  if (node?.comfyClass !== VIDEO_CUTTER_ID || !document) return undefined;
  if (node[installed]) {
    node[installed].refresh();
    node[installed].view.restore();
    return node[installed].widget;
  }
  const byName = (name) => node.widgets?.find((candidate) => candidate.name === name);
  const mode = byName("selection_mode");
  const startTime = byName("start_time");
  const endTime = byName("end_time");
  const firstFrame = byName("first_frame");
  const lastFrame = byName("last_frame");
  if (![mode, startTime, endTime, firstFrame, lastFrame].every(Boolean)) return undefined;

  const root = element(document, "div", { tabIndex: 0 });
  root.setAttribute("role", "group");
  Object.assign(root.style, {
    display: "flex",
    flexDirection: "column",
    gap: `${UI.gap}px`,
    padding: `${UI.inset}px`,
    boxSizing: "border-box",
    width: "100%",
  });
  const player = element(document, "video", {
    controls: true,
    preload: "metadata",
    playsInline: true,
  });
  Object.assign(player.style, { display: "block", width: "100%", minHeight: "0", objectFit: "contain", background: "#111" });
  const thumbnailPlayer = element(document, "video", {
    muted: true,
    preload: "metadata",
    playsInline: true,
  });
  thumbnailPlayer.style.display = "none";
  const filmstrip = element(document, "div");
  Object.assign(filmstrip.style, { display: "grid", gridTemplateColumns: `repeat(${THUMBNAIL_COUNT}, minmax(0, 1fr))`, gap: "2px" });
  const thumbnails = Array.from({ length: THUMBNAIL_COUNT }, () => {
    const canvas = element(document, "canvas", { width: 120, height: 68 });
    canvas.style.width = "100%";
    canvas.style.minWidth = "0";
    canvas.style.height = "auto";
    filmstrip.appendChild(canvas);
    return canvas;
  });
  const playhead = element(document, "input", {
    type: "range",
    min: "0",
    max: "1",
    step: "1",
    value: "0",
  });
  playhead.dataset.role = "playhead";
  const startHandle = element(document, "input", { type: "range", min: "0", max: "1", step: "1", value: "0" });
  startHandle.dataset.role = "boundary";
  startHandle.dataset.boundary = "start";
  startHandle.className = "lfgg-video-cutter-boundary";
  const endHandle = element(document, "input", { type: "range", min: "1", max: "1", step: "1", value: "1" });
  endHandle.dataset.role = "boundary";
  endHandle.dataset.boundary = "end";
  endHandle.className = "lfgg-video-cutter-boundary";
  playhead.setAttribute("aria-label", "Video playhead");
  startHandle.setAttribute("aria-label", "Selection start");
  endHandle.setAttribute("aria-label", "Selection end (exclusive)");
  const handles = element(document, "div");
  handles.dataset.role = "boundary-track";
  handles.className = "lfgg-video-cutter-boundary-track";
  Object.assign(handles.style, { display: "grid", gap: "4px" });
  for (const [handle, label] of [[startHandle, "Start"], [endHandle, "End (exclusive)"]]) {
    Object.assign(handle.style, { margin: "0", width: "100%" });
    const caption = element(document, "span", { textContent: label });
    caption.style.fontSize = `${UI.secondarySize}px`;
    const row = element(document, "label", {}, caption, handle);
    Object.assign(row.style, { display: "flex", flexWrap: "wrap", columnGap: `${UI.gap}px`, alignItems: "center" });
    caption.style.flex = "0 0 100px";
    handle.style.flex = "1 1 140px";
    handle.style.minWidth = "0";
    handles.append(row);
  }

  const startTimeInput = element(document, "input", { type: "text" });
  startTimeInput.dataset.role = "start-timecode";
  const endTimeInput = element(document, "input", { type: "text" });
  endTimeInput.dataset.role = "end-timecode";
  const firstFrameInput = element(document, "input", { type: "number", min: "0", step: "1" });
  firstFrameInput.dataset.role = "first-frame";
  const lastFrameInput = element(document, "input", { type: "number", min: "0", step: "1" });
  lastFrameInput.dataset.role = "last-frame";
  const labeledField = (input, caption, help) => {
    input.title = help;
    Object.assign(input.style, {
      width: "100%", minWidth: "0", boxSizing: "border-box", minHeight: `${UI.controlHeight}px`,
    });
    const label = element(document, "label", {},
      element(document, "span", { textContent: caption }), input);
    Object.assign(label.style, { display: "grid", gap: "4px", minWidth: "0" });
    return label;
  };
  const fields = element(document, "div", {},
    labeledField(startTimeInput, "Start time", "Included start, in HH:MM:SS.mmm."),
    labeledField(endTimeInput, "End time (exclusive)", "First time outside the selection, in HH:MM:SS.mmm."),
    labeledField(firstFrameInput, "First frame", "Included first frame, counted from zero."),
    labeledField(lastFrameInput, "Last frame (inclusive)", "Included last frame, counted from zero."));
  Object.assign(fields.style, {
    display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 140px), 1fr))", gap: `${UI.gap}px`,
  });

  const setStart = element(document, "button", { type: "button", textContent: "Set Start" });
  const setEnd = element(document, "button", { type: "button", textContent: "Set End" });
  const previous = element(document, "button", { type: "button", textContent: "Previous frame" });
  const next = element(document, "button", { type: "button", textContent: "Next frame" });
  const loop = element(document, "input", { type: "checkbox", checked: true });
  const loopLabel = element(document, "label", { textContent: "Loop selection " }, loop);
  const stepping = element(document, "div", {}, previous, next);
  const marking = element(document, "div", {}, setStart, setEnd);
  for (const group of [stepping, marking]) {
    Object.assign(group.style, { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "4px" });
  }
  Object.assign(loopLabel.style, { display: "flex", alignItems: "center", gap: "4px" });
  const controls = element(document, "div", {}, stepping, marking, loopLabel);
  Object.assign(controls.style, { display: "grid", gap: `${UI.gap}px` });
  const status = element(document, "div", { textContent: "Connect a direct Load Video source or run the node." });
  status.dataset.role = "status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const heading = element(document, "div", { textContent: "Selection" });
  initializeRoot(node, root, document, heading);
  const disclosure = element(document, "button", { type: "button", textContent: "Edit selection" });
  disclosure.dataset.role = "editor-disclosure";
  disclosure.setAttribute("aria-expanded", "false");
  const summary = element(document, "div");
  summary.dataset.role = "selection-summary";
  const locks = element(document, "div");
  locks.dataset.role = "boundary-locks";
  locks.style.fontSize = `${UI.secondarySize}px`;
  const timeline = element(document, "div");
  timeline.dataset.role = "timeline";
  Object.assign(timeline.style, { display: "grid", gap: `${UI.gap}px` });
  const strip = element(document, "div", {}, filmstrip);
  Object.assign(strip.style, { position: "relative", minWidth: "0" });
  const interval = element(document, "div");
  interval.setAttribute("aria-hidden", "true");
  Object.assign(interval.style, { position: "absolute", top: "0", bottom: "0", pointerEvents: "none", background: "var(--lfgg-text)", opacity: "0.18" });
  strip.append(interval);
  const thumbnailStatus = element(document, "div", { textContent: "Thumbnails appear when a source is available." });
  thumbnailStatus.style.fontSize = `${UI.secondarySize}px`;
  timeline.append(strip, thumbnailStatus, playhead, handles, controls);
  root.append(heading, player, thumbnailPlayer, fields, locks, summary, disclosure, timeline, status);

  const controller = {
    metadata: undefined,
    startFrame: 0,
    endFrame: 1,
    previewOffset: 0,
    previewDuration: undefined,
    lastMode: mode.value,
    metadataRequest: 0,
    thumbnailRequest: 0,
    source: undefined,
    inputLink: undefined,
    pendingRefresh: undefined,
    thumbnailsPending: false,
  };
  let applyView;
  const view = createEditorView(node, { isConfiguring, changed: expanded => applyView(expanded) });
  controller.view = view;
  const frameTime = (frame) => frame / controller.metadata.reported_fps;
  const selectionEndTime = () => controller.endFrame === controller.metadata.nominal_frame_count
    ? controller.metadata.duration
    : frameTime(controller.endFrame);
  const currentFrame = () => Math.round(
    (Number(player.currentTime) + controller.previewOffset) * controller.metadata.reported_fps,
  );
  const boundaryLinks = () => controller.lastMode === "Frames"
    ? [linked(node, "first_frame"), linked(node, "last_frame")]
    : [linked(node, "start_time"), linked(node, "end_time")];
  const updateLocks = () => {
    const unavailable = !controller.metadata;
    const [startLocked, endLocked] = boundaryLinks();
    controller.boundaryLocks = [startLocked, endLocked];
    playhead.disabled = unavailable;
    startHandle.disabled = unavailable || startLocked;
    endHandle.disabled = unavailable || endLocked;
    startTimeInput.disabled = unavailable || (controller.lastMode === "Time" && startLocked);
    endTimeInput.disabled = unavailable || (controller.lastMode === "Time" && endLocked);
    firstFrameInput.disabled = unavailable || (controller.lastMode === "Frames" && startLocked);
    lastFrameInput.disabled = unavailable || (controller.lastMode === "Frames" && endLocked);
    previous.disabled = unavailable;
    next.disabled = unavailable;
    setStart.disabled = unavailable;
    setEnd.disabled = unavailable;
    loop.disabled = unavailable;
    const timeMode = controller.lastMode === "Time";
    fields.children[0].hidden = fields.children[1].hidden = !timeMode;
    fields.children[2].hidden = fields.children[3].hidden = timeMode;
    for (const widget of [startTime, endTime, firstFrame, lastFrame]) {
      setWidgetHidden(node, widget, !unavailable && controller.validSelection !== false && !linked(node, widget.name));
    }
    const connected = [startTime, endTime, firstFrame, lastFrame].filter(widget => linked(node, widget.name)).map(widget => widget.name);
    locks.textContent = connected.length ? `Controlled upstream: ${connected.join(", ")}. Disconnect to edit saved local values.` : "";
    const label = unavailable ? "Video selection unavailable"
      : controller.validSelection === false ? "Invalid video selection" : "Video selection";
    root.setAttribute("aria-label", label);
    if (controller.widget) controller.widget.label = label;
  };
  const clearPreviewState = () => {
    controller.metadata = undefined;
    summary.textContent = "";
    controller.validSelection = undefined;
    controller.startFrame = 0;
    controller.endFrame = 1;
    controller.previewOffset = 0;
    controller.previewDuration = undefined;
    controller.thumbnailRequest += 1;
    controller.thumbnailsPending = false;
    playhead.value = "0";
    playhead.max = "1";
    startHandle.value = "0";
    startHandle.max = "1";
    endHandle.value = "1";
    endHandle.max = "1";
    startTimeInput.value = "";
    endTimeInput.value = "";
    firstFrameInput.value = "";
    lastFrameInput.value = "";
    thumbnailPlayer.onseeked = null;
    thumbnailPlayer.onloadeddata = null;
    updateLocks();
  };
  const writeWidgets = () => {
    if (!controller.metadata) return;
    startTime.value = frameTime(controller.startFrame);
    endTime.value = controller.endFrame === controller.metadata.nominal_frame_count
      ? -1
      : frameTime(controller.endFrame);
    firstFrame.value = controller.startFrame;
    lastFrame.value = controller.endFrame === controller.metadata.nominal_frame_count
      ? -1
      : controller.endFrame - 1;
  };
  const updateDom = () => {
    if (!controller.metadata) return;
    const maximum = controller.metadata.nominal_frame_count;
    playhead.max = String(maximum - 1);
    startHandle.max = String(maximum - 1);
    endHandle.max = String(maximum);
    startHandle.value = String(controller.startFrame);
    endHandle.value = String(controller.endFrame);
    startTimeInput.value = formatTimecode(frameTime(controller.startFrame));
    endTimeInput.value = formatTimecode(selectionEndTime());
    firstFrameInput.value = String(controller.startFrame);
    lastFrameInput.value = String(controller.endFrame - 1);
    summary.textContent = `${formatTimecode(frameTime(controller.startFrame))} – ${formatTimecode(selectionEndTime())} (end exclusive) · ${formatTimecode(selectionEndTime() - frameTime(controller.startFrame))} duration · frames ${controller.startFrame}–${controller.endFrame - 1} inclusive`;
    interval.style.left = `${controller.startFrame / maximum * 100}%`;
    interval.style.width = `${(controller.endFrame - controller.startFrame) / maximum * 100}%`;
    updateLocks();
    node.setDirtyCanvas?.(true, true);
  };
  const setSelection = (start, end, persist = true) => {
    const maximum = controller.metadata?.nominal_frame_count;
    if (!Number.isInteger(start) || !Number.isInteger(end) || !maximum || start < 0 || end > maximum || end <= start) {
      controller.validSelection = false;
      status.textContent = "Selection must stay in bounds and contain at least one frame.";
      if (controller.metadata) updateDom();
      return false;
    }
    controller.startFrame = start;
    controller.validSelection = true;
    controller.endFrame = end;
    status.textContent = "";
    if (persist) writeWidgets();
    updateDom();
    return true;
  };
  const selectionFromWidgets = (selectionMode = mode.value) => {
    const maximum = controller.metadata.nominal_frame_count;
    if (selectionMode === "Frames") {
      const start = Number(firstFrame.value);
      const last = Number(lastFrame.value);
      return [start, last === -1 ? maximum : last + 1];
    }
    const fps = controller.metadata.reported_fps;
    const start = Math.round(Number(startTime.value) * fps);
    const end = Number(endTime.value) === -1 ? maximum : Math.round(Number(endTime.value) * fps);
    return [start, end];
  };
  const applyMetadata = (metadata) => {
    if (!validMetadata(metadata)) throw new Error("Invalid video metadata response");
    controller.metadata = metadata;
    const [start, end] = selectionFromWidgets(controller.lastMode);
    if (!setSelection(start, end, false)) {
      status.textContent = "Saved selection is outside the source bounds; update the backend widgets.";
      return false;
    }
    updateDom();
    return true;
  };
  const applyExecutionMetadata = (metadata) => {
    if (
      !validMetadata(metadata) ||
      !Number.isFinite(metadata.selection_start) ||
      !Number.isFinite(metadata.selection_end) ||
      metadata.selection_start < 0 ||
      metadata.selection_end > metadata.duration ||
      metadata.selection_end <= metadata.selection_start
    ) {
      status.textContent = "Execution returned invalid video selection metadata.";
      return false;
    }
    controller.metadata = metadata;
    const start = Math.round(metadata.selection_start * metadata.reported_fps);
    const end = metadata.selection_end === metadata.duration
      ? metadata.nominal_frame_count
      : Math.round(metadata.selection_end * metadata.reported_fps);
    if (!setSelection(start, end, false)) {
      status.textContent = "Execution returned video selection metadata outside the source bounds.";
      return false;
    }
    return true;
  };
  const captureThumbnails = () => {
    if (!controller.metadata || !controller.thumbnailSource || !controller.previewDuration) return;
    const request = ++controller.thumbnailRequest;
    controller.thumbnailsPending = Boolean(node.flags?.collapsed) || !view.expanded;
    if (controller.thumbnailsPending) return;
    if (thumbnailPlayer.getAttribute?.("src") !== controller.thumbnailSource) thumbnailPlayer.src = controller.thumbnailSource;
    let index = 0;
    const capture = () => {
      if (request !== controller.thumbnailRequest || index >= thumbnails.length) return;
      if (node.flags?.collapsed || !view.expanded) {
        controller.thumbnailsPending = true;
        thumbnailPlayer.onseeked = null;
        return;
      }
      const canvas = thumbnails[index];
      canvas.getContext?.("2d")?.drawImage?.(thumbnailPlayer, 0, 0, canvas.width, canvas.height);
      index += 1;
      thumbnailStatus.textContent = index === thumbnails.length ? "" : `Loading thumbnails ${index}/${thumbnails.length}`;
      if (index < thumbnails.length) {
        thumbnailPlayer.currentTime = controller.previewDuration * index / (thumbnails.length - 1);
      } else {
        thumbnailPlayer.onseeked = null;
      }
    };
    const begin = () => {
      if (request !== controller.thumbnailRequest) return;
      thumbnailPlayer.onloadeddata = null;
      thumbnailPlayer.onseeked = capture;
      if (thumbnailPlayer.currentTime === 0) capture();
      else thumbnailPlayer.currentTime = 0;
    };
    thumbnailPlayer.onseeked = null;
    if ((thumbnailPlayer.readyState ?? 2) >= 2) begin();
    else thumbnailPlayer.onloadeddata = begin;
  };
  applyView = (expanded) => {
    if (!expanded && timeline.contains?.(document.activeElement)) disclosure.focus();
    timeline.hidden = !expanded;
    timeline.style.display = expanded ? "grid" : "none";
    player.style.maxHeight = expanded ? "360px" : "180px";
    disclosure.textContent = expanded ? "Hide selection controls" : "Edit selection";
    disclosure.setAttribute("aria-expanded", String(expanded));
    if (!expanded) {
      if (thumbnailPlayer.onseeked || thumbnailPlayer.onloadeddata) controller.thumbnailsPending = true;
      controller.thumbnailRequest += 1;
      thumbnailPlayer.onseeked = null;
      thumbnailPlayer.onloadeddata = null;
    } else if (controller.thumbnailsPending && !node.flags?.collapsed) {
      captureThumbnails();
    }
  };
  disclosure.addEventListener("click", () => view.setExpanded(!view.expanded));
  controller.refresh = ({ force = true } = {}) => {
    const source = resolveLoadVideoInput(node, getGraph());
    const inputLink = node.inputs?.find(({ name }) => name === "video")?.link;
    if (!force && source === controller.source && inputLink === controller.inputLink) {
      return controller.pendingRefresh ?? Promise.resolve(Boolean(controller.metadata));
    }
    const request = ++controller.metadataRequest;
    const changedSource = source !== controller.source;
    controller.source = source;
    controller.inputLink = inputLink;
    controller.pendingRefresh = (async () => {
      if (!source) {
        clearPreviewState();
        player.pause?.();
        player.removeAttribute?.("src");
        thumbnailPlayer.removeAttribute?.("src");
        status.textContent = "Run the node to preview a computed video.";
        return false;
      }
      if (changedSource) clearPreviewState();
      const url = buildViewUrl(source);
      player.src = url;
      controller.thumbnailSource = url;
      status.textContent = "Loading video metadata…";
      controller.previewOffset = 0;
      try {
        const metadata = await fetchMetadata(source);
        if (request !== controller.metadataRequest || controller.source !== source) return false;
        controller.previewDuration = metadata.duration;
        if (!applyMetadata(metadata)) return false;
        captureThumbnails();
        return true;
      } catch (_error) {
        if (request !== controller.metadataRequest || controller.source !== source) return false;
        status.textContent = "Video metadata preview is unavailable; backend widgets still execute.";
        return false;
      }
    })().finally(() => {
      if (request === controller.metadataRequest) controller.pendingRefresh = undefined;
    });
    return controller.pendingRefresh;
  };
  const setBoundaryFromPlayer = (which) => {
    if (!controller.metadata) return;
    const frame = currentFrame();
    if (which === "start" && !boundaryLinks()[0]) setSelection(frame, controller.endFrame);
    if (which === "end" && !boundaryLinks()[1]) setSelection(controller.startFrame, frame + 1);
  };
  const step = (delta) => {
    if (!controller.metadata) return;
    const frame = Math.max(0, Math.min(controller.metadata.nominal_frame_count - 1, currentFrame() + delta));
    player.currentTime = Math.max(0, frameTime(frame) - controller.previewOffset);
    playhead.value = String(frame);
  };

  playhead.addEventListener("input", () => {
    if (!controller.metadata) return;
    player.currentTime = Math.max(0, frameTime(Number(playhead.value)) - controller.previewOffset);
  });
  startHandle.addEventListener("input", () => setSelection(Number(startHandle.value), controller.endFrame));
  endHandle.addEventListener("input", () => setSelection(controller.startFrame, Number(endHandle.value)));
  startTimeInput.addEventListener("change", () => {
    if (!controller.metadata) return;
    const seconds = parseTimecode(startTimeInput.value);
    if (seconds !== undefined) {
      mode.value = "Time";
      controller.lastMode = "Time";
      setSelection(Math.round(seconds * controller.metadata.reported_fps), controller.endFrame);
    }
  });
  endTimeInput.addEventListener("change", () => {
    if (!controller.metadata) return;
    const seconds = parseTimecode(endTimeInput.value);
    if (seconds !== undefined) {
      mode.value = "Time";
      controller.lastMode = "Time";
      setSelection(controller.startFrame, Math.round(seconds * controller.metadata.reported_fps));
    }
  });
  firstFrameInput.addEventListener("change", () => {
    if (!controller.metadata) return;
    mode.value = "Frames";
    controller.lastMode = "Frames";
    setSelection(Number(firstFrameInput.value), controller.endFrame);
  });
  lastFrameInput.addEventListener("change", () => {
    if (!controller.metadata) return;
    mode.value = "Frames";
    controller.lastMode = "Frames";
    setSelection(controller.startFrame, Number(lastFrameInput.value) + 1);
  });
  previous.addEventListener("click", () => step(-1));
  next.addEventListener("click", () => step(1));
  setStart.addEventListener("click", () => setBoundaryFromPlayer("start"));
  setEnd.addEventListener("click", () => setBoundaryFromPlayer("end"));
  player.addEventListener("play", () => {
    if (!controller.metadata) return;
    const frame = currentFrame();
    if (frame < controller.startFrame || frame >= controller.endFrame) {
      player.currentTime = Math.max(0, frameTime(controller.startFrame) - controller.previewOffset);
    }
  });
  player.addEventListener("timeupdate", () => {
    if (!controller.metadata || player.paused) return;
    const frame = currentFrame();
    playhead.value = String(Math.max(0, Math.min(controller.metadata.nominal_frame_count - 1, frame)));
    if (frame < controller.endFrame) return;
    if (loop.checked) {
      player.currentTime = Math.max(0, frameTime(controller.startFrame) - controller.previewOffset);
      player.play?.();
    } else {
      player.pause?.();
    }
  });
  root.addEventListener("keydown", (event) => {
    if (["INPUT", "TEXTAREA", "SELECT", "BUTTON", "SUMMARY", "VIDEO"].includes(event.target?.tagName) || event.target?.isContentEditable) return;
    if (event.key === " ") {
      event.preventDefault();
      if (player.paused) player.play?.(); else player.pause?.();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      step(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      step(1);
    } else if (event.key.toLowerCase() === "i") {
      event.preventDefault();
      setBoundaryFromPlayer("start");
    } else if (event.key.toLowerCase() === "o") {
      event.preventDefault();
      setBoundaryFromPlayer("end");
    }
  });

  composeCallback(mode, () => {
    if (!controller.metadata) {
      controller.lastMode = mode.value;
      updateLocks();
      return;
    }
    writeWidgets();
    controller.lastMode = mode.value;
    updateDom();
  });
  for (const [widget, selectionMode] of [
    [startTime, "Time"], [endTime, "Time"], [firstFrame, "Frames"], [lastFrame, "Frames"],
  ]) {
    composeCallback(widget, () => {
      if (!controller.metadata || mode.value !== selectionMode) return;
      const [start, end] = selectionFromWidgets(selectionMode);
      setSelection(start, end);
    });
  }
  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function (...args) {
    const result = originalConnectionsChange?.apply(this, args);
    const locks = boundaryLinks();
    const unlocked = locks.map((locked, index) => controller.boundaryLocks?.[index] && !locked);
    if (controller.metadata && unlocked.some(Boolean)) {
      const [start, end] = selectionFromWidgets(controller.lastMode);
      setSelection(
        unlocked[0] ? start : controller.startFrame,
        unlocked[1] ? end : controller.endFrame,
        false,
      );
    }
    updateLocks();
    controller.widget.lfggReady = controller.refresh({ force: false });
    return result;
  };
  const originalExecuted = node.onExecuted;
  node.onExecuted = function (message) {
    const result = originalExecuted?.apply(this, arguments);
    const descriptor = message?.images?.[0];
    const metadata = message?.video_cutter?.[0];
    const previewDuration = Number(metadata?.selection_end) - Number(metadata?.selection_start);
    controller.metadataRequest += 1;
    controller.pendingRefresh = undefined;
    if (
      validMetadata(metadata) &&
      Number.isFinite(previewDuration) &&
      previewDuration > 0 &&
      applyExecutionMetadata(metadata)
    ) {
      controller.inputLink = node.inputs?.find(({ name }) => name === "video")?.link;
      const source = resolveLoadVideoInput(node, getGraph());
      if (source) {
        controller.source = source;
        const url = buildViewUrl(source);
        player.src = url;
        controller.thumbnailSource = url;
        controller.previewOffset = 0;
        controller.previewDuration = metadata.duration;
      } else if (descriptor) {
        controller.source = undefined;
        player.src = buildOutputViewUrl(descriptor);
        controller.thumbnailSource = player.src;
        controller.previewOffset = metadata.selection_start;
        controller.previewDuration = previewDuration;
      } else {
        return result;
      }
      captureThumbnails();
    }
    return result;
  };

  const widget = node.addDOMWidget("lfgg_video_cutter", "lfgg_video_cutter", root, {
    serialize: false,
    getMinHeight: () => root.scrollHeight || 180,
    onDraw: () => {
      if (resolveLoadVideoInput(node, getGraph()) !== controller.source) {
        widget.lfggReady = controller.refresh();
      }
      if (controller.thumbnailsPending && view.expanded && !node.flags?.collapsed) captureThumbnails();
    },
  });
  widget.serialize = false;
  widget.options.serialize = false;
  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    omitPresentationValues(node, serialized, [widget]);
    return result;
  };
  controller.widget = widget;
  node[installed] = controller;
  const configured = node.onAfterGraphConfigured;
  node.onAfterGraphConfigured = function (...args) {
    const result = configured?.apply(this, args);
    widget.lfggReady = controller.refresh({ force: false });
    return result;
  };
  view.restore();
  const graphChanged = () => {
    if (node.graph === getGraph() && !isConfiguring()) widget.lfggReady = controller.refresh({ force: false });
  };
  events?.addEventListener("graphChanged", graphChanged);
  const observer = typeof ResizeObserver === "function" ? new ResizeObserver(() => {
    view.fit(true);
    if (controller.thumbnailsPending && view.expanded && !node.flags?.collapsed) captureThumbnails();
  }) : undefined;
  observer?.observe(root);
  const removed = node.onRemoved;
  node.onRemoved = function (...args) {
    events?.removeEventListener("graphChanged", graphChanged);
    observer?.disconnect();
    controller.metadataRequest += 1;
    controller.thumbnailRequest += 1;
    player.pause?.();
    thumbnailPlayer.pause?.();
    thumbnailPlayer.onseeked = null;
    thumbnailPlayer.onloadeddata = null;
    return removed?.apply(this, args);
  };
  widget.lfggReady = controller.refresh();
  return widget;
}
