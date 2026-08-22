import assert from "node:assert/strict";
import test from "node:test";

import {
  BOOLEAN_SWITCH_ID,
  BOOLEAN_SWITCH_NAME,
  INDEX_SWITCH_ID,
  INDEX_SWITCH_NAME,
  MAX_BRANCHES,
  extendSwitches,
  installSwitch,
} from "../../web/switches.mjs";

class Graph {
  constructor() {
    this.links = {};
    this.nodes = new Map();
    this.nextId = 1;
    this.nextLink = 1;
  }

  add(node) {
    node.id = this.nextId++;
    node.graph = this;
    this.nodes.set(node.id, node);
    return node;
  }

  getNodeById(id) {
    return this.nodes.get(id);
  }
}

class Node {
  constructor(title = "Node") {
    this.title = title;
    this.inputs = [];
    this.outputs = [];
    this.properties = {};
  }

  addInput(name, type, extra = {}) {
    const input = { name, type, link: null, ...extra };
    this.inputs.push(input);
    return input;
  }

  addOutput(name, type) {
    const output = { name, type, links: [] };
    this.outputs.push(output);
    return output;
  }

  removeInput(index) {
    this.disconnectInput(index);
    this.inputs.splice(index, 1);
  }

  connect(outputIndex, target, inputIndex) {
    const output = this.outputs[outputIndex];
    const input = target.inputs[inputIndex];
    if (!output || !input || !liteGraph.isValidConnection(output.type, input.type)) return null;
    if (target.onConnectInput?.(inputIndex, output.type) === false) return null;
    const link = {
      id: this.graph.nextLink++, origin_id: this.id, origin_slot: outputIndex,
      target_id: target.id, target_slot: inputIndex, type: output.type,
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
    const link = this.graph?.links[input?.link];
    if (!link) return false;
    const origin = this.graph.getNodeById(link.origin_id);
    origin.outputs[link.origin_slot].links = origin.outputs[link.origin_slot].links.filter((id) => id !== link.id);
    input.link = null;
    delete this.graph.links[link.id];
    this.onConnectionsChange?.(liteGraph.INPUT, index, false, link, input);
    return true;
  }

  setDirtyCanvas() {}
}

const liteGraph = {
  INPUT: 1,
  OUTPUT: 2,
  isValidConnection(left, right) {
    return left === "*" || right === "*" || left === right;
  },
};

function endpoint(graph, type) {
  const node = graph.add(new Node());
  node.addOutput("value", type);
  return node;
}

function switchNode(graph, kind) {
  const node = graph.add(new Node(kind === "boolean" ? BOOLEAN_SWITCH_NAME : INDEX_SWITCH_NAME));
  node.type = kind === "boolean" ? BOOLEAN_SWITCH_ID : INDEX_SWITCH_ID;
  const count = kind === "boolean" ? 2 : MAX_BRANCHES;
  for (let index = 0; index < count; index += 1) {
    node.addInput(kind === "boolean" ? (index ? "true" : "false") : `branch_${index}`, "*");
  }
  node.addOutput("value", "*");
  return { node, controls: installSwitch(node, kind, { LiteGraph: liteGraph }) };
}

const flush = () => new Promise(queueMicrotask);

test("extends backend definitions and normalizes boolean labels and titles", () => {
  class BooleanNode extends Node {}
  assert.equal(extendSwitches(BooleanNode, { name: BOOLEAN_SWITCH_ID }, { LiteGraph: liteGraph }), true);
  const node = new BooleanNode(BOOLEAN_SWITCH_ID);
  node.type = BOOLEAN_SWITCH_ID;
  new Graph().add(node);
  node.addInput("false", "*");
  node.addInput("true", "*");
  node.addOutput("value", "*");
  node.onNodeCreated();
  node.configure({ title: BOOLEAN_SWITCH_ID, inputs: [{}, {}] });

  assert.equal(node.title, BOOLEAN_SWITCH_NAME);
  assert.deepEqual(node.inputs.map(({ name, label }) => [name, label]), [["false", "false"], ["true", "true"]]);
});

test("grows the index switch only after a real final-branch link and persists bounded state", async () => {
  const graph = new Graph();
  const { node, controls } = switchNode(graph, "index");
  assert.equal(node.inputs.length, 2);
  endpoint(graph, "IMAGE").connect(0, node, 1);
  await flush();
  assert.equal(node.inputs.length, 3);
  assert.equal(node.inputs[2].label, "2");
  node.onConnectionsChange(liteGraph.INPUT, 2, true, null, node.inputs[2]);
  assert.equal(node.inputs.length, 3);

  const serialized = {};
  node.onSerialize(serialized);
  assert.deepEqual(serialized.properties.lfgg_switch, { count: 3, type: "IMAGE" });
  assert.equal(controls.node.title, INDEX_SWITCH_NAME);
  node.disconnectInput(1);
  await flush();
  assert.equal(node.inputs.length, 3);
});

test("stops growing at 32 index branches", async () => {
  const graph = new Graph();
  const { node } = switchNode(graph, "index");
  while (node.inputs.length < MAX_BRANCHES) {
    endpoint(graph, "IMAGE").connect(0, node, node.inputs.length - 1);
    await flush();
  }
  endpoint(graph, "IMAGE").connect(0, node, MAX_BRANCHES - 1);
  await flush();

  assert.equal(node.inputs.length, MAX_BRANCHES);
});

test("shares one concrete type, rejects incompatible branches, and resets when unconstrained", async () => {
  const graph = new Graph();
  const { node } = switchNode(graph, "index");
  const image = endpoint(graph, "IMAGE");
  const mask = endpoint(graph, "MASK");
  assert.ok(image.connect(0, node, 0));
  assert.equal(mask.connect(0, node, 1), null);
  await flush();
  assert.equal(node.outputs[0].type, "IMAGE");
  node.disconnectInput(0);
  await flush();
  assert.equal(node.inputs[0].type, "*");
  assert.equal(node.outputs[0].type, "*");
});

test("restore callbacks without a link do not add phantom index branches", async () => {
  const graph = new Graph();
  const { node } = switchNode(graph, "index");
  node.properties.lfgg_switch = { count: 2, type: "IMAGE" };
  node.onConfigure({});
  node.onConnectionsChange(liteGraph.INPUT, 1, true, null, node.inputs[1]);

  assert.equal(node.inputs.length, 2);
  assert.equal(node.outputs[0].type, "IMAGE");
  node.onAfterGraphConfigured();
  await flush();
  assert.equal(node.outputs[0].type, "*");
});

test("restore callbacks with a saved slot link retain the required trailing branch", () => {
  const graph = new Graph();
  const { node } = switchNode(graph, "index");
  node.inputs[1].link = 99;
  node.onConnectionsChange(liteGraph.INPUT, 1, true, null, node.inputs[1]);

  assert.equal(node.inputs.length, 3);
});

test("restores branch count and type until real links are available", async () => {
  const graph = new Graph();
  const { node } = switchNode(graph, "index");
  node.properties.lfgg_switch = { count: 3, type: "IMAGE" };
  node.onConfigure({});

  assert.equal(node.inputs.length, 3);
  assert.deepEqual(node.inputs.map(({ name, label, type }) => [name, label, type]), [
    ["branch_0", "0", "IMAGE"],
    ["branch_1", "1", "IMAGE"],
    ["branch_2", "2", "IMAGE"],
  ]);
  endpoint(graph, "IMAGE").connect(0, node, 1);
  node.onAfterGraphConfigured();
  await flush();

  const serialized = {};
  node.onSerialize(serialized);
  assert.deepEqual(serialized.properties.lfgg_switch, { count: 3, type: "IMAGE" });
});

test("does not apply branch typing to a converted selector input", async () => {
  const graph = new Graph();
  const node = graph.add(new Node(BOOLEAN_SWITCH_NAME));
  node.type = BOOLEAN_SWITCH_ID;
  node.addInput("condition", "BOOLEAN");
  node.addInput("false", "*");
  node.addInput("true", "*");
  node.addOutput("value", "*");
  installSwitch(node, "boolean", { LiteGraph: liteGraph });

  assert.ok(endpoint(graph, "IMAGE").connect(0, node, 1));
  await flush();
  assert.ok(endpoint(graph, "BOOLEAN").connect(0, node, 0));
});
