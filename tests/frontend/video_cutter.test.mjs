import assert from "node:assert/strict";
import test from "node:test";

import {
  formatTimecode,
  installVideoCutter,
  parseTimecode,
  resolveLoadVideoInput,
} from "../../web/video_cutter.mjs";

class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.listeners = {};
    this.value = "";
    this.checked = false;
    this.disabled = false;
    this.currentTime = 0;
    this.paused = true;
    this.drawCount = 0;
  }

  append(...children) {
    this.children.push(...children);
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  addEventListener(name, callback) {
    (this.listeners[name] ??= []).push(callback);
  }

  dispatch(name, event = {}) {
    for (const callback of this.listeners[name] ?? []) {
      callback({ target: this, preventDefault() {}, ...event });
    }
  }

  setAttribute(name, value) {
    this[name] = String(value);
  }

  removeAttribute(name) {
    delete this[name];
  }

  getContext() {
    return { drawImage: () => { this.drawCount += 1; } };
  }

  play() {
    this.paused = false;
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
  }
}

const documentStub = {
  createElement: (tagName) => new Element(tagName),
};

function descendants(element) {
  return [element, ...element.children.flatMap(descendants)];
}

function widget(name, value) {
  return { name, value, callback() {} };
}

function graphNode({ frameStartConnected = false } = {}) {
  const widgets = [
    widget("selection_mode", "Time"),
    widget("start_time", 1),
    widget("end_time", 2),
    widget("first_frame", 0),
    widget("last_frame", -1),
  ];
  const node = {
    comfyClass: "LFGG_VideoCutter",
    widgets,
    inputs: [
      { name: "video", link: 1 },
      { name: "start_time", link: null },
      { name: "end_time", link: null },
      { name: "first_frame", link: frameStartConnected ? 7 : null },
      { name: "last_frame", link: null },
    ],
    size: [320, 240],
    addDOMWidget(name, type, element, options) {
      const added = { name, type, element, options, serialize: options.serialize };
      widgets.push(added);
      return added;
    },
    setSize(size) {
      this.size = size;
    },
    setDirtyCanvas() {},
  };
  return node;
}

function directGraph(file = "clips/a b.mp4") {
  const load = { id: 2, type: "LoadVideo", widgets: [widget("file", file)] };
  return {
    links: { 1: { origin_id: 2 } },
    getNodeById: (id) => (id === 2 ? load : undefined),
    load,
  };
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

test("formats and parses editable millisecond timecode", () => {
  assert.equal(formatTimecode(3723.456), "01:02:03.456");
  assert.equal(parseTimecode("01:02:03.456"), 3723.456);
  assert.equal(parseTimecode("bad"), undefined);
});

test("resolves direct LoadVideo through simple reroutes only", () => {
  const load = { id: 3, type: "LoadVideo", widgets: [widget("file", "source.mp4")] };
  const reroute = { id: 2, type: "Reroute", inputs: [{ link: 2 }] };
  const graph = {
    links: { 1: { origin_id: 2 }, 2: { origin_id: 3 } },
    getNodeById: (id) => ({ 2: reroute, 3: load })[id],
  };
  const node = { inputs: [{ name: "video", link: 1 }] };

  assert.equal(resolveLoadVideoInput(node, graph), "source.mp4");
  reroute.inputs[0].link = 1;
  assert.equal(resolveLoadVideoInput(node, graph), undefined);
});

test("installs a non-serialized bounded editor and preloads direct input video", async () => {
  const node = graphNode();
  const originalValues = node.widgets.map(({ value }) => value);
  const requests = [];

  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    buildViewUrl: (value) => `/view/native/${value}`,
    fetchMetadata: async (value) => {
      requests.push(value);
      return { duration: 10, reported_fps: 30, nominal_frame_count: 300 };
    },
  });
  await domWidget.lfggReady;

  const elements = descendants(domWidget.element);
  assert.equal(domWidget.serialize, false);
  assert.equal(domWidget.options.serialize, false);
  assert.deepEqual(node.widgets.slice(0, 5).map(({ value }) => value), originalValues);
  assert.deepEqual(requests, ["clips/a b.mp4"]);
  assert.equal(elements.find(({ tagName }) => tagName === "VIDEO").src, "/view/native/clips/a b.mp4");
  assert.equal(elements.filter(({ tagName }) => tagName === "CANVAS").length, 10);
  assert.equal(elements.filter(({ dataset }) => dataset.role === "boundary").length, 2);
  assert.equal(elements.some(({ tagName }) => tagName === "AUDIO"), false);
});

