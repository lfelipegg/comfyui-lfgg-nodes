export const STRING_JOIN_ID = "LFGG_StringJoin";
export const STRING_JOIN_NAME = "LFGG String Join";
export const MAX_TEXT_INPUTS = 32;

const STATE_KEY = "lfgg_string_join";
const installed = Symbol("lfggStringJoin");
const extended = Symbol("lfggStringJoinExtension");

function textIndex(name) {
  const match = typeof name === "string" && /^text_(\d+)$/.exec(name);
  const index = match ? Number(match[1]) : 0;
  return index > 0 && index <= MAX_TEXT_INPUTS ? index : 0;
}

function label(index) {
  return `Text ${index}`;
}

function normalizeSavedSlots(data) {
  data?.inputs?.forEach((slot) => {
    const index = textIndex(slot.name);
    if (index) {
      slot.name = `text_${index}`;
      slot.label = label(index);
    }
  });
  if (data?.title === STRING_JOIN_ID) data.title = STRING_JOIN_NAME;
}

export function installStringJoin(node, { LiteGraph } = {}) {
  if (node[installed]) return node[installed];
  if (!LiteGraph) throw new Error("LFGG String Join requires LiteGraph");
  const controls = { node };
  const slots = () => (node.inputs ?? []).filter((slot) => textIndex(slot.name));
  const state = () => node.properties[STATE_KEY];
  const linked = (slot) => slot?.link != null;

  controls.normalize = () => {
    node.properties ??= {};
    const saved = node.properties[STATE_KEY] ?? {};
    const count = Math.min(MAX_TEXT_INPUTS, Math.max(2, Number.isInteger(saved.count) ? saved.count : 2));
    node.properties[STATE_KEY] = { count };
    while (slots().length > count) node.removeInput?.(node.inputs.indexOf(slots().at(-1)));
    while (slots().length < count) {
      const index = slots().length + 1;
      node.addInput(`text_${index}`, "STRING", { label: label(index) });
    }
    for (const [offset, slot] of slots().entries()) {
      const index = offset + 1;
      slot.name = `text_${index}`;
      slot.label = label(index);
      slot.type = "STRING";
    }
    if (node.outputs?.[0]) node.outputs[0].name = "text";
    if (!node.title || node.title === STRING_JOIN_ID) node.title = STRING_JOIN_NAME;
    return state();
  };

  controls.activate = (slot) => {
    if (!linked(slot) || slot !== slots().at(-1) || state().count === MAX_TEXT_INPUTS) return;
    state().count += 1;
    controls.normalize();
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function (type, index, isConnected, link, slot) {
    originalConnectionsChange?.apply(this, arguments);
    const text = slots().includes(slot) ? slot : node.inputs?.[index];
    if (isConnected && type === LiteGraph.INPUT && (link || linked(text))) controls.activate(text);
  };

  const originalConfigure = node.onConfigure;
  node.onConfigure = function () {
    originalConfigure?.apply(this, arguments);
    controls.normalize();
  };

  const originalAfterConfigured = node.onAfterGraphConfigured;
  node.onAfterGraphConfigured = function () {
    originalAfterConfigured?.apply(this, arguments);
    controls.normalize();
  };

  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    originalSerialize?.apply(this, arguments);
    controls.normalize();
    serialized.properties ??= {};
    serialized.properties[STATE_KEY] = { ...state() };
  };

  node[installed] = controls;
  controls.normalize();
  return controls;
}

export function extendStringJoin(nodeType, nodeData, { LiteGraph }) {
  if (nodeData?.name !== STRING_JOIN_ID) return false;
  if (!LiteGraph) throw new Error("LFGG String Join requires LiteGraph");
  if (nodeType.prototype[extended]) return true;
  const original = nodeType.prototype.onNodeCreated;
  const originalConfigure = nodeType.prototype.configure;
  nodeType.prototype.onNodeCreated = function () {
    original?.apply(this, arguments);
    installStringJoin(this, { LiteGraph });
  };
  nodeType.prototype.configure = function (data) {
    normalizeSavedSlots(data);
    return originalConfigure?.apply(this, arguments);
  };
  nodeType.prototype[extended] = true;
  return true;
}
