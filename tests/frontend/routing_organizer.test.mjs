import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_CHANNELS,
  ROUTING_ORGANIZER_ID,
  extendRoutingOrganizer,
  installRoutingOrganizer,
  mergeWidgetConfigs,
  normalizeChannelLabel,
} from "../../web/routing_organizer.mjs";

class FakeGraph {
  constructor() {
    this.links = {};
    this.nodes = new Map();
    this.nextNodeId = 1;
    this.nextLinkId = 1;
  }

  add(node) {
    node.id = this.nextNodeId++;
    node.graph = this;
    this.nodes.set(node.id, node);
    return node;
  }

  getNodeById(id) {
    return this.nodes.get(id);
  }

  beforeChange() {
    this.changes = (this.changes ?? 0) + 1;
  }

  afterChange() {
    this.changes = (this.changes ?? 0) + 1;
  }
}

class FakeNode {
  constructor(title = "Fake") {
    this.title = title;
    this.type = "Fake";
    this.id = -1;
    this.pos = [0, 0];
    this.size = [140, 60];
    this.inputs = [];
    this.outputs = [];
    this.properties = {};
    this.flags = {};
  }

  addInput(name, type, extra = {}) {
    const input = { name, type, link: null, ...extra };
    this.inputs.push(input);
    return input;
  }

  addOutput(name, type, extra = {}) {
    const output = { name, type, links: [], ...extra };
    this.outputs.push(output);
    return output;
  }

  setSize(size) {
    this.size = [...size];
  }

  setDirtyCanvas() {
    this.dirty = (this.dirty ?? 0) + 1;
  }

  connect(outputIndex, target, inputIndex, parentId) {
    const output = this.outputs[outputIndex];
    const input = target?.inputs?.[inputIndex];
    if (!this.graph || this.graph !== target?.graph || !output || !input) return null;
    if (!liteGraph.isValidConnection(output.type, input.type)) return null;
    if (target.onConnectInput?.(inputIndex, output.type, output, this, outputIndex) === false) {
      return null;
    }
    if (this.onConnectOutput?.(outputIndex, input.type, input, target, inputIndex) === false) {
      return null;
    }
    if (input.link != null) target.disconnectInput(inputIndex);
    const link = {
      id: this.graph.nextLinkId++,
      origin_id: this.id,
      origin_slot: outputIndex,
      target_id: target.id,
      target_slot: inputIndex,
      type: output.type === "*" ? input.type : output.type,
      parentId,
    };
    this.graph.links[link.id] = link;
    output.links.push(link.id);
    input.link = link.id;
    this.onConnectionsChange?.(liteGraph.OUTPUT, outputIndex, true, link, output);
    target.onConnectionsChange?.(liteGraph.INPUT, inputIndex, true, link, input);
    return link;
  }

  disconnectInput(index) {
    const input = this.inputs[index];
    const link = this.graph?.links?.[input?.link];
    if (!input || !link) return false;
    const origin = this.graph.getNodeById(link.origin_id);
    origin.outputs[link.origin_slot].links = origin.outputs[link.origin_slot].links.filter(
      (id) => id !== link.id,
    );
    input.link = null;
    delete this.graph.links[link.id];
    origin.onConnectionsChange?.(
      liteGraph.OUTPUT,
      link.origin_slot,
      false,
      link,
      origin.outputs[link.origin_slot],
    );
    this.onConnectionsChange?.(liteGraph.INPUT, index, false, link, input);
    return true;
  }

  disconnectOutput(index) {
    const output = this.outputs[index];
    for (const id of [...(output?.links ?? [])]) {
      const link = this.graph.links[id];
      this.graph.getNodeById(link.target_id).disconnectInput(link.target_slot);
    }
  }

  removeInput(index) {
    if (this.inputs[index]?.link != null) this.disconnectInput(index);
    this.inputs.splice(index, 1);
    for (const link of Object.values(this.graph?.links ?? {})) {
      if (link.target_id === this.id && link.target_slot > index) link.target_slot -= 1;
    }
  }

