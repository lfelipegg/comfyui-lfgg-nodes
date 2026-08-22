export const ROUTING_ORGANIZER_ID = "LFGG_RoutingOrganizer";
export const ROUTING_ORGANIZER_NAME = "LFGG Routing Organizer";
export const MAX_CHANNELS = 32;

const STATE_KEY = "lfgg_routing_channels";
const LABEL_LIMIT = 64;
const installed = Symbol("lfggRoutingOrganizer");
const extended = Symbol("lfggRoutingOrganizerExtension");
const ignoredWidgetOptions = new Set([
  "control_after_generate",
  "default",
  "defaultInput",
  "dynamicPrompts",
  "forceInput",
  "multiline",
  "placeholder",
  "tooltip",
]);

export function normalizeChannelLabel(value) {
  if (typeof value !== "string") return null;
  const label = value.trim();
  return label ? label.slice(0, LABEL_LIMIT) : null;
}

function linkById(graph, id) {
  return graph?.links?.[id] ?? graph?._links?.get?.(id);
}

function routePoint(node, slot) {
  if (node?.type === ROUTING_ORGANIZER_ID && node.inputs?.[slot]) {
    return { node, slot };
  }
  if (node?.type === "Reroute" && slot === 0) return { node, slot: 0 };
  return null;
}

function pointKey(point) {
  return `${point.node.id}:${point.slot}`;
}

function reachesRoute(start, target) {
  const graph = start.node.graph;
  if (!graph) return false;
  const wanted = pointKey(target);
  const seen = new Set();
  const pending = [start];
  while (pending.length) {
    const point = pending.pop();
    const key = pointKey(point);
    if (key === wanted) return true;
    if (seen.has(key)) continue;
    seen.add(key);
    for (const id of point.node.outputs?.[point.slot]?.links ?? []) {
      const link = linkById(graph, id);
      const targetNode = link && graph.getNodeById?.(link.target_id);
      const next = targetNode && routePoint(targetNode, link.target_slot);
      if (next) pending.push(next);
    }
  }
  return false;
}

function componentFrom(start) {
  const graph = start.node.graph;
  if (!graph) return { points: [start], source: null, targets: [], links: [] };

  let root = start;
  let source = null;
  const upstream = new Set();
  while (true) {
    const key = pointKey(root);
    if (upstream.has(key)) break;
    upstream.add(key);
    const inputLink = linkById(graph, root.node.inputs?.[root.slot]?.link);
    if (!inputLink) break;
    const origin = graph.getNodeById?.(inputLink.origin_id);
    const previous = origin && routePoint(origin, inputLink.origin_slot);
    if (!previous) {
      source = origin
        ? { node: origin, slot: inputLink.origin_slot, link: inputLink }
        : null;
      break;
    }
    root = previous;
  }

  const points = [];
  const targets = [];
  const links = [];
  const seen = new Set();
  const pending = [root];
  while (pending.length) {
    const point = pending.pop();
    const key = pointKey(point);
    if (seen.has(key)) continue;
    seen.add(key);
    points.push(point);
    for (const id of point.node.outputs?.[point.slot]?.links ?? []) {
      const link = linkById(graph, id);
      if (!link) continue;
      links.push(link);
      const targetNode = graph.getNodeById?.(link.target_id);
      const next = targetNode && routePoint(targetNode, link.target_slot);
      if (next) pending.push(next);
      else if (targetNode) {
        targets.push({ node: targetNode, slot: link.target_slot, link });
      }
    }
    const inputLink = linkById(graph, point.node.inputs?.[point.slot]?.link);
    if (inputLink) links.push(inputLink);
  }
  return { points, source, targets, links };
}

function concreteType(value) {
  return value && value !== "*" ? value : null;
}

function widgetConfig(slot) {
  const widget = slot?.widget;
  if (!widget) return null;
  for (const key of Object.getOwnPropertySymbols(widget)) {
    const candidate = widget[key];
    if (Array.isArray(candidate) && candidate.length >= 1) {
      return { config: candidate, key, getter: false, widget };
    }
  }
  for (const key of Object.getOwnPropertySymbols(widget)) {
    const candidate = widget[key];
    if (typeof candidate !== "function") continue;
    try {
      const config = candidate.call(widget);
      if (Array.isArray(config) && config.length >= 1) {
        return { config, key, getter: true, widget };
      }
    } catch {
      // A widget can expose unrelated functions that require arguments.
    }
  }
  return null;
}