test("keeps same-source playback and metadata through unrelated connection changes", async () => {
  const node = graphNode();
  const graph = directGraph();
  const metadata = deferred();
  let requests = 0;
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: () => graph,
    fetchMetadata: () => { requests += 1; return metadata.promise; },
  });
  node.inputs.find(({ name }) => name === "start_time").link = 7;
  node.onConnectionsChange();
  assert.equal(requests, 1);
  metadata.resolve({ duration: 10, reported_fps: 30, nominal_frame_count: 300 });
  await domWidget.lfggReady;
  const elements = descendants(domWidget.element);
  const thumbnail = elements.find(({ tagName }) => tagName === "CANVAS");
  const draws = thumbnail.drawCount;
  const player = elements.find(({ tagName }) => tagName === "VIDEO");
  player.currentTime = 4;
  node.onConnectionsChange();
  await domWidget.lfggReady;
  assert.equal(requests, 1);
  assert.equal(player.currentTime, 4);
  assert.equal(thumbnail.drawCount, draws);
  assert.equal(elements.find(({ dataset }) => dataset.boundary === "start").disabled, true);
  node.inputs[0].link = null;
  node.onConnectionsChange();
  assert.equal(player.src, undefined);
  node.inputs[0].link = 1;
  node.onConnectionsChange();
  await domWidget.lfggReady;
  assert.equal(requests, 2);
});

test("restores disconnected boundaries from saved widgets without reloading video", async () => {
  const node = graphNode();
  const start = node.inputs.find(({ name }) => name === "start_time");
  const end = node.inputs.find(({ name }) => name === "end_time");
  start.link = 7;
  end.link = 8;
  let requests = 0;
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    fetchMetadata: async () => {
      requests += 1;
      return { duration: 10, reported_fps: 30, nominal_frame_count: 300 };
    },
  });
  await domWidget.lfggReady;
  node.onExecuted({ video_cutter: [{
    duration: 10, reported_fps: 30, nominal_frame_count: 300,
    selection_start: 3, selection_end: 5,
  }] });
  const elements = descendants(domWidget.element);
  const startHandle = elements.find(({ dataset }) => dataset.boundary === "start");
  const endHandle = elements.find(({ dataset }) => dataset.boundary === "end");
  start.link = null;
  node.onConnectionsChange();
  assert.equal(startHandle.value, "30");
  assert.equal(endHandle.value, "150");
  end.link = null;
  node.onConnectionsChange();
  assert.equal(endHandle.value, "60");
  assert.equal(requests, 1);
  assert.deepEqual(node.widgets.slice(1, 3).map(({ value }) => value), [1, 2]);
});

test("defers filmstrip decoding until an expanded node is drawn", async () => {
  const node = graphNode();
  node.flags = { collapsed: true };
  node.properties = { lfgg_editor_expanded: true };
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    fetchMetadata: async () => ({ duration: 10, reported_fps: 30, nominal_frame_count: 300 }),
  });
  await domWidget.lfggReady;
  const thumbnail = descendants(domWidget.element).find(({ tagName }) => tagName === "CANVAS");
  assert.equal(thumbnail.drawCount, 0);
  node.flags.collapsed = false;
  domWidget.options.onDraw();
  assert.equal(thumbnail.drawCount, 1);
  domWidget.options.onDraw();
  assert.equal(thumbnail.drawCount, 1);
});

