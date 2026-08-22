import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_TEXT_INPUTS,
  STRING_JOIN_ID,
  STRING_JOIN_NAME,
  extendStringJoin,
  installStringJoin,
} from "../../web/string_join.mjs";

class Graph {
  constructor() {
    this.links = {};
    this.nextLink = 1;
  }

  add(node) {
    node.graph = this;
    return node;
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
    this.inputs.splice(index, 1);
  }

  connect(outputIndex, target, inputIndex) {
    const output = this.outputs[outputIndex];
    const input = target.inputs[inputIndex];
    if (!output || !input) return null;
    const link = { id: this.graph.nextLink++ };
    this.graph.links[link.id] = link;
    input.link = link.id;
    target.onConnectionsChange?.(liteGraph.INPUT, inputIndex, true, link, input);
    return link;
  }
}

const liteGraph = { INPUT: 1 };

function endpoint(graph) {
  const node = graph.add(new Node());
  node.addOutput("text", "STRING");
  return node;
}

function stringJoinNode(graph) {
  const node = graph.add(new Node(STRING_JOIN_NAME));
  node.type = STRING_JOIN_ID;
  node.addInput("separator", "STRING");
  for (let index = 1; index <= MAX_TEXT_INPUTS; index += 1) node.addInput(`text_${index}`, "STRING");
  node.addOutput("text", "STRING");
  return { node, controls: installStringJoin(node, { LiteGraph: liteGraph }) };
}

test("extends backend definitions and normalizes text labels and titles", () => {
  class StringJoinNode extends Node {}
  assert.equal(extendStringJoin(StringJoinNode, { name: STRING_JOIN_ID }, { LiteGraph: liteGraph }), true);
  const node = new StringJoinNode(STRING_JOIN_ID);
  new Graph().add(node);
  node.addInput("separator", "STRING");
  node.addInput("text_1", "STRING");
  node.addInput("text_2", "STRING");
  node.addOutput("text", "STRING");
  node.onNodeCreated();
  node.configure({ title: STRING_JOIN_ID, inputs: [{}, { name: "text_1" }, { name: "text_2" }] });

  assert.equal(node.title, STRING_JOIN_NAME);
  assert.deepEqual(node.inputs.map(({ name, label }) => [name, label]), [
    ["separator", undefined], ["text_1", "Text 1"], ["text_2", "Text 2"],
  ]);
});

test("grows only after a real final link and saves its count", () => {
  const graph = new Graph();
  const { node } = stringJoinNode(graph);
  assert.equal(node.inputs.length, 3);
  endpoint(graph).connect(0, node, 2);
  assert.equal(node.inputs.length, 4);
  node.onConnectionsChange(liteGraph.INPUT, 3, true, null, node.inputs[3]);
  assert.equal(node.inputs.length, 4);
  const serialized = {};
  node.onSerialize(serialized);
  assert.deepEqual(serialized.properties.lfgg_string_join, { count: 3 });
});

test("does not shrink, stops at 32, and restores saved slots without phantoms", () => {
  const graph = new Graph();
  const { node } = stringJoinNode(graph);
  while (node.inputs.length - 1 < MAX_TEXT_INPUTS) endpoint(graph).connect(0, node, node.inputs.length - 1);
  assert.equal(node.inputs.length - 1, MAX_TEXT_INPUTS);
  node.inputs.at(-1).link = null;
  node.onConnectionsChange(liteGraph.INPUT, node.inputs.length - 1, false, null, node.inputs.at(-1));
  assert.equal(node.inputs.length - 1, MAX_TEXT_INPUTS);

  const restored = stringJoinNode(new Graph()).node;
  restored.properties.lfgg_string_join = { count: 3 };
  restored.onConfigure({});
  assert.equal(restored.inputs.length, 4);
  restored.onConnectionsChange(liteGraph.INPUT, 3, true, null, restored.inputs[3]);
  assert.equal(restored.inputs.length, 4);

  restored.inputs[3].link = 99;
  restored.onConnectionsChange(liteGraph.INPUT, 3, true, null, restored.inputs[3]);
  assert.equal(restored.inputs.length, 5);
  restored.onConnectionsChange(liteGraph.INPUT, 3, true, null, restored.inputs[3]);
  assert.equal(restored.inputs.length, 5);
  restored.inputs[3].link = null;
  restored.onConnectionsChange(liteGraph.INPUT, 3, false, null, restored.inputs[3]);
  const serialized = {};
  restored.onSerialize(serialized);
  assert.deepEqual(serialized.properties.lfgg_string_join, { count: 4 });
});