function configType(config) {
  return Array.isArray(config?.[0]) ? "COMBO" : config?.[0];
}

function comboOptions(config) {
  return Array.isArray(config?.[0])
    ? config[0]
    : config?.[1]?.options ?? [];
}

function sameOption(left, right) {
  return Object.is(left, right);
}

function decimalPlaces(value) {
  const text = String(value);
  return text.includes("e-")
    ? Number(text.split("e-")[1])
    : (text.split(".")[1]?.length ?? 0);
}

function greatestCommonDivisor(left, right) {
  while (right) [left, right] = [right, left % right];
  return left;
}

function combinedStep(left = 1, right = 1) {
  const places = Math.min(8, Math.max(decimalPlaces(left), decimalPlaces(right)));
  const scale = 10 ** places;
  const a = Math.round(left * scale);
  const b = Math.round(right * scale);
  return (Math.abs(a * b) / greatestCommonDivisor(a, b)) / scale;
}

function mergeCommonConfig(type, left, right) {
  const leftOptions = left ?? {};
  const rightOptions = right ?? {};
  for (const key of new Set([
    ...Object.keys(leftOptions),
    ...Object.keys(rightOptions),
  ])) {
    if (ignoredWidgetOptions.has(key)) continue;
    const a = leftOptions[key];
    const b = rightOptions[key];
    if (!Object.is(a, b) && !(a == null && b == null)) return null;
  }
  return [type, { ...leftOptions, ...rightOptions }];
}

export function mergeWidgetConfigs(left, right) {
  const type = configType(left);
  if (!type || type !== configType(right)) return null;
  const leftOptions = left?.[1] ?? {};
  const rightOptions = right?.[1] ?? {};
  if (type === "COMBO") {
    const options = comboOptions(left).filter((value) =>
      comboOptions(right).some((other) => sameOption(value, other)),
    );
    if (!options.length) return null;
    return mergeCommonConfig(
      type,
      { ...leftOptions, options },
      { ...rightOptions, options },
    );
  }
  if (type === "INT" || type === "FLOAT") {
    const min = Math.max(leftOptions.min ?? -Infinity, rightOptions.min ?? -Infinity);
    const max = Math.min(leftOptions.max ?? Infinity, rightOptions.max ?? Infinity);
    if (min > max) return null;
    const shared = {
      min,
      max,
      step: combinedStep(leftOptions.step, rightOptions.step),
    };
    return mergeCommonConfig(
      type,
      { ...leftOptions, ...shared },
      { ...rightOptions, ...shared },
    );
  }
  return mergeCommonConfig(type, leftOptions, rightOptions);
}

function componentWidget(component, extraSlot) {
  const entries = [];
  const sourceOutput = component.source?.node.outputs?.[component.source.slot];
  for (const slot of [sourceOutput, ...component.targets.map(({ node, slot }) =>
    node.inputs?.[slot]), extraSlot]) {
    const entry = widgetConfig(slot);
    if (entry) entries.push(entry);
  }
  if (!entries.length) return { entry: null, config: null };
  let config = entries[0].config;
  for (const entry of entries.slice(1)) {
    config = mergeWidgetConfigs(config, entry.config);
    if (!config) return null;
  }
  return { entry: entries[0], config };
}

function copyWidget(slot, resolved) {
  if (!resolved?.entry) {
    delete slot.widget;
    return;
  }
  const { entry, config } = resolved;
  const widget = { ...entry.widget, name: slot.name || "value" };
  widget[entry.key] = entry.getter ? () => config : config;
  slot.widget = widget;
}

function notify(app, message) {
  const toast = app?.extensionManager?.toast;
  if (toast?.add) {
    toast.add({ severity: "warn", summary: ROUTING_ORGANIZER_NAME, detail: message });
  } else {
    console.warn(`[LFGG] ${message}`);
  }
}

function dirty(node) {
  node.setDirtyCanvas?.(true, true);
  node.graph?.setDirtyCanvas?.(true, true);
}

function channelSlotName(index) {
  return `channel_${index + 1}`;
}

function normalizeSavedSlots(data) {
  for (const slots of [data?.inputs, data?.outputs]) {
    slots?.forEach((slot, index) => {
      slot.name = channelSlotName(index);
      slot.label = " ";
    });
  }
  if (data?.title === ROUTING_ORGANIZER_ID) data.title = ROUTING_ORGANIZER_NAME;
}