test("gives video boundaries visible labels and sliders accessible names", () => {
  const domWidget = installVideoCutter(graphNode(), { document: documentStub });
  const elements = descendants(domWidget.element);
  for (const role of ["start-timecode", "end-timecode", "first-frame", "last-frame"]) {
    const input = elements.find(({ dataset }) => dataset.role === role);
    const label = elements.find(({ tagName, children }) => tagName === "LABEL" && children.includes(input));
    assert.ok(label);
    assert.ok(label.children.some(({ tagName, textContent }) => tagName === "SPAN" && textContent));
  }
  for (const input of elements.filter(({ type }) => type === "range")) {
    assert.ok(input["aria-label"]);
  }
});

test("removes the DOM widget positional hole from workflow serialization", async () => {
  const node = graphNode();
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    fetchMetadata: async () => ({ duration: 10, reported_fps: 30, nominal_frame_count: 300 }),
  });
  await domWidget.lfggReady;
  const serialized = { widgets_values: ["Time", 1, 2, 0, -1, null] };

  node.onSerialize(serialized);

  assert.deepEqual(serialized.widgets_values, ["Time", 1, 2, 0, -1]);
});

test("flags invalid saved bounds after a direct source changes without resetting them", async () => {
  const node = graphNode();
  const graph = directGraph();
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: () => graph,
    buildViewUrl: String,
    fetchMetadata: async (source) => ({
      duration: source === "short.mp4" ? 1 : 10,
      reported_fps: 30,
      nominal_frame_count: source === "short.mp4" ? 30 : 300,
    }),
  });
  await domWidget.lfggReady;
  graph.load.widgets[0].value = "short.mp4";
  domWidget.options.onDraw();
  await domWidget.lfggReady;

  const status = descendants(domWidget.element).find(({ dataset }) => dataset.role === "status");
  assert.deepEqual(node.widgets.slice(1, 5).map(({ value }) => value), [1, 2, 0, -1]);
  assert.match(status.textContent, /outside the source bounds/);
});

test("new-source failure clears preview controls but preserves backend widgets", async () => {
  const node = graphNode();
  const graph = directGraph("working.mp4");
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: () => graph,
    buildViewUrl: String,
    fetchMetadata: async (source) => {
      if (source === "broken.mp4") throw new Error("metadata failed");
      return { duration: 10, reported_fps: 30, nominal_frame_count: 300 };
    },
  });
  await domWidget.lfggReady;
  const elements = descendants(domWidget.element);
  const customInputs = elements.filter(
    ({ dataset }) => dataset.role === "boundary" || [
      "playhead", "start-timecode", "end-timecode", "first-frame", "last-frame",
    ].includes(dataset.role),
  );
  assert.equal(customInputs.every(({ disabled }) => !disabled), true);

  graph.load.widgets[0].value = "broken.mp4";
  domWidget.options.onDraw();
  assert.equal(customInputs.every(({ disabled }) => disabled), true);
  await domWidget.lfggReady;

  const persisted = node.widgets.slice(0, 5).map(({ value }) => value);
  const startTimecode = elements.find(({ dataset }) => dataset.role === "start-timecode");
  startTimecode.value = "00:00:03.000";
  startTimecode.dispatch("change");
  assert.deepEqual(node.widgets.slice(0, 5).map(({ value }) => value), persisted);
  assert.match(
    elements.find(({ dataset }) => dataset.role === "status").textContent,
    /metadata preview is unavailable/,
  );
});

