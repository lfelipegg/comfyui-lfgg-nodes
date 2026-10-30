import { UI, initializeRoot } from "./node_ui.mjs";
import { createEditorView, omitPresentationValues } from "./editor_view.mjs";

export const OUTPUT_GALLERY_ID = "LFGG_OutputGallery";
export const REFRESH_DEBOUNCE_MS = 500;
export const TILE_PREVIEW = "webp;60";
const WIDGET_NAMES = ["path", "include_subfolders", "media_filter", "name_filter", "sort", "limit"];
const KIND_EXTENSIONS = {
  image: ["png", "jpg", "jpeg", "webp", "gif"],
  video: ["mp4", "webm", "mov"],
  audio: ["mp3", "wav", "flac", "ogg"],
};
const COMPACT_PREVIEW_HEIGHT = 180;
const EXPANDED_PREVIEW_HEIGHT = 360;
const installed = Symbol("lfggOutputGallery");

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

export function kindOf(extension) {
  const lower = String(extension ?? "").toLowerCase();
  return Object.keys(KIND_EXTENSIONS).find((kind) => KIND_EXTENSIONS[kind].includes(lower));
}

export function itemKey(item) {
  return item?.subfolder ? `${item.subfolder}/${item.filename}` : String(item?.filename ?? "");
}

export function buildOutputViewUrl(item, { preview } = {}) {
  const query = new URLSearchParams({
    filename: item?.filename ?? "",
    subfolder: item?.subfolder ?? "",
    type: "output",
  });
  if (preview) query.set("preview", preview);
  return `/view?${query}`;
}

export function buildListQuery(values) {
  return new URLSearchParams({
    path: String(values?.path ?? ""),
    include_subfolders: values?.include_subfolders === false ? "false" : "true",
    media_filter: String(values?.media_filter ?? "all"),
    name_filter: String(values?.name_filter ?? ""),
    sort: String(values?.sort ?? "newest first"),
    limit: String(values?.limit ?? 24),
  }).toString();
}

export function selectAfterRefresh({ previousKeys, items, sort, selectedKey, playing }) {
  const keys = items.map(itemKey);
  const kept = selectedKey != null && keys.includes(selectedKey) ? selectedKey : undefined;
  const fresh = keys.some((key) => !previousKeys.has(key));
  if (sort === "newest first" && fresh && keys.length && !(kept !== undefined && playing)) return keys[0];
  return kept;
}

export function formatSize(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  const kib = bytes / 1024;
  if (kib < 1024) return `${kib < 10 ? kib.toFixed(1) : Math.round(kib)} KiB`;
  const mib = kib / 1024;
  return `${mib < 10 ? mib.toFixed(1) : Math.round(mib)} MiB`;
}

