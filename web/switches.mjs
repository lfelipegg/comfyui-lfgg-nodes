export const BOOLEAN_SWITCH_ID = "LFGG_BooleanSwitch";
export const BOOLEAN_SWITCH_NAME = "LFGG Boolean Switch";
export const INDEX_SWITCH_ID = "LFGG_IndexSwitch";
export const INDEX_SWITCH_NAME = "LFGG Index Switch";
export const MAX_BRANCHES = 32;

const STATE_KEY = "lfgg_switch";
const installed = Symbol("lfggSwitch");
const extended = Symbol("lfggSwitchExtension");

function branchName(kind, index) {
  return kind === "boolean" ? (index ? "true" : "false") : `branch_${index}`;
}

function branchLabel(kind, index) {
  return kind === "boolean" ? (index ? "true" : "false") : String(index);
}

function branchIndex(kind, name) {
  if (kind === "boolean") return ["false", "true"].indexOf(name);
  const match = typeof name === "string" && /^branch_(\d+)$/.exec(name);
  return match ? Number(match[1]) : -1;
}

function concreteType(type) {
  return typeof type === "string" && type && type !== "*" ? type : null;
}

function linkById(graph, id) {
  return graph?.links?.[id] ?? graph?._links?.get?.(id);
}

function dirty(node) {
  node.setDirtyCanvas?.(true, true);
  node.graph?.setDirtyCanvas?.(true, true);
}

function normalizeSavedSlots(data, kind, name) {
  data?.inputs?.forEach((slot) => {
    const index = branchIndex(kind, slot.name);
    if (Number.isInteger(index) && index >= 0 && index < (kind === "boolean" ? 2 : MAX_BRANCHES)) {
      slot.name = branchName(kind, index);
      slot.label = branchLabel(kind, index);
    }
  });
  if (data?.title === (kind === "boolean" ? BOOLEAN_SWITCH_ID : INDEX_SWITCH_ID)) {
    data.title = name;
  }
}

function kindFor(nodeData) {
  if (nodeData?.name === BOOLEAN_SWITCH_ID) return "boolean";
  if (nodeData?.name === INDEX_SWITCH_ID) return "index";
  return null;
}