  removeOutput(index) {
    if (this.outputs[index]?.links?.length) this.disconnectOutput(index);
    this.outputs.splice(index, 1);
    for (const link of Object.values(this.graph?.links ?? {})) {
      if (link.origin_id === this.id && link.origin_slot > index) link.origin_slot -= 1;
    }
  }
}

const liteGraph = {
  ALWAYS: 0,
  INPUT: 1,
  OUTPUT: 2,
  NODE_SLOT_HEIGHT: 20,
  NODE_SUBTEXT_SIZE: 12,
  WIDGET_TEXT_COLOR: "#eee",
  LGraphNode: FakeNode,
  isValidConnection(left, right) {
    return !left || !right || left === "*" || right === "*" || left === right;
  },
};

function organizer(graph, app = {}) {
  const node = new FakeNode("LFGG Routing Organizer");
  node.type = ROUTING_ORGANIZER_ID;
  graph.add(node);
  return { node, controls: installRoutingOrganizer(node, { LiteGraph: liteGraph, app }) };
}

test("extends the backend definition instead of registering a frontend-only node", () => {
  class BackendNode extends FakeNode {
    constructor() {
      super("LFGG Routing Organizer");
    }
  }

  assert.equal(
    extendRoutingOrganizer(
      BackendNode,
      { name: ROUTING_ORGANIZER_ID },
      { LiteGraph: liteGraph, app: {} },
    ),
    true,
  );
  const node = new BackendNode();
  node.type = ROUTING_ORGANIZER_ID;
  node.onNodeCreated();
  assert.equal(node.isVirtualNode, true);
  assert.equal(node.inputs[0].name, "");
  assert.equal(node.outputs[0].name, "");
});

function endpoint(graph, { input, output, type = "Fake" } = {}) {
  const node = graph.add(new FakeNode());
  node.type = type;
  if (input) node.addInput(input, input);
  if (output) node.addOutput(output, output);
  return node;
}

test("normalizes labels and keeps one bounded trailing channel", () => {
  assert.equal(normalizeChannelLabel("  final image  "), "final image");
  assert.equal(normalizeChannelLabel(" "), null);
  assert.equal(normalizeChannelLabel("x".repeat(80)).length, 64);

  const graph = new FakeGraph();
  const { node, controls } = organizer(graph);
  assert.equal(node.isVirtualNode, true);
  assert.equal(node.inputs.length, 1);
  assert.equal(controls.label(0), "channel 1");

  controls.rename(0, " model ");
  assert.equal(controls.label(0), "model");
  assert.equal(node.inputs.length, 2);
  controls.rename(0, "");
  assert.equal(controls.label(0), "channel 1");

  while (controls.add());
  assert.equal(node.inputs.length, MAX_CHANNELS);
  assert.equal(controls.add(), false);

  const serialized = {};
  node.mode = 4;
  node.onConfigure({});
  node.onSerialize(serialized);
  assert.equal(node.mode, liteGraph.ALWAYS);
  assert.equal(serialized.properties.lfgg_routing_channels.length, MAX_CHANNELS);
});

test("propagates types, permits fan-out and rejects routing cycles", () => {
  const graph = new FakeGraph();
  const source = endpoint(graph, { output: "IMAGE" });
  const firstTarget = endpoint(graph, { input: "IMAGE" });
  const secondTarget = endpoint(graph, { input: "IMAGE" });
  const wrongTarget = endpoint(graph, { input: "MASK" });
  const first = organizer(graph).node;
  const second = organizer(graph).node;

  assert.ok(first.connect(0, firstTarget, 0));
  assert.equal(first.inputs[0].type, "IMAGE");
  assert.ok(source.connect(0, first, 0));
  assert.ok(first.connect(0, secondTarget, 0));
  assert.equal(first.connect(0, wrongTarget, 0), null);

  assert.ok(first.connect(0, second, 0));
  assert.equal(second.outputs[0].type, "IMAGE");
  assert.equal(second.connect(0, first, 0), null);
  assert.equal(first.inputs[0].link != null, true);
});