export function installRoutingOrganizer(node, { LiteGraph, app } = {}) {
  if (node[installed]) return node[installed];
  if (!LiteGraph) throw new Error("LFGG Routing Organizer requires LiteGraph");

  node.properties ??= {};
  node.flags ??= {};
  node.flags.keepAllLinksOnBypass = false;
  node.isVirtualNode = true;
  node.mode = LiteGraph.ALWAYS ?? 0;

  const controls = { node };
  const pending = new Set();
  let automaticSize = null;
  let manuallySized = false;

  const state = () => node.properties[STATE_KEY];
  const connected = (index, verifyLinks = false) => {
    const ids = [
      node.inputs?.[index]?.link,
      ...(node.outputs?.[index]?.links ?? []),
    ].filter((id) => id != null);
    return verifyLinks
      ? ids.some((id) => Boolean(linkById(node.graph, id)))
      : ids.length > 0;
  };

  const addSlot = (entry = { label: null, used: false }) => {
    const index = node.inputs?.length ?? 0;
    node.addInput(channelSlotName(index), "*", { label: " " });
    node.addOutput(channelSlotName(index), "*", { label: " " });
    state().push(entry);
  };

  controls.normalize = (verifyLinks = true) => {
    if (!node.title || node.title === ROUTING_ORGANIZER_ID) {
      node.title = ROUTING_ORGANIZER_NAME;
    }
    node.properties ??= {};
    const saved = Array.isArray(node.properties[STATE_KEY])
      ? node.properties[STATE_KEY]
      : [];
    const count = Math.min(
      MAX_CHANNELS,
      Math.max(1, saved.length, node.inputs?.length ?? 0, node.outputs?.length ?? 0),
    );
    node.properties[STATE_KEY] = Array.from({ length: count }, (_, index) => {
      const raw = saved[index];
      const label = normalizeChannelLabel(raw?.label);
      return {
        label,
        used: Boolean(
          raw?.used || label || connected(index, verifyLinks) || index < count - 1,
        ),
      };
    });
    while ((node.inputs?.length ?? 0) < count) node.addInput("", "*");
    while ((node.outputs?.length ?? 0) < count) node.addOutput("", "*");
    while (node.inputs.length > count) node.removeInput(node.inputs.length - 1);
    while (node.outputs.length > count) node.removeOutput(node.outputs.length - 1);
    for (let index = state().length - 1; index > 0; index -= 1) {
      const input = node.inputs[index];
      if (
        connected(index, verifyLinks) ||
        state()[index].label ||
        pending.has(input)
      ) {
        continue;
      }
      pending.delete(input);
      node.removeOutput(index);
      node.removeInput(index);
      state().splice(index, 1);
    }
    for (let index = 0; index < state().length; index += 1) {
      for (const slot of [node.inputs[index], node.outputs[index]]) {
        slot.name = channelSlotName(index);
        slot.label = " ";
      }
    }
    controls.resize();
    return state();
  };

  controls.label = (index) => state()?.[index]?.label ?? `channel ${index + 1}`;

  controls.resize = () => {
    const slotHeight = LiteGraph.NODE_SLOT_HEIGHT ?? 20;
    const longest = state()?.reduce(
      (length, _entry, index) => Math.max(length, controls.label(index).length),
      ROUTING_ORGANIZER_NAME.length,
    ) ?? ROUTING_ORGANIZER_NAME.length;
    const minimum = [
      Math.min(520, Math.max(220, 42 + longest * 7)),
      state().length * slotHeight + 6,
    ];
    if (
      automaticSize &&
      (node.size?.[0] !== automaticSize[0] || node.size?.[1] !== automaticSize[1])
    ) {
      manuallySized = true;
    }
    const size = manuallySized
      ? [
          Math.max(node.size?.[0] ?? 0, minimum[0]),
          Math.max(node.size?.[1] ?? 0, minimum[1]),
        ]
      : minimum;
    automaticSize = manuallySized ? null : [...size];
    node.setSize?.(size);
  };

  controls.activate = (index) => {
    const entry = state()?.[index];
    if (!entry) return false;
    entry.used = true;
    pending.delete(node.inputs?.[index]);
    controls.resize();
    return true;
  };

  controls.add = () => {
    if (state().length >= MAX_CHANNELS) return false;
    addSlot();
    pending.add(node.inputs.at(-1));
    controls.resize();
    dirty(node);
    return true;
  };

  controls.rename = (index, value) => {
    const entry = state()?.[index];
    if (!entry) return false;
    entry.label = normalizeChannelLabel(value);
    if (entry.label) controls.activate(index);
    controls.resize();
    dirty(node);
    return true;
  };

  controls.componentAccepts = (index, slot) => {
    const component = componentFrom({ node, slot: index });
    const resolved = componentWidget(component, slot);
    if (resolved === null) return false;
    const currentType =
      concreteType(component.source?.node.outputs?.[component.source.slot]?.type) ??
      component.targets
        .map(({ node: target, slot: targetSlot }) =>
          concreteType(target.inputs?.[targetSlot]?.type))
        .find(Boolean);
    const nextType = concreteType(slot?.type);
    return !currentType || !nextType || LiteGraph.isValidConnection(currentType, nextType);
  };

  controls.recompute = (index) => {
    if (!node.graph || !state()?.[index]) return;
    const component = componentFrom({ node, slot: index });
    const resolvedWidget = componentWidget(component);
    const sourceType = concreteType(
      component.source?.node.outputs?.[component.source.slot]?.type,
    );
    const targetType = component.targets
      .map(({ node: target, slot: targetSlot }) =>
        concreteType(target.inputs?.[targetSlot]?.type))
      .find(Boolean);
    const type = sourceType ?? targetType ?? "*";
    for (const point of component.points) {
      const input = point.node.inputs?.[point.slot];
      const output = point.node.outputs?.[point.slot];
      if (!output) continue;
      output.type = type;
      point.node.__outputType = type;
      if (point.node.type === ROUTING_ORGANIZER_ID && input) {
        input.type = type;
        copyWidget(input, resolvedWidget);
        copyWidget(output, resolvedWidget);
      }
    }
    const color = LiteGraph.LGraphCanvas?.link_type_colors?.[type];
    for (const link of component.links) {
      link.type = type;
      link.color = color;
    }
    dirty(node);
  };

  controls.remove = (index) => {
    if (!state()?.[index] || state().length === 1) return false;
    pending.delete(node.inputs[index]);
    const graph = node.graph;
    const inputLink = graph && linkById(graph, node.inputs[index].link);
    const outputLinks = graph
      ? (node.outputs[index].links ?? []).map((id) => linkById(graph, id)).filter(Boolean)
      : [];
    if (!inputLink && outputLinks.length) {
      notify(app, "Connect an input or disconnect this channel's outputs before removing it.");
      return false;
    }

    graph?.beforeChange?.(node);
    const restored = [];
    if (inputLink) {
      const source = graph.getNodeById?.(inputLink.origin_id);
      for (const outputLink of outputLinks) {
        const target = graph.getNodeById?.(outputLink.target_id);
        const direct = source?.connect?.(
          inputLink.origin_slot,
          target,
          outputLink.target_slot,
          inputLink.parentId,
        );
        if (!direct) {
          for (const previous of restored) {
            node.connect?.(index, previous.target, previous.slot);
          }
          graph?.afterChange?.(node);
          notify(app, "The channel was kept because one or more links could not be reconnected.");
          return false;
        }
        restored.push({ target, slot: outputLink.target_slot });
      }
    }
    node.removeOutput(index);
    node.removeInput(index);
    state().splice(index, 1);
    controls.normalize();
    graph?.afterChange?.(node);
    dirty(node);
    return true;
  };

  const rowAt = (position) => {
    const slotHeight = LiteGraph.NODE_SLOT_HEIGHT ?? 20;
    const index = Math.floor(position?.[1] / slotHeight);
    return index >= 0 && index < state().length ? index : -1;
  };

  const promptRename = (index, canvas, event) => {
    canvas?.prompt?.("Channel label", controls.label(index), (value) => {
      node.graph?.beforeChange?.(node);
      controls.rename(index, value);
      node.graph?.afterChange?.(node);
    }, event);
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function (type, index, isConnected, link, slot) {
    originalConnectionsChange?.apply(this, arguments);
    if (!state()?.[index]) return;
    if (isConnected && (link || connected(index))) controls.activate(index);
    const update = () => {
      if (!isConnected) controls.normalize();
      controls.recompute(index);
    };
    if (isConnected) update();
    else queueMicrotask(update);
  };

  const originalConnectInput = node.onConnectInput;
  node.onConnectInput = function (index, type, output, origin, originSlot) {
    if (originalConnectInput?.apply(this, arguments) === false) return false;
    const previous = routePoint(origin, originSlot);
    if (previous && reachesRoute({ node, slot: index }, previous)) return false;
    return controls.componentAccepts(index, output);
  };

  const originalConnectOutput = node.onConnectOutput;
  node.onConnectOutput = function (index, type, input, target, targetSlot) {
    if (originalConnectOutput?.apply(this, arguments) === false) return false;
    const next = routePoint(target, targetSlot);
    if (next && reachesRoute(next, { node, slot: index })) return false;
    return controls.componentAccepts(index, input);
  };

  const originalConfigure = node.onConfigure;
  node.onConfigure = function () {
    pending.clear();
    originalConfigure?.apply(this, arguments);
    node.mode = LiteGraph.ALWAYS ?? 0;
    controls.normalize(false);
  };

  const originalAfterConfigured = node.onAfterGraphConfigured;
  node.onAfterGraphConfigured = function () {
    originalAfterConfigured?.apply(this, arguments);
    controls.normalize();
    queueMicrotask(() => {
      for (let index = 0; index < state().length; index += 1) {
        controls.recompute(index);
      }
    });
  };

  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    originalSerialize?.apply(this, arguments);
    controls.normalize();
    serialized.properties ??= {};
    serialized.properties[STATE_KEY] = state().map(({ label, used }) => ({ label, used }));
  };

  const originalDraw = node.onDrawForeground;
  node.onDrawForeground = function (ctx) {
    originalDraw?.apply(this, arguments);
    const slotHeight = LiteGraph.NODE_SLOT_HEIGHT ?? 20;
    ctx.save?.();
    ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR ?? "#dddddd";
    ctx.font = `${LiteGraph.NODE_SUBTEXT_SIZE ?? 12}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (let index = 0; index < state().length; index += 1) {
      ctx.fillText(controls.label(index), node.size[0] / 2, (index + 0.7) * slotHeight);
    }
    ctx.restore?.();
  };

  const originalDoubleClick = node.onDblClick;
  node.onDblClick = function (event, position, canvas) {
    originalDoubleClick?.apply(this, arguments);
    const index = rowAt(position);
    if (index >= 0) promptRename(index, canvas, event);
  };

  const originalMenu = node.getExtraMenuOptions;
  node.getExtraMenuOptions = function (canvas, options) {
    originalMenu?.apply(this, arguments);
    for (const blocked of ["Convert to Subgraph", "Mode"]) {
      const index = options.findIndex((option) => option?.content === blocked);
      if (index >= 0) options.splice(index, 1);
    }
    const mouse = canvas?.graph_mouse ?? [node.pos[0], node.pos[1] - 1];
    const channel = rowAt([mouse[0] - node.pos[0], mouse[1] - node.pos[1]]);
    const items = [{ content: "Add channel", disabled: state().length >= MAX_CHANNELS, callback: controls.add }];
    if (channel >= 0) {
      items.push(
        { content: "Rename channel", callback: (_item, _options, event) => promptRename(channel, canvas, event) },
        { content: "Remove channel", disabled: state().length === 1, callback: () => controls.remove(channel) },
      );
    }
    options.unshift(...items, null);
    return [];
  };

  node.changeMode = () => false;
  node[installed] = controls;
  controls.normalize();
  return controls;
}

export function extendRoutingOrganizer(nodeType, nodeData, { LiteGraph, app }) {
  if (nodeData?.name !== ROUTING_ORGANIZER_ID) return false;
  if (!LiteGraph) throw new Error("LFGG Routing Organizer requires LiteGraph");
  if (nodeType.prototype[extended]) return true;

  const original = nodeType.prototype.onNodeCreated;
  const originalConfigure = nodeType.prototype.configure;
  nodeType.prototype.onNodeCreated = function () {
    original?.apply(this, arguments);
    installRoutingOrganizer(this, { LiteGraph, app });
  };
  nodeType.prototype.configure = function (data) {
    normalizeSavedSlots(data);
    return originalConfigure?.apply(this, arguments);
  };
  nodeType.prototype[extended] = true;
  nodeType.collapsable = false;
  return true;
}