export function installSwitch(node, kind, { LiteGraph } = {}) {
  if (node[installed]) return node[installed];
  if (!LiteGraph) throw new Error("LFGG switches require LiteGraph");

  const name = kind === "boolean" ? BOOLEAN_SWITCH_NAME : INDEX_SWITCH_NAME;
  const maximum = kind === "boolean" ? 2 : MAX_BRANCHES;
  const controls = { node };
  const slots = () => (node.inputs ?? []).filter((slot) => {
    const index = branchIndex(kind, slot.name);
    return index >= 0 && index < maximum;
  });
  const state = () => node.properties[STATE_KEY];
  const linked = (slot) => slot?.link != null;

  controls.normalize = () => {
    node.properties ??= {};
    const saved = node.properties[STATE_KEY] ?? {};
    const count = kind === "boolean"
      ? 2
      : Math.min(MAX_BRANCHES, Math.max(2, Number.isInteger(saved.count) ? saved.count : 2));
    node.properties[STATE_KEY] = { count, type: concreteType(saved.type) ?? "*" };
    while (slots().length > count) {
      const index = node.inputs.indexOf(slots().at(-1));
      node.removeInput?.(index);
    }
    while (slots().length < count) {
      const index = slots().length;
      node.addInput(branchName(kind, index), "*", { label: branchLabel(kind, index) });
    }
    for (const [index, slot] of slots().entries()) {
      slot.name = branchName(kind, index);
      slot.label = branchLabel(kind, index);
    }
    if (node.outputs?.[0]) node.outputs[0].name = "value";
    if (!node.title || node.title === (kind === "boolean" ? BOOLEAN_SWITCH_ID : INDEX_SWITCH_ID)) {
      node.title = name;
    }
    controls.applyType(state().type);
    return state();
  };

  controls.types = () => {
    const types = [];
    for (const slot of slots()) {
      const link = linkById(node.graph, slot.link);
      const source = link && node.graph?.getNodeById?.(link.origin_id);
      const type = concreteType(source?.outputs?.[link?.origin_slot]?.type) ?? concreteType(link?.type);
      if (type) types.push(type);
    }
    for (const id of node.outputs?.[0]?.links ?? []) {
      const link = linkById(node.graph, id);
      const target = link && node.graph?.getNodeById?.(link.target_id);
      const type = concreteType(target?.inputs?.[link?.target_slot]?.type) ?? concreteType(link?.type);
      if (type) types.push(type);
    }
    return types;
  };

  controls.applyType = (type) => {
    state().type = type;
    for (const slot of slots()) slot.type = type;
    if (node.outputs?.[0]) node.outputs[0].type = type;
    const color = LiteGraph.LGraphCanvas?.link_type_colors?.[type];
    for (const slot of slots()) {
      const link = linkById(node.graph, slot.link);
      if (link) {
        link.type = type;
        link.color = color;
      }
    }
    for (const id of node.outputs?.[0]?.links ?? []) {
      const link = linkById(node.graph, id);
      if (link) {
        link.type = type;
        link.color = color;
      }
    }
    dirty(node);
  };

  controls.recompute = () => controls.applyType(controls.types()[0] ?? "*");

  controls.accepts = (type) => {
    const current = controls.types()[0] ?? concreteType(state().type);
    const next = concreteType(type);
    return !current || !next || LiteGraph.isValidConnection(current, next);
  };

  controls.activate = (slot) => {
    if (kind !== "index" || !linked(slot) || slot !== slots().at(-1)) return;
    if (state().count < MAX_BRANCHES) state().count += 1;
    controls.normalize();
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function (type, index, isConnected, link, slot) {
    originalConnectionsChange?.apply(this, arguments);
    const branch = slots().includes(slot) ? slot : node.inputs?.[index];
    if (isConnected && type === LiteGraph.INPUT && (link || linked(branch))) {
      controls.activate(branch);
    }
    queueMicrotask(() => controls.recompute());
  };

  const originalConnectInput = node.onConnectInput;
  node.onConnectInput = function (index, type) {
    if (originalConnectInput?.apply(this, arguments) === false) return false;
    return !slots().includes(node.inputs?.[index]) || controls.accepts(type);
  };

  const originalConnectOutput = node.onConnectOutput;
  node.onConnectOutput = function (index, type) {
    if (originalConnectOutput?.apply(this, arguments) === false) return false;
    return index !== 0 || controls.accepts(type);
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
    queueMicrotask(() => controls.recompute());
  };

  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    originalSerialize?.apply(this, arguments);
    controls.recompute();
    controls.normalize();
    serialized.properties ??= {};
    serialized.properties[STATE_KEY] = { ...state() };
  };

  node[installed] = controls;
  controls.normalize();
  return controls;
}

export function extendSwitches(nodeType, nodeData, { LiteGraph }) {
  const kind = kindFor(nodeData);
  if (!kind) return false;
  if (!LiteGraph) throw new Error("LFGG switches require LiteGraph");
  if (nodeType.prototype[extended]) return true;
  const name = kind === "boolean" ? BOOLEAN_SWITCH_NAME : INDEX_SWITCH_NAME;
  const original = nodeType.prototype.onNodeCreated;
  const originalConfigure = nodeType.prototype.configure;
  nodeType.prototype.onNodeCreated = function () {
    original?.apply(this, arguments);
    installSwitch(this, kind, { LiteGraph });
  };
  nodeType.prototype.configure = function (data) {
    normalizeSavedSlots(data, kind, name);
    return originalConfigure?.apply(this, arguments);
  };
  nodeType.prototype[extended] = true;
  return true;
}