test("merges compatible widget constraints and rejects disjoint combos", () => {
  assert.deepEqual(
    mergeWidgetConfigs(
      ["COMBO", { options: ["a", "b", "c"] }],
      ["COMBO", { options: ["b", "c", "d"] }],
    ),
    ["COMBO", { options: ["b", "c"] }],
  );
  assert.equal(
    mergeWidgetConfigs(
      ["COMBO", { options: ["a"] }],
      ["COMBO", { options: ["b"] }],
    ),
    null,
  );
  assert.deepEqual(
    mergeWidgetConfigs(
      ["INT", { min: 0, max: 10, step: 2 }],
      ["INT", { min: 4, max: 20, step: 3 }],
    ),
    ["INT", { min: 4, max: 10, step: 6 }],
  );

  const configKey = Symbol("config");
  const graph = new FakeGraph();
  const { node } = organizer(graph);
  const first = endpoint(graph, { input: "COMBO" });
  const second = endpoint(graph, { input: "COMBO" });
  const third = endpoint(graph, { input: "COMBO" });
  first.inputs[0].widget = { [configKey]: () => ["COMBO", { options: ["a", "b"] }] };
  second.inputs[0].widget = { [configKey]: () => ["COMBO", { options: ["b", "c"] }] };
  third.inputs[0].widget = { [configKey]: () => ["COMBO", { options: ["z"] }] };

  assert.ok(node.connect(0, first, 0));
  assert.ok(node.connect(0, second, 0));
  assert.deepEqual(node.inputs[0].widget[configKey](), ["COMBO", { options: ["b"] }]);
  assert.equal(node.connect(0, third, 0), null);
});

test("removing a channel splices fan-out and refuses destructive removal", () => {
  const warnings = [];
  const app = {
    extensionManager: {
      toast: { add(value) { warnings.push(value.detail); } },
    },
  };
  const graph = new FakeGraph();
  const source = endpoint(graph, { output: "IMAGE" });
  const firstTarget = endpoint(graph, { input: "IMAGE" });
  const secondTarget = endpoint(graph, { input: "IMAGE" });
  const { node, controls } = organizer(graph, app);
  source.connect(0, node, 0);
  node.connect(0, firstTarget, 0);
  node.connect(0, secondTarget, 0);

  assert.equal(controls.remove(0), true);
  assert.equal(graph.links[firstTarget.inputs[0].link].origin_id, source.id);
  assert.equal(graph.links[secondTarget.inputs[0].link].origin_id, source.id);
  assert.equal(node.inputs.length, 1);

  const unsafeNode = graph.add(new FakeNode("Unsafe organizer"));
  unsafeNode.type = ROUTING_ORGANIZER_ID;
  const unsafeControls = installRoutingOrganizer(unsafeNode, { LiteGraph: liteGraph, app });
  unsafeNode.connect(0, firstTarget, 0);
  assert.equal(unsafeControls.remove(0), false);
  assert.match(warnings.at(-1), /Connect an input/);
});

test("exposes compact channel actions while removing execution-only menus", () => {
  const graph = new FakeGraph();
  const { node, controls } = organizer(graph);
  const prompts = [];
  const canvas = {
    graph_mouse: [10, 10],
    prompt(title, value, apply) {
      prompts.push({ title, value });
      apply("positive");
    },
  };
  const options = [
    { content: "Convert to Subgraph" },
    { content: "Mode" },
    { content: "Clone" },
  ];

  node.getExtraMenuOptions(canvas, options);
  assert.deepEqual(
    options.filter(Boolean).map(({ content }) => content),
    ["Add channel", "Rename channel", "Remove channel", "Clone"],
  );
  node.onDblClick({ clientX: 0, clientY: 0 }, [10, 10], canvas);
  assert.deepEqual(prompts, [{ title: "Channel label", value: "channel 1" }]);
  assert.equal(controls.label(0), "positive");
  assert.equal(node.changeMode(4), false);
});