test("stale source rejection cannot overwrite newer metadata success", async () => {
  const node = graphNode();
  const graph = directGraph("a.mp4");
  const a = deferred();
  const b = deferred();
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: () => graph,
    buildViewUrl: String,
    fetchMetadata: (source) => (source === "a.mp4" ? a.promise : b.promise),
  });
  const aReady = domWidget.lfggReady;

  graph.load.widgets[0].value = "b.mp4";
  domWidget.options.onDraw();
  b.resolve({ duration: 10, reported_fps: 30, nominal_frame_count: 300 });
  await domWidget.lfggReady;
  const status = descendants(domWidget.element).find(({ dataset }) => dataset.role === "status");
  const successfulStatus = status.textContent;

  a.reject(new Error("stale metadata failure"));
  await aReady;

  assert.equal(status.textContent, successfulStatus);
});

test("clears a direct preview when a computed input replaces it", async () => {
  const node = graphNode();
  const graph = directGraph();
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: () => graph,
    buildViewUrl: String,
    fetchMetadata: async () => ({
      duration: 10,
      reported_fps: 30,
      nominal_frame_count: 300,
    }),
  });
  await domWidget.lfggReady;

  graph.links[1] = { origin_id: 3 };
  node.onConnectionsChange();

  const player = descendants(domWidget.element).find(({ tagName }) => tagName === "VIDEO");
  assert.equal(player.src, undefined);
});

test("mode changes preserve one selection and connected active boundary is readonly", async () => {
  const node = graphNode({ frameStartConnected: true });
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    buildViewUrl: String,
    fetchMetadata: async () => ({
      duration: 10,
      reported_fps: 30,
      nominal_frame_count: 300,
    }),
  });
  await domWidget.lfggReady;

  node.widgets[0].value = "Frames";
  node.widgets[0].callback("Frames");

  assert.equal(node.widgets[1].value, 1);
  assert.equal(node.widgets[2].value, 2);
  assert.equal(node.widgets[3].value, 30);
  assert.equal(node.widgets[4].value, 59);
  const firstBoundary = descendants(domWidget.element).find(
    ({ dataset }) => dataset.role === "boundary" && dataset.boundary === "start",
  );
  assert.equal(firstBoundary.disabled, true);
});

test("boundary handles restore after a rejected crossing without changing inputs", async () => {
  const node = graphNode();
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    buildViewUrl: String,
    fetchMetadata: async () => ({
      duration: 10,
      reported_fps: 30,
      nominal_frame_count: 300,
    }),
  });
  await domWidget.lfggReady;
  const elements = descendants(domWidget.element);
  const boundaries = elements.filter(({ dataset }) => dataset.role === "boundary");

  boundaries[0].value = "60";
  boundaries[0].dispatch("input");

  assert.deepEqual(boundaries.map(({ value }) => value), ["30", "60"]);
  assert.deepEqual(node.widgets.slice(1, 5).map(({ value }) => value), [1, 2, 0, -1]);
});

test("focus-scoped frame and mark shortcuts control the source player", async () => {
  const node = graphNode();
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    buildViewUrl: String,
    fetchMetadata: async () => ({
      duration: 10,
      reported_fps: 30,
      nominal_frame_count: 300,
    }),
  });
  await domWidget.lfggReady;
  const player = descendants(domWidget.element).find(({ tagName }) => tagName === "VIDEO");
  player.currentTime = 1;

  domWidget.element.dispatch("keydown", { key: "ArrowRight", target: domWidget.element });
  assert.equal(player.currentTime, 31 / 30);
  domWidget.element.dispatch("keydown", { key: "i", target: domWidget.element });
  assert.equal(node.widgets[1].value, 31 / 30);
  domWidget.element.dispatch("keydown", { key: " ", target: domWidget.element });
  assert.equal(player.paused, false);
});

test("playback resumes at selection start while paused scrubbing stays unrestricted", async () => {
  const node = graphNode();
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    buildViewUrl: String,
    fetchMetadata: async () => ({
      duration: 10,
      reported_fps: 30,
      nominal_frame_count: 300,
    }),
  });
  await domWidget.lfggReady;
  const player = descendants(domWidget.element).find(({ tagName }) => tagName === "VIDEO");

  player.pause();
  player.currentTime = 5;
  player.dispatch("timeupdate");
  assert.equal(player.currentTime, 5);

  player.play();
  player.dispatch("play");
  assert.equal(player.currentTime, 1);
});