function validItem(item) {
  return item && typeof item.filename === "string" && item.filename &&
    typeof item.subfolder === "string" && typeof item.kind === "string" &&
    typeof item.extension === "string";
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

function defaultObserver(callback) {
  if (typeof IntersectionObserver !== "function") return undefined;
  return new IntersectionObserver(callback, { rootMargin: "96px" });
}

function defaultTimers() {
  return {
    set: (callback, delay) => setTimeout(callback, delay),
    clear: (handle) => clearTimeout(handle),
  };
}

function releaseMedia(media) {
  if (!media) return;
  media.pause?.();
  media.removeAttribute?.("src");
  media.load?.();
}

// ---------------------------------------------------------------------------
// Installation
// ---------------------------------------------------------------------------

export function installOutputGallery(
  node,
  {
    document = globalThis.document,
    fetchList = async () => { throw new Error("Output gallery listing is unavailable"); },
    viewUrl = (path) => path,
    fetchBlob,
    loadFile,
    openUrl = (url) => globalThis.open?.(url, "_blank", "noopener"),
    copyText = (text) => globalThis.navigator?.clipboard?.writeText?.(text),
    isConfiguring = () => false,
    events,
    timers = defaultTimers(),
    createObserver = defaultObserver,
  } = {},
) {
  if (node?.comfyClass !== OUTPUT_GALLERY_ID || !document) return undefined;
  if (node[installed]) {
    node[installed].view.restore();
    node[installed].requestRefresh();
    return node[installed].widget;
  }
  const byName = (name) => node.widgets?.find((candidate) => candidate.name === name);
  const widgets = WIDGET_NAMES.map(byName);
  if (!widgets.every(Boolean)) return undefined;

  const root = element(document, "div");
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", "Output gallery");
  Object.assign(root.style, {
    display: "flex", flexDirection: "column", gap: `${UI.gap}px`, padding: `${UI.inset}px`,
    boxSizing: "border-box", width: "100%", minWidth: "0",
  });
  const heading = element(document, "div", { textContent: "Output gallery" });
  initializeRoot(node, root, document, heading);

  const preview = element(document, "div");
  preview.dataset.role = "preview";
  preview.className = "lfgg-gallery-preview";
  Object.assign(preview.style, {
    display: "flex", alignItems: "center", justifyContent: "center", minWidth: "0",
    minHeight: "48px", maxHeight: `${COMPACT_PREVIEW_HEIGHT}px`, background: "#111",
    borderRadius: "6px", overflow: "hidden",
  });
  const caption = element(document, "div");
  caption.dataset.role = "caption";
  Object.assign(caption.style, { fontSize: `${UI.secondarySize}px`, overflowWrap: "anywhere", minWidth: "0" });
  const previewActions = element(document, "div");
  previewActions.dataset.role = "preview-actions";
  const toolbar = element(document, "div");
  toolbar.dataset.role = "toolbar";
  Object.assign(toolbar.style, { display: "flex", flexWrap: "wrap", alignItems: "center", gap: `${UI.tightGap}px ${UI.gap}px`, minWidth: "0" });
  const count = element(document, "span");
  count.dataset.role = "count";
  Object.assign(count.style, { flex: "1 1 120px", minWidth: "0", fontSize: `${UI.secondarySize}px`, overflowWrap: "anywhere" });
  const refreshButton = element(document, "button", { type: "button", textContent: "Refresh" });
  refreshButton.dataset.role = "refresh";
  const disclosure = element(document, "button", { type: "button", textContent: "Show gallery" });
  disclosure.dataset.role = "editor-disclosure";
  disclosure.setAttribute("aria-expanded", "false");
  toolbar.append(count, refreshButton, disclosure);
  const grid = element(document, "div");
  grid.dataset.role = "grid";
  grid.setAttribute("role", "list");
  grid.setAttribute("aria-label", "Gallery items");
  Object.assign(grid.style, {
    display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(96px, 1fr))", gap: `${UI.tightGap}px`, minWidth: "0",
  });
  const status = element(document, "div", { textContent: "Loading…" });
  status.dataset.role = "status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  root.append(heading, preview, caption, previewActions, toolbar, grid, status);

  const controller = {
    items: [],
    keys: new Set(),
    selectedKey: undefined,
    volume: { volume: 1, muted: true },
    request: 0,
    timer: undefined,
    queueRemaining: undefined,
    tiles: new Map(),
    previewMedia: undefined,
    stale: false,
    observer: undefined,
  };
  let applyView;
  const view = createEditorView(node, { isConfiguring, changed: (expanded) => applyView(expanded) });
  controller.view = view;

  const values = () => Object.fromEntries(WIDGET_NAMES.map((name) => [name, byName(name)?.value]));
  const canLoadTiles = () => view.expanded && !node.flags?.collapsed;
  const previewPlaying = () => Boolean(controller.previewMedia) && controller.previewMedia.paused === false;
  const announce = (text) => { status.textContent = text; };
  const selectedItem = () => controller.items.find((item) => itemKey(item) === controller.selectedKey);

  // ---- tiles ---------------------------------------------------------------

  const loadTile = (tile) => {
    if (tile.loaded || !tile.media || !canLoadTiles()) return;
    tile.media.src = tile.src;
    tile.loaded = true;
  };
  const pauseTile = (tile) => {
    if (tile.media?.tagName === "VIDEO" && tile.media.paused === false) tile.media.pause?.();
    if (tile.play) tile.play.setAttribute("aria-label", `Play ${tile.item.filename}`);
  };
  const releaseTile = (tile) => {
    pauseTile(tile);
    controller.observer?.unobserve?.(tile.element);
    if (tile.loaded) releaseMedia(tile.media);
    tile.loaded = false;
  };
  const loadVisibleTiles = () => {
    if (!canLoadTiles()) return;
    for (const tile of controller.tiles.values()) {
      if (controller.observer ? tile.visible : true) loadTile(tile);
    }
  };
  const pauseAllTiles = () => { for (const tile of controller.tiles.values()) pauseTile(tile); };
  const suspend = () => {
    pauseAllTiles();
    if (controller.previewMedia?.paused === false) controller.previewMedia.pause?.();
  };

  const actionsMenu = (item) => {
    const menu = element(document, "details");
    menu.dataset.role = "actions";
    menu.className = "lfgg-gallery-actions";
    const summary = element(document, "summary", { textContent: "Actions" });
    summary.setAttribute("aria-label", `Actions for ${item.filename}`);
    const list = element(document, "div");
    Object.assign(list.style, { display: "grid", gap: `${UI.tightGap}px`, padding: `${UI.tightGap}px 0` });
    const open = element(document, "button", { type: "button", textContent: "Open" });
    open.dataset.role = "open";
    open.addEventListener("click", () => {
      openUrl(viewUrl(buildOutputViewUrl(item)));
      menu.open = false;
    });
    const copy = element(document, "button", { type: "button", textContent: "Copy path" });
    copy.dataset.role = "copy-path";
    copy.addEventListener("click", async () => {
      menu.open = false;
      try {
        await copyText(itemKey(item));
        announce(`Copied path ${itemKey(item)}`);
      } catch (error) {
        announce(`Could not copy path: ${error?.message ?? "clipboard unavailable"}`);
      }
    });
    list.append(open, copy);
    if (item.extension === "png") {
      const load = element(document, "button", { type: "button", textContent: "Load workflow" });
      load.dataset.role = "load-workflow";
      load.disabled = typeof fetchBlob !== "function" || typeof loadFile !== "function";
      load.addEventListener("click", async () => {
        menu.open = false;
        announce(`Loading workflow from ${item.filename}…`);
        try {
          const blob = await fetchBlob(buildOutputViewUrl(item));
          const file = typeof File === "function" ? new File([blob], item.filename, { type: "image/png" }) : blob;
          await loadFile(file);
          announce(`Loaded workflow from ${item.filename}`);
        } catch (error) {
          announce(`Could not load workflow from ${item.filename}: ${error?.message ?? "unknown error"}`);
        }
      });
      list.append(load);
    }
    menu.append(summary, list);
    return menu;
  };

  const placeholderTile = (item) => {
    const placeholder = element(document, "div");
    placeholder.dataset.role = "placeholder";
    Object.assign(placeholder.style, {
      display: "grid", alignContent: "center", gap: `${UI.tightGap}px`, padding: `${UI.tightGap}px`,
      width: "100%", height: "100%", boxSizing: "border-box", fontSize: `${UI.secondarySize}px`, overflowWrap: "anywhere",
    });
    const name = element(document, "span", { textContent: item.filename });
    const kind = element(document, "span", { textContent: item.kind });
    kind.dataset.role = "kind";
    Object.assign(kind.style, { color: "var(--lfgg-secondary)", textTransform: "uppercase", fontSize: "10px" });
    placeholder.append(name, kind);
    return placeholder;
  };

  const createTile = (item) => {
    const key = itemKey(item);
    const tileElement = element(document, "div");
    tileElement.dataset.role = "tile";
    tileElement.dataset.key = key;
    tileElement.setAttribute("role", "listitem");
    tileElement.className = "lfgg-gallery-tile";
    Object.assign(tileElement.style, {
      position: "relative", aspectRatio: "1 / 1", minWidth: "0", background: "#111", borderRadius: "4px", overflow: "hidden",
    });
    const frame = element(document, "div");
    frame.dataset.role = "frame";
    Object.assign(frame.style, { position: "absolute", inset: "0", display: "flex", alignItems: "center", justifyContent: "center" });
    const tile = { item, key, element: tileElement, frame, media: undefined, play: undefined, select: undefined, loaded: false, visible: false, src: undefined };
    if (item.kind === "image") {
      tile.media = element(document, "img", { alt: "", decoding: "async" });
      tile.src = viewUrl(buildOutputViewUrl(item, { preview: TILE_PREVIEW }));
    } else if (item.kind === "video") {
      tile.media = element(document, "video", { muted: true, preload: "metadata", playsInline: true, loop: true });
      tile.src = viewUrl(buildOutputViewUrl(item));
    }
    if (tile.media) {
      Object.assign(tile.media.style, { width: "100%", height: "100%", objectFit: "cover", display: "block" });
      tile.media.addEventListener("error", () => {
        if (!tile.loaded) return;
        frame.replaceChildren(placeholderTile(item));
        tile.media = undefined;
        if (tile.play) tile.play.hidden = true;
      });
      frame.append(tile.media);
    } else {
      frame.append(placeholderTile(item));
    }
    const select = element(document, "button", { type: "button" });
    select.dataset.role = "select";
    select.setAttribute("aria-label", `Select ${item.filename}`);
    select.setAttribute("aria-pressed", "false");
    select.title = key;
    Object.assign(select.style, {
      position: "absolute", inset: "0", width: "100%", height: "100%", padding: "0", margin: "0",
      background: "transparent", border: "2px solid transparent", borderRadius: "4px", cursor: "pointer",
    });
    select.addEventListener("click", () => selectKey(key));
    tile.select = select;
    tileElement.append(frame, select);
    if (item.kind === "video") {
      const play = element(document, "button", { type: "button", textContent: "▶" });
      play.dataset.role = "play";
      play.setAttribute("aria-label", `Play ${item.filename}`);
      Object.assign(play.style, { position: "absolute", left: `${UI.tightGap}px`, bottom: `${UI.tightGap}px`, minHeight: `${UI.controlHeight}px`, minWidth: `${UI.controlHeight}px` });
      play.addEventListener("click", () => {
        if (!tile.media) return;
        if (tile.media.paused === false) {
          tile.media.pause?.();
          play.setAttribute("aria-label", `Play ${item.filename}`);
          play.textContent = "▶";
        } else {
          loadTile(tile);
          tile.media.muted = true;
          Promise.resolve(tile.media.play?.()).catch(() => {});
          play.setAttribute("aria-label", `Pause ${item.filename}`);
          play.textContent = "❚❚";
        }
      });
      tile.play = play;
      tileElement.append(play);
    }
    const menu = actionsMenu(item);
    Object.assign(menu.style, { position: "absolute", right: `${UI.tightGap}px`, top: `${UI.tightGap}px` });
    tileElement.append(menu);
    return tile;
  };

  const markTile = (tile) => {
    const selected = tile.key === controller.selectedKey;
    tile.select.setAttribute("aria-pressed", String(selected));
    tile.select.style.borderColor = selected ? "var(--lfgg-text, currentColor)" : "transparent";
  };

  const sameItem = (a, b) => a.mtime === b.mtime && a.size === b.size && a.kind === b.kind && a.extension === b.extension;

  const renderTiles = () => {
    const next = new Map();
    for (const item of controller.items) {
      const key = itemKey(item);
      const existing = controller.tiles.get(key);
      const tile = existing && sameItem(existing.item, item) ? existing : createTile(item);
      if (existing && tile !== existing) releaseTile(existing);
      tile.item = item;
      next.set(key, tile);
    }
    for (const [key, tile] of controller.tiles) if (next.get(key) !== tile) releaseTile(tile);
    controller.tiles = next;
    grid.replaceChildren(...[...next.values()].map((tile) => tile.element));
    for (const tile of next.values()) {
      markTile(tile);
      if (controller.observer && !tile.observed) {
        controller.observer.observe?.(tile.element);
        tile.observed = true;
      }
    }
    loadVisibleTiles();
  };

  const markSelectedTiles = () => { for (const tile of controller.tiles.values()) markTile(tile); };

  // ---- selected preview ----------------------------------------------------

  const rememberVolume = () => {
    const media = controller.previewMedia;
    if (!media) return;
    controller.volume = { volume: Number.isFinite(media.volume) ? media.volume : 1, muted: Boolean(media.muted) };
  };

  const renderPreview = () => {
    if (controller.previewMedia) {
      controller.previewMedia.removeEventListener?.("volumechange", rememberVolume);
      releaseMedia(controller.previewMedia);
      controller.previewMedia = undefined;
    }
    const item = selectedItem();
    if (!item) {
      const empty = element(document, "div", { textContent: controller.items.length ? "Select an item from the gallery." : "No item selected." });
      empty.dataset.role = "preview-empty";
      Object.assign(empty.style, { padding: `${UI.gap}px`, fontSize: `${UI.secondarySize}px`, color: "var(--lfgg-secondary)" });
      preview.replaceChildren(empty);
      caption.textContent = "";
      previewActions.replaceChildren();
      previewActions.hidden = true;
      return;
    }
    let media;
    if (item.kind === "image") {
      media = element(document, "img", { alt: item.filename, decoding: "async" });
    } else if (item.kind === "video") {
      media = element(document, "video", { controls: true, loop: true, preload: "metadata", playsInline: true });
    } else {
      media = element(document, "audio", { controls: true, preload: "metadata" });
    }
    media.dataset.role = "preview-media";
    Object.assign(media.style, { display: "block", maxWidth: "100%", maxHeight: "100%", width: item.kind === "audio" ? "100%" : "auto", objectFit: "contain" });
    if (item.kind !== "image") {
      media.muted = controller.volume.muted;
      media.volume = controller.volume.volume;
      media.addEventListener("volumechange", rememberVolume);
    }
    media.src = viewUrl(buildOutputViewUrl(item));
    controller.previewMedia = media;
    preview.replaceChildren(media);
    caption.textContent = [itemKey(item), item.kind, formatSize(item.size)].filter(Boolean).join(" · ");
    previewActions.replaceChildren(actionsMenu(item));
    previewActions.hidden = false;
  };

  const selectKey = (key) => {
    if (key === controller.selectedKey) return;
    controller.selectedKey = key;
    markSelectedTiles();
    renderPreview();
    node.setDirtyCanvas?.(true, true);
  };

  // ---- refresh -------------------------------------------------------------

  const setStale = (stale) => {
    controller.stale = stale;
    const opacity = stale ? "0.6" : "";
    grid.style.opacity = opacity;
    preview.style.opacity = opacity;
    grid.setAttribute("aria-busy", String(stale));
  };

  const countText = () => {
    const total = controller.items.length;
    const base = total === 0 ? "no items match" : `${total} ${total === 1 ? "item" : "items"}`;
    return controller.truncated ? `${base} · list may be incomplete: scan cap reached` : base;
  };

  const apply = (result) => {
    if (!result || !Array.isArray(result.items)) throw new Error("Output gallery returned an invalid listing");
    const items = result.items.filter(validItem);
    const nextKey = selectAfterRefresh({
      previousKeys: controller.keys,
      items,
      sort: byName("sort")?.value,
      selectedKey: controller.selectedKey,
      playing: previewPlaying(),
    });
    controller.items = items;
    controller.keys = new Set(items.map(itemKey));
    controller.truncated = result.truncated === true;
    const changed = nextKey !== controller.selectedKey;
    controller.selectedKey = nextKey;
    renderTiles();
    if (changed || !controller.previewMedia) renderPreview();
    count.textContent = countText();
    announce(countText());
    view.fit(true);
    node.setDirtyCanvas?.(true, true);
  };

  const refresh = () => {
    const request = ++controller.request;
    const hadItems = controller.items.length > 0;
    setStale(true);
    announce(hadItems ? "Refreshing…" : "Loading…");
    const run = (async () => {
      try {
        const result = await fetchList(buildListQuery(values()));
        if (request !== controller.request) return false;
        apply(result);
        return true;
      } catch (error) {
        if (request !== controller.request) return false;
        announce(error?.message ?? "Output gallery listing is unavailable");
        return false;
      } finally {
        if (request === controller.request) setStale(false);
      }
    })();
    if (controller.widget) controller.widget.lfggReady = run;
    return run;
  };

  const requestRefresh = () => {
    if (controller.timer !== undefined) timers.clear(controller.timer);
    controller.timer = timers.set(() => {
      controller.timer = undefined;
      refresh();
    }, REFRESH_DEBOUNCE_MS);
  };
  controller.requestRefresh = requestRefresh;
  controller.refresh = refresh;

  // ---- view, events, lifecycle --------------------------------------------

  applyView = (expanded) => {
    if (!expanded && grid.contains?.(document.activeElement)) disclosure.focus?.();
    grid.hidden = !expanded;
    grid.style.display = expanded ? "grid" : "none";
    preview.style.maxHeight = `${expanded ? EXPANDED_PREVIEW_HEIGHT : COMPACT_PREVIEW_HEIGHT}px`;
    disclosure.textContent = expanded ? "Hide gallery" : "Show gallery";
    disclosure.setAttribute("aria-expanded", String(expanded));
    if (expanded) loadVisibleTiles();
    else pauseAllTiles();
  };
  disclosure.addEventListener("click", () => view.setExpanded(!view.expanded));
  refreshButton.addEventListener("click", requestRefresh);
  for (const widget of widgets) composeCallback(widget, requestRefresh);

  const onExecutionSuccess = () => requestRefresh();
  const onStatus = (event) => {
    const remaining = Number(event?.detail?.exec_info?.queue_remaining);
    if (!Number.isFinite(remaining)) return;
    if (remaining === 0 && controller.queueRemaining > 0) requestRefresh();
    controller.queueRemaining = remaining;
  };
  events?.addEventListener?.("execution_success", onExecutionSuccess);
  events?.addEventListener?.("status", onStatus);

  controller.observer = createObserver?.((entries) => {
    for (const entry of entries ?? []) {
      if (entry.target === root) {
        if (!entry.isIntersecting) suspend();
        continue;
      }
      const tile = [...controller.tiles.values()].find((candidate) => candidate.element === entry.target);
      if (!tile) continue;
      tile.visible = Boolean(entry.isIntersecting);
      if (tile.visible) loadTile(tile);
      else pauseTile(tile);
    }
  });
  controller.observer?.observe?.(root);

  const widget = node.addDOMWidget("lfgg_output_gallery", "lfgg_output_gallery", root, {
    serialize: false,
    getMinHeight: () => root.scrollHeight || (view.expanded ? 480 : 300),
    onDraw: () => {
      if (!controller.observer) loadVisibleTiles();
    },
  });
  widget.serialize = false;
  widget.options.serialize = false;
  controller.widget = widget;
  node[installed] = controller;

  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    omitPresentationValues(node, serialized, [widget]);
    return result;
  };
  const originalConfigure = node.onConfigure;
  node.onConfigure = function (...args) {
    const result = originalConfigure?.apply(this, args);
    requestRefresh();
    return result;
  };
  const resizeObserver = typeof ResizeObserver === "function" ? new ResizeObserver(() => view.fit(true)) : undefined;
  resizeObserver?.observe(root);
  const originalRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    events?.removeEventListener?.("execution_success", onExecutionSuccess);
    events?.removeEventListener?.("status", onStatus);
    if (controller.timer !== undefined) timers.clear(controller.timer);
    controller.timer = undefined;
    controller.request += 1;
    controller.observer?.disconnect?.();
    resizeObserver?.disconnect();
    for (const tile of controller.tiles.values()) releaseTile(tile);
    controller.tiles = new Map();
    if (controller.previewMedia) {
      releaseMedia(controller.previewMedia);
      controller.previewMedia = undefined;
    }
    return originalRemoved?.apply(this, args);
  };

  view.restore();
  if (isConfiguring()) widget.lfggReady = Promise.resolve(false);
  else refresh();
  return widget;
}
