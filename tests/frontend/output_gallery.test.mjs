import assert from "node:assert/strict";
import test from "node:test";

import {
  OUTPUT_GALLERY_ID,
  REFRESH_DEBOUNCE_MS,
  buildListQuery,
  buildOutputViewUrl,
  formatSize,
  installOutputGallery,
  itemKey,
  kindOf,
  selectAfterRefresh,
} from "../../web/output_gallery.mjs";

class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.listeners = {};
    this.attributes = {};
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
    this.paused = true;
    this.muted = false;
    this.volume = 1;
    this.open = false;
    this.loadCalls = 0;
  }

  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
  removeEventListener(name, callback) {
    this.listeners[name] = (this.listeners[name] ?? []).filter((item) => item !== callback);
  }
  dispatch(name, event = {}) {
    for (const callback of [...(this.listeners[name] ?? [])]) callback({ target: this, ...event });
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  removeAttribute(name) { delete this.attributes[name]; if (name === "src") delete this.src; }
  contains() { return false; }
  focus() { this.focused = true; }
  load() { this.loadCalls += 1; }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
}

const documentStub = { createElement: (tagName) => new Element(tagName) };

function descendants(element) {
  return [element, ...element.children.flatMap(descendants)];
}

function byRole(element, role) {
  return descendants(element).filter((item) => item.dataset.role === role);
}

function tile(domWidget, key) {
  return byRole(domWidget.element, "tile").find((item) => item.dataset.key === key);
}

function tileMedia(tileElement) {
  return descendants(tileElement).find(({ tagName }) => ["IMG", "VIDEO"].includes(tagName));
}

function previewMedia(domWidget) {
  return byRole(domWidget.element, "preview-media")[0];
}

function status(domWidget) {
  return byRole(domWidget.element, "status")[0];
}

function widget(name, value) {
  return { name, value, callback() {} };
}

function graphNode(overrides = {}) {
  const widgets = [
    widget("path", "runs/wan22"),
    widget("include_subfolders", true),
    widget("media_filter", "all"),
    widget("name_filter", ""),
    widget("sort", "newest first"),
    widget("limit", 24),
  ];
  for (const [name, value] of Object.entries(overrides)) {
    widgets.find((item) => item.name === name).value = value;
  }
  return {
    comfyClass: OUTPUT_GALLERY_ID,
    widgets,
    properties: {},
    flags: {},
    size: [420, 320],
    addDOMWidget(name, type, element, options) {
      const added = { name, type, element, options, serialize: options.serialize };
      widgets.push(added);
      return added;
    },
    computeSize() { return [420, 320]; },
    setSize(size) { this.size = size; },
    setDirtyCanvas() {},
  };
}

function fakeTimers() {
  const queue = new Map();
  let next = 0;
  return {
    set(callback, delay) { next += 1; queue.set(next, { callback, delay }); return next; },
    clear(handle) { queue.delete(handle); },
    flush() {
      const entries = [...queue.values()];
      queue.clear();
      for (const entry of entries) entry.callback();
    },
    get pending() { return queue.size; },
    get delays() { return [...queue.values()].map((entry) => entry.delay); },
  };
}

class Bus {
  constructor() { this.listeners = {}; }
  addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
  removeEventListener(name, callback) {
    this.listeners[name] = (this.listeners[name] ?? []).filter((item) => item !== callback);
  }
  dispatch(name, detail) { for (const callback of [...(this.listeners[name] ?? [])]) callback({ detail }); }
  count(name) { return (this.listeners[name] ?? []).length; }
}

const VIDEO = { filename: "c.mp4", subfolder: "runs/wan22", kind: "video", extension: "mp4", size: 4_193_304, mtime: 3 };
const PNG = { filename: "b.png", subfolder: "runs/wan22", kind: "image", extension: "png", size: 2048, mtime: 2 };
const AUDIO = { filename: "a.wav", subfolder: "", kind: "audio", extension: "wav", size: 100, mtime: 1 };
const ITEMS = [VIDEO, PNG, AUDIO];