test("execution metadata controls connected boundaries while direct source stays scrubbable", async () => {
  const node = graphNode();
  node.inputs.find(({ name }) => name === "start_time").link = 7;
  node.inputs.find(({ name }) => name === "end_time").link = 8;
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    buildViewUrl: (source) => `/view/native/${source}`,
    buildOutputViewUrl: () => "/view/generated/cut.mp4",
    fetchMetadata: async () => ({
      duration: 10,
      reported_fps: 30,
      nominal_frame_count: 300,
    }),
  });
  await domWidget.lfggReady;
  const elements = descendants(domWidget.element);
  const player = elements.find(({ tagName }) => tagName === "VIDEO");

  node.onExecuted({
    images: [{ filename: "cut.mp4", subfolder: "", type: "temp" }],
    video_cutter: [{
      duration: 10,
      reported_fps: 30,
      nominal_frame_count: 300,
      selection_start: 3,
      selection_end: 5,
    }],
  });

  assert.equal(player.src, "/view/native/clips/a b.mp4");
  assert.deepEqual(node.widgets.slice(1, 5).map(({ value }) => value), [1, 2, 0, -1]);
  assert.equal(elements.find(({ dataset }) => dataset.boundary === "start").value, "90");
  assert.equal(elements.find(({ dataset }) => dataset.boundary === "end").value, "150");
  player.play();
  player.currentTime = 5;
  player.dispatch("timeupdate");
  assert.equal(player.currentTime, 3);
});

test("uses the cut duration for post-run preview thumbnails", async () => {
  const node = graphNode();
  node.properties = { lfgg_editor_expanded: true };
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: () => undefined,
  });
  const videos = descendants(domWidget.element).filter(({ tagName }) => tagName === "VIDEO");
  const thumbnailPlayer = videos[1];

  node.onExecuted({
    images: [{ filename: "cut.mp4", subfolder: "", type: "temp" }],
    video_cutter: [{
      duration: 10,
      reported_fps: 30,
      nominal_frame_count: 300,
      selection_start: 2,
      selection_end: 4,
    }],
  });

  assert.match(videos[0].src, /cut\.mp4/);
  assert.equal(thumbnailPlayer.currentTime, 2 / 9);
});

test("waits for drawable media before capturing the first thumbnail", () => {
  const node = graphNode();
  node.properties = { lfgg_editor_expanded: true };
  const domWidget = installVideoCutter(node, {
    document: documentStub,
    getGraph: () => undefined,
  });
  const elements = descendants(domWidget.element);
  const thumbnailPlayer = elements.filter(({ tagName }) => tagName === "VIDEO")[1];
  const firstThumbnail = elements.find(({ tagName }) => tagName === "CANVAS");
  thumbnailPlayer.readyState = 0;

  node.onExecuted({
    images: [{ filename: "cut.mp4", subfolder: "", type: "temp" }],
    video_cutter: [{
      duration: 10,
      reported_fps: 30,
      nominal_frame_count: 300,
      selection_start: 2,
      selection_end: 4,
    }],
  });

  assert.equal(firstThumbnail.drawCount, 0);
  assert.equal(typeof thumbnailPlayer.onloadeddata, "function");
  thumbnailPlayer.readyState = 2;
  thumbnailPlayer.onloadeddata();
  assert.equal(firstThumbnail.drawCount, 1);
});