function listing(items = ITEMS, extra = {}) {
  return { root: "runs/wan22", items, scanned: items.length, truncated: false, ...extra };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function install(node, { results = [listing()], timers = fakeTimers(), events = new Bus(), ...rest } = {}) {
  const queries = [];
  let index = 0;
  const domWidget = installOutputGallery(node, {
    document: documentStub,
    timers,
    events,
    fetchList: async (query) => {
      queries.push(query);
      const result = results[Math.min(index, results.length - 1)];
      index += 1;
      if (typeof result === "function") return result(query);
      return result;
    },
    ...rest,
  });
  return { domWidget, queries, timers, events };
}

async function installExpanded(options = {}) {
  const node = graphNode();
  node.properties.lfgg_editor_expanded = true;
  const context = install(node, options);
  await context.domWidget.lfggReady;
  return { node, ...context };
}

test("pure helpers build keys, view URLs, list queries, kinds, and sizes", () => {
  assert.equal(itemKey(VIDEO), "runs/wan22/c.mp4");
  assert.equal(itemKey(AUDIO), "a.wav");
  assert.equal(buildOutputViewUrl(VIDEO), "/view?filename=c.mp4&subfolder=runs%2Fwan22&type=output");
  assert.equal(
    buildOutputViewUrl(PNG, { preview: "webp;60" }),
    "/view?filename=b.png&subfolder=runs%2Fwan22&type=output&preview=webp%3B60",
  );
  assert.equal(
    buildListQuery({ path: "runs/wan22", include_subfolders: false, media_filter: "mp4", name_filter: "Wan", sort: "name Z to A", limit: 7 }),
    "path=runs%2Fwan22&include_subfolders=false&media_filter=mp4&name_filter=Wan&sort=name+Z+to+A&limit=7",
  );
  assert.equal(kindOf("JPEG"), "image");
  assert.equal(kindOf("mov"), "video");
  assert.equal(kindOf("flac"), "audio");
  assert.equal(kindOf("exe"), undefined);
  assert.equal(formatSize(512), "512 B");
  assert.equal(formatSize(2048), "2.0 KiB");
  assert.equal(formatSize(4_193_304), "4.0 MiB");
  assert.equal(REFRESH_DEBOUNCE_MS, 500);
});

test("selection rules keep, clear, and auto-select newest only under newest first when idle", () => {
  const previousKeys = new Set(["runs/wan22/b.png", "a.wav"]);
  const base = { previousKeys, items: ITEMS, selectedKey: "runs/wan22/b.png", playing: false };
  assert.equal(selectAfterRefresh({ ...base, sort: "newest first" }), "runs/wan22/c.mp4");
  assert.equal(selectAfterRefresh({ ...base, sort: "newest first", playing: true }), "runs/wan22/b.png");
  assert.equal(selectAfterRefresh({ ...base, sort: "name A to Z" }), "runs/wan22/b.png");
  assert.equal(selectAfterRefresh({ ...base, sort: "newest first", items: [PNG, AUDIO], previousKeys: new Set(["runs/wan22/b.png", "a.wav"]) }), "runs/wan22/b.png");
  assert.equal(selectAfterRefresh({ ...base, sort: "newest first", items: [VIDEO], selectedKey: "runs/wan22/b.png", playing: true }), "runs/wan22/c.mp4");
  assert.equal(selectAfterRefresh({ previousKeys: new Set(), items: [], sort: "newest first", selectedKey: "x", playing: false }), undefined);
});

test("installs a non-serialized compact gallery on a new node and lists once with the widget values", async () => {
  const node = graphNode();
  const originalValues = node.widgets.map(({ value }) => value);
  const { domWidget, queries } = install(node);
  assert.equal(status(domWidget).textContent, "Loading…");
  await domWidget.lfggReady;

  assert.equal(domWidget.serialize, false);
  assert.equal(domWidget.options.serialize, false);
  assert.deepEqual(node.widgets.slice(0, 6).map(({ value }) => value), originalValues);
  assert.deepEqual(queries, [
    "path=runs%2Fwan22&include_subfolders=true&media_filter=all&name_filter=&sort=newest+first&limit=24",
  ]);
  assert.deepEqual(Object.keys(node.properties), []);
  const grid = byRole(domWidget.element, "grid")[0];
  assert.equal(grid.hidden, true);
  assert.equal(byRole(domWidget.element, "tile").length, 3);
  assert.equal(byRole(domWidget.element, "tile").every((item) => tileMedia(item)?.src === undefined), true);
  const preview = previewMedia(domWidget);
  assert.equal(preview.tagName, "VIDEO");
  assert.equal(preview.src, "/view?filename=c.mp4&subfolder=runs%2Fwan22&type=output");
  assert.equal(preview.controls, true);
  assert.equal(preview.loop, true);
  assert.equal(preview.muted, true);
  assert.equal(preview.paused, true);
  assert.equal(byRole(domWidget.element, "caption")[0].textContent, "runs/wan22/c.mp4 · video · 4.0 MiB");
  assert.equal(byRole(domWidget.element, "count")[0].textContent, "3 items");
  assert.equal(status(domWidget).textContent, "3 items");
  assert.equal(status(domWidget).attributes["aria-live"], "polite");
  assert.equal(byRole(domWidget.element, "preview")[0].style.maxHeight, "180px");
});

test("configured reload installs once, defers listing until loaded, and restores the expanded grid", async () => {
  const node = graphNode({ path: "saved", sort: "name A to Z" });
  node.properties.lfgg_editor_expanded = true;
  let configuring = true;
  const timers = fakeTimers();
  const { domWidget, queries } = install(node, { timers, isConfiguring: () => configuring });
  await domWidget.lfggReady;
  assert.deepEqual(queries, []);

  configuring = false;
  node.onConfigure?.();
  const again = installOutputGallery(node, { document: documentStub, timers });
  assert.equal(again, domWidget);
  assert.equal(node.widgets.filter(({ name }) => name === "lfgg_output_gallery").length, 1);
  assert.equal(timers.pending, 1);
  timers.flush();
  await domWidget.lfggReady;

  assert.deepEqual(queries, [
    "path=saved&include_subfolders=true&media_filter=all&name_filter=&sort=name+A+to+Z&limit=24",
  ]);
  assert.equal(byRole(domWidget.element, "grid")[0].hidden, false);
  assert.equal(byRole(domWidget.element, "editor-disclosure")[0].attributes["aria-expanded"], "true");
  assert.equal(byRole(domWidget.element, "preview")[0].style.maxHeight, "360px");
  const serialized = { widgets_values: ["saved", true, "all", "", "name A to Z", 24, null] };
  node.onSerialize(serialized);
  assert.deepEqual(serialized.widgets_values, ["saved", true, "all", "", "name A to Z", 24]);
  assert.deepEqual(Object.keys(node.properties), ["lfgg_editor_expanded"]);
});

test("refreshes from the button, execution_success, the status zero transition, and widget changes", async () => {
  const node = graphNode();
  const { domWidget, queries, timers, events } = install(node);
  await domWidget.lfggReady;
  assert.equal(queries.length, 1);

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  assert.deepEqual(timers.delays, [REFRESH_DEBOUNCE_MS]);
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(queries.length, 2);

  events.dispatch("execution_success", {});
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(queries.length, 3);

  events.dispatch("status", { exec_info: { queue_remaining: 0 } });
  assert.equal(timers.pending, 0);
  events.dispatch("status", { exec_info: { queue_remaining: 2 } });
  events.dispatch("status", { exec_info: { queue_remaining: 1 } });
  assert.equal(timers.pending, 0);
  events.dispatch("status", { exec_info: { queue_remaining: 0 } });
  assert.equal(timers.pending, 1);
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(queries.length, 4);
  events.dispatch("status", { exec_info: { queue_remaining: 0 } });
  events.dispatch("status", {});
  assert.equal(timers.pending, 0);

  for (const [index, name] of ["path", "include_subfolders", "media_filter", "name_filter", "sort", "limit"].entries()) {
    const changed = node.widgets.find((item) => item.name === name);
    changed.value = name === "include_subfolders" ? false : name === "limit" ? 5 : `v${index}`;
    changed.callback(changed.value);
    assert.equal(timers.pending, 1);
    timers.flush();
    await domWidget.lfggReady;
    assert.equal(queries.length, 5 + index);
  }
  assert.equal(queries.at(-1), "path=v0&include_subfolders=false&media_filter=v2&name_filter=v3&sort=v4&limit=5");
});

test("collapses a burst of triggers into one debounced request", async () => {
  const node = graphNode();
  const { domWidget, queries, timers, events } = install(node);
  await domWidget.lfggReady;

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  byRole(domWidget.element, "refresh")[0].dispatch("click");
  events.dispatch("execution_success", {});
  events.dispatch("status", { exec_info: { queue_remaining: 1 } });
  events.dispatch("status", { exec_info: { queue_remaining: 0 } });
  node.widgets[0].callback("x");
  assert.equal(timers.pending, 1);
  timers.flush();
  await domWidget.lfggReady;

  assert.equal(queries.length, 2);
});

test("keeps a selection across refresh, clears it when missing, and auto-selects newest only when idle under newest first", async () => {
  const fresh = { filename: "d.webm", subfolder: "runs/wan22", kind: "video", extension: "webm", size: 10, mtime: 4 };
  const node = graphNode();
  node.properties.lfgg_editor_expanded = true;
  const results = [listing(), listing(), listing([fresh, ...ITEMS]), listing([AUDIO])];
  const { domWidget, timers } = install(node, { results });
  await domWidget.lfggReady;

  byRole(tile(domWidget, "runs/wan22/b.png"), "select")[0].dispatch("click");
  assert.equal(previewMedia(domWidget).tagName, "IMG");
  assert.equal(byRole(tile(domWidget, "runs/wan22/b.png"), "select")[0].attributes["aria-pressed"], "true");
  assert.equal(byRole(tile(domWidget, "runs/wan22/c.mp4"), "select")[0].attributes["aria-pressed"], "false");

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(byRole(domWidget.element, "caption")[0].textContent, "runs/wan22/b.png · image · 2.0 KiB");

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(byRole(domWidget.element, "caption")[0].textContent, "runs/wan22/d.webm · video · 10 B");
  assert.equal(byRole(domWidget.element, "tile").length, 4);

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(previewMedia(domWidget), undefined);
  assert.equal(byRole(domWidget.element, "preview-empty")[0].textContent, "Select an item from the gallery.");
  assert.equal(byRole(domWidget.element, "caption")[0].textContent, "");
  assert.equal(byRole(domWidget.element, "preview-actions")[0].hidden, true);
});

test("leaves a playing selection alone and ignores newest for other sorts", async () => {
  const fresh = { filename: "d.webm", subfolder: "runs/wan22", kind: "video", extension: "webm", size: 10, mtime: 4 };
  const playingNode = graphNode();
  const playing = install(playingNode, { results: [listing(), listing([fresh, ...ITEMS])] });
  await playing.domWidget.lfggReady;
  const player = previewMedia(playing.domWidget);
  await player.play();
  byRole(playing.domWidget.element, "refresh")[0].dispatch("click");
  playing.timers.flush();
  await playing.domWidget.lfggReady;
  assert.equal(previewMedia(playing.domWidget), player);
  assert.equal(player.paused, false);
  assert.equal(byRole(playing.domWidget.element, "tile").length, 4);

  const namedNode = graphNode({ sort: "name A to Z" });
  const named = install(namedNode, { results: [listing([PNG]), listing([fresh, PNG])] });
  await named.domWidget.lfggReady;
  assert.equal(previewMedia(named.domWidget), undefined);
  assert.equal(byRole(named.domWidget.element, "preview-empty")[0].textContent, "Select an item from the gallery.");
  byRole(named.domWidget.element, "refresh")[0].dispatch("click");
  named.timers.flush();
  await named.domWidget.lfggReady;
  assert.equal(previewMedia(named.domWidget), undefined);
});

test("starts the preview muted, keeps tiles muted, and applies remembered volume to the next item", async () => {
  const { domWidget } = await installExpanded();
  const player = previewMedia(domWidget);
  assert.equal(player.muted, true);
  assert.equal(player.volume, 1);
  for (const item of byRole(domWidget.element, "tile")) {
    const media = tileMedia(item);
    if (media?.tagName === "VIDEO") assert.equal(media.muted, true);
  }

  player.muted = false;
  player.volume = 0.4;
  player.dispatch("volumechange");
  byRole(tile(domWidget, "a.wav"), "select")[0].dispatch("click");

  const audio = previewMedia(domWidget);
  assert.equal(audio.tagName, "AUDIO");
  assert.equal(audio.controls, true);
  assert.equal(audio.muted, false);
  assert.equal(audio.volume, 0.4);
  assert.equal(audio.paused, true);
  assert.equal(player.attributes.src, undefined);
  assert.equal(player.src, undefined);
});

test("announces empty, truncated, not-found, and error states while preserving the last valid list", async () => {
  const node = graphNode();
  const results = [
    listing([]),
    listing(ITEMS, { truncated: true, scanned: 20_000 }),
    () => { throw new Error("LFGG Output Gallery: folder not found under output: runs/x"); },
    () => { throw new Error("LFGG Output Gallery: path must stay inside the ComfyUI output root"); },
  ];
  const { domWidget, timers } = install(node, { results });
  await domWidget.lfggReady;
  assert.equal(status(domWidget).textContent, "no items match");
  assert.equal(byRole(domWidget.element, "count")[0].textContent, "no items match");
  assert.equal(byRole(domWidget.element, "preview-empty")[0].textContent, "No item selected.");

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(status(domWidget).textContent, "3 items · list may be incomplete: scan cap reached");

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(status(domWidget).textContent, "LFGG Output Gallery: folder not found under output: runs/x");
  assert.equal(byRole(domWidget.element, "tile").length, 3);
  assert.equal(previewMedia(domWidget).src, "/view?filename=c.mp4&subfolder=runs%2Fwan22&type=output");

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(status(domWidget).textContent, "LFGG Output Gallery: path must stay inside the ComfyUI output root");
  assert.equal(byRole(domWidget.element, "tile").length, 3);
  assert.equal(byRole(domWidget.element, "grid")[0].style.opacity, "");
});

test("dims the previous list while a refresh is in flight and ignores stale responses", async () => {
  const node = graphNode();
  const pending = deferred();
  const results = [listing(), () => pending.promise, listing([AUDIO])];
  const { domWidget, timers } = install(node, { results });
  await domWidget.lfggReady;

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  timers.flush();
  assert.equal(status(domWidget).textContent, "Refreshing…");
  assert.equal(byRole(domWidget.element, "grid")[0].style.opacity, "0.6");
  assert.equal(byRole(domWidget.element, "grid")[0].attributes["aria-busy"], "true");
  assert.equal(byRole(domWidget.element, "tile").length, 3);

  byRole(domWidget.element, "refresh")[0].dispatch("click");
  timers.flush();
  await domWidget.lfggReady;
  assert.equal(byRole(domWidget.element, "tile").length, 1);
  pending.resolve(listing([PNG, VIDEO]));
  await pending.promise;
  await Promise.resolve();
  assert.equal(byRole(domWidget.element, "tile").length, 1);
  assert.equal(status(domWidget).textContent, "1 item");
  assert.equal(byRole(domWidget.element, "grid")[0].style.opacity, "");
});

test("loads tile media only when expanded, not collapsed, and pauses tiles on compact", async () => {
  const node = graphNode();
  const { domWidget } = install(node);
  await domWidget.lfggReady;
  const videoTile = () => tileMedia(tile(domWidget, "runs/wan22/c.mp4"));
  const imageTile = () => tileMedia(tile(domWidget, "runs/wan22/b.png"));
  assert.equal(videoTile().src, undefined);
  assert.equal(imageTile().src, undefined);
  assert.equal(byRole(tile(domWidget, "a.wav"), "placeholder")[0].children[1].textContent, "audio");

  node.flags.collapsed = true;
  byRole(domWidget.element, "editor-disclosure")[0].dispatch("click");
  assert.equal(node.properties.lfgg_editor_expanded, true);
  assert.equal(videoTile().src, undefined);
  node.flags.collapsed = false;
  domWidget.options.onDraw();
  assert.equal(videoTile().src, "/view?filename=c.mp4&subfolder=runs%2Fwan22&type=output");
  assert.equal(imageTile().src, "/view?filename=b.png&subfolder=runs%2Fwan22&type=output&preview=webp%3B60");

  const play = byRole(tile(domWidget, "runs/wan22/c.mp4"), "play")[0];
  play.dispatch("click");
  await Promise.resolve();
  assert.equal(videoTile().paused, false);
  assert.equal(videoTile().muted, true);
  assert.equal(play.attributes["aria-label"], "Pause c.mp4");
  byRole(domWidget.element, "editor-disclosure")[0].dispatch("click");
  assert.equal(videoTile().paused, true);
  assert.equal(play.attributes["aria-label"], "Play c.mp4");
  assert.equal(byRole(domWidget.element, "grid")[0].hidden, true);
});

test("defers off-canvas tiles through the observer, pauses when the root leaves view, and releases media on removal", async () => {
  let callback;
  const observed = [];
  let disconnected = false;
  const observer = {
    observe(element) { observed.push(element); },
    unobserve() {},
    disconnect() { disconnected = true; },
  };
  const { node, domWidget, events } = await installExpanded({
    createObserver: (handler) => { callback = handler; return observer; },
  });
  const videoTile = tile(domWidget, "runs/wan22/c.mp4");
  const imageTile = tile(domWidget, "runs/wan22/b.png");
  assert.ok(observed.includes(domWidget.element));
  assert.ok(observed.includes(videoTile));
  assert.equal(tileMedia(videoTile).src, undefined);

  callback([{ target: videoTile, isIntersecting: true }, { target: imageTile, isIntersecting: false }]);
  assert.equal(tileMedia(videoTile).src, "/view?filename=c.mp4&subfolder=runs%2Fwan22&type=output");
  assert.equal(tileMedia(imageTile).src, undefined);

  byRole(videoTile, "play")[0].dispatch("click");
  const player = previewMedia(domWidget);
  await player.play();
  callback([{ target: domWidget.element, isIntersecting: false }]);
  assert.equal(tileMedia(videoTile).paused, true);
  assert.equal(player.paused, true);

  node.onRemoved();
  assert.equal(disconnected, true);
  assert.equal(events.count("execution_success"), 0);
  assert.equal(events.count("status"), 0);
  assert.equal(tileMedia(videoTile).src, undefined);
  assert.equal(player.src, undefined);
  assert.equal(byRole(domWidget.element, "tile").length, 3);
});

test("falls back to a placeholder tile when a video cannot be decoded", async () => {
  const { domWidget } = await installExpanded();
  const videoTile = tile(domWidget, "runs/wan22/c.mp4");
  const media = tileMedia(videoTile);
  assert.ok(media.src);

  media.dispatch("error");

  assert.equal(tileMedia(videoTile), undefined);
  const placeholder = byRole(videoTile, "placeholder")[0];
  assert.equal(placeholder.children[0].textContent, "c.mp4");
  assert.equal(placeholder.children[1].textContent, "video");
  assert.equal(byRole(videoTile, "play")[0].hidden, true);
});

test("offers open, copy path, and PNG-only load workflow actions on tiles and the preview", async () => {
  const opened = [];
  const copied = [];
  const blobs = [];
  const loaded = [];
  const { domWidget } = await installExpanded({
    viewUrl: (path) => `http://host/api${path}`,
    openUrl: (url) => opened.push(url),
    copyText: async (text) => copied.push(text),
    fetchBlob: async (path) => { blobs.push(path); return "png-bytes"; },
    loadFile: async (file) => loaded.push(file),
  });
  const pngTile = tile(domWidget, "runs/wan22/b.png");
  const videoTile = tile(domWidget, "runs/wan22/c.mp4");
  assert.equal(byRole(pngTile, "load-workflow").length, 1);
  assert.equal(byRole(videoTile, "load-workflow").length, 0);
  assert.equal(byRole(tile(domWidget, "a.wav"), "load-workflow").length, 0);
  assert.equal(byRole(videoTile, "actions")[0].children[0].attributes["aria-label"], "Actions for c.mp4");

  byRole(pngTile, "open")[0].dispatch("click");
  assert.deepEqual(opened, ["http://host/api/view?filename=b.png&subfolder=runs%2Fwan22&type=output"]);
  byRole(pngTile, "copy-path")[0].dispatch("click");
  await Promise.resolve();
  assert.deepEqual(copied, ["runs/wan22/b.png"]);
  assert.equal(status(domWidget).textContent, "Copied path runs/wan22/b.png");

  byRole(pngTile, "load-workflow")[0].dispatch("click");
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert.deepEqual(blobs, ["/view?filename=b.png&subfolder=runs%2Fwan22&type=output"]);
  assert.equal(loaded.length, 1);
  assert.equal(loaded[0].name, "b.png");
  assert.equal(loaded[0].type, "image/png");
  assert.equal(status(domWidget).textContent, "Loaded workflow from b.png");

  const previewActions = byRole(domWidget.element, "preview-actions")[0];
  assert.equal(byRole(previewActions, "open").length, 1);
  assert.equal(byRole(previewActions, "copy-path").length, 1);
  assert.equal(byRole(previewActions, "load-workflow").length, 0);
  byRole(pngTile, "select")[0].dispatch("click");
  assert.equal(byRole(byRole(domWidget.element, "preview-actions")[0], "load-workflow").length, 1);
});

test("ignores nodes of other types and nodes missing the standard widgets", () => {
  assert.equal(installOutputGallery({ comfyClass: "Other", widgets: [] }, { document: documentStub }), undefined);
  const node = graphNode();
  node.widgets.splice(0, 1);
  assert.equal(installOutputGallery(node, { document: documentStub }), undefined);
});