test("media disclosure preserves inputs, restores Boolean state, and defers thumbnails", async () => {
  const node = graphNode();
  node.properties = { keep: "unchanged", lfgg_editor_expanded: "false" };
  let requests = 0;
  const widget = installVideoCutter(node, {
    document: documentStub,
    getGraph: directGraph,
    fetchMetadata: async () => {
      requests += 1;
      return { duration: 10, reported_fps: 30, nominal_frame_count: 300 };
    },
  });
  await widget.lfggReady;
  const elements = descendants(widget.element);
  const toggle = elements.find(element => element.dataset.role === "editor-disclosure");
  const timeline = elements.find(element => element.dataset.role === "timeline");
  const thumbnail = elements.find(element => element.tagName === "CANVAS");
  const values = node.widgets.slice(0, 5).map(widget => widget.value);
  assert.equal(timeline.hidden, true);
  assert.equal(thumbnail.drawCount, 0);
  toggle.dispatch("click");
  assert.equal(timeline.hidden, false);
  assert.equal(node.properties.lfgg_editor_expanded, true);
  assert.equal(thumbnail.drawCount, 1);
  toggle.dispatch("click");
  assert.equal(timeline.hidden, true);
  assert.equal(node.properties.keep, "unchanged");
  assert.deepEqual(node.widgets.slice(0, 5).map(widget => widget.value), values);
  assert.equal(requests, 1);
  node.properties.lfgg_editor_expanded = true;
  node.onConfigure({});
  assert.equal(timeline.hidden, false);
  const thumbnailPlayer = elements.filter(element => element.tagName === "VIDEO")[1];
  for (let index = 1; index < 10; index += 1) thumbnailPlayer.onseeked();
  const completedDraws = elements.filter(element => element.tagName === "CANVAS").map(canvas => canvas.drawCount);
  toggle.dispatch("click");
  toggle.dispatch("click");
  assert.deepEqual(elements.filter(element => element.tagName === "CANVAS").map(canvas => canvas.drawCount), completedDraws);
  const serialized = { widgets_values: [...values] };
  node.onSerialize(serialized);
  assert.deepEqual(serialized.widgets_values, values);
});

test("button activation keys do not bubble into playback shortcuts", async () => {
  const widget = installVideoCutter(graphNode(), { document: documentStub });
  await widget.lfggReady;
  const player = descendants(widget.element).find(element => element.tagName === "VIDEO");
  for (const tagName of ["BUTTON", "SUMMARY", "INPUT", "SELECT", "TEXTAREA", "VIDEO"]) {
    widget.element.dispatch("keydown", { key: " ", target: { tagName } });
    assert.equal(player.paused, true);
  }
});

test("restores a direct video preview after all graph origins are configured", async () => {
  const node = graphNode();
  let graph;
  let requests = 0;
  const events = new EventTarget();
  const widget = installVideoCutter(node, {
    document: documentStub,
    events,
    getGraph: () => graph,
    fetchMetadata: async () => {
      requests += 1;
      return { duration: 10, reported_fps: 30, nominal_frame_count: 300 };
    },
  });
  await widget.lfggReady;
  const start = descendants(widget.element).find(element => element.dataset.boundary === "start");
  assert.equal(start.disabled, true);
  graph = directGraph();
  node.graph = graph;
  node.onAfterGraphConfigured();
  await widget.lfggReady;
  assert.equal(start.disabled, false);
  assert.deepEqual(node.widgets.slice(1, 3).map(widget => widget.value), [1, 2]);
  node.onAfterGraphConfigured();
  await widget.lfggReady;
  assert.equal(requests, 1);
  graph.load.widgets[0].value = "replacement.mp4";
  events.dispatchEvent(new Event("graphChanged"));
  await widget.lfggReady;
  const player = descendants(widget.element).find(element => element.tagName === "VIDEO");
  assert.match(player.src, /replacement\.mp4/);
  assert.equal(requests, 2);
  events.dispatchEvent(new Event("graphChanged"));
  await widget.lfggReady;
  assert.equal(requests, 2);
  node.onRemoved();
  graph.load.widgets[0].value = "removed.mp4";
  events.dispatchEvent(new Event("graphChanged"));
  assert.equal(requests, 2);
});
