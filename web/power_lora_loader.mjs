export const ALL_LORAS = "All LoRAs";

const NODE_ID = "LFGG_PowerLoraLoaderFolder";
const NO_LORAS = "<no LoRAs found>";
const ROW_HEIGHT = 24;
const TOGGLE_WIDTH = 24;
const STRENGTH_WIDTH = 60;
const MENU_WIDTH = 24;
const installed = Symbol("lfggPowerLoraLoader");

function normalizeName(value) {
  return String(value).replaceAll("\\", "/");
}

function loraNames(names) {
  return [...new Set(names.map(normalizeName).filter((name) => name && name !== NO_LORAS))]
    .sort();
}

export function folderChoices(names) {
  const folders = new Set();
  for (const name of loraNames(names)) {
    const parts = name.split("/");
    for (let depth = 1; depth < parts.length; depth += 1) {
      folders.add(parts.slice(0, depth).join("/"));
    }
  }
  return [ALL_LORAS, ...folders].sort((left, right) =>
    left === ALL_LORAS ? -1 : right === ALL_LORAS ? 1 : left.localeCompare(right),
  );
}

export function chooserChoices(names, folder) {
  const normalizedFolder = normalizeName(folder);
  const prefix = `${normalizedFolder}/`;
  return loraNames(names)
    .filter(
      (name) => normalizedFolder === ALL_LORAS || name.startsWith(prefix),
    )
    .map((value) => ({
      label:
        normalizedFolder === ALL_LORAS ? value : value.slice(prefix.length),
      value,
    }));
}

function optionValues(widget) {
  const values = widget?.options?.values ?? widget?.options?.options ?? [];
  return Array.isArray(values) ? values : [];
}

function composeCallback(widget, after) {
  const original = widget.callback;
  widget.callback = function (...args) {
    if (args.length) this.value = args[0];
    const result = original?.apply(this, args);
    after();
    return result;
  };
}

function resize(node) {
  const [, minimumHeight] = node.computeSize();
  node.setSize([node.size[0], Math.max(node.size[1], minimumHeight)]);
}

function clampStrength(value) {
  const number = Number(value);
  return Number.isFinite(number)
    ? Math.max(-100, Math.min(100, number))
    : undefined;
}

function colors() {
  const theme = globalThis.LiteGraph ?? {};
  return {
    background: theme.WIDGET_BGCOLOR ?? "#202020",
    outline: theme.WIDGET_OUTLINE_COLOR ?? "#808080",
    text: theme.WIDGET_TEXT_COLOR ?? "#eeeeee",
    secondary: theme.WIDGET_SECONDARY_TEXT_COLOR ?? "#b0b0b0",
  };
}

function menu(items, event, select) {
  const ContextMenu = globalThis.LiteGraph?.ContextMenu;
  if (!ContextMenu || !items.length) return;
  new ContextMenu(
    items.map((item) => ({ content: item.label, value: item.value })),
    {
      className: "dark",
      event: event?.eDown ?? event?.e ?? event,
      callback: (item) => select(item?.value ?? item?.content ?? item),
    },
  );
}

function numericPrompt(node, label, value, event, apply) {
  const canvas =
    globalThis.LGraphCanvas?.active_canvas ??
    node.graph?.list_of_graphcanvas?.[0];
  canvas?.prompt?.(
    label,
    String(value),
    apply,
    event?.eDown ?? event?.e ?? event,
  );
}

function rowValue(row) {
  return {
    on: row.on,
    lora: row.lora,
    strength_model: row.strengthModel,
    strength_clip: row.strengthClip,
  };
}

function drawRow(ctx, row, width, y, folder) {
  const theme = colors();
  const nameWidth = Math.max(
    40,
    width - TOGGLE_WIDTH - STRENGTH_WIDTH * 2 - MENU_WIDTH,
  );
  ctx.fillStyle = theme.background;
  ctx.fillRect?.(0, y, width, ROW_HEIGHT);
  ctx.strokeStyle = theme.outline;
  ctx.strokeRect?.(0, y, width, ROW_HEIGHT);
  ctx.fillStyle = row.on ? theme.text : theme.secondary;
  ctx.font = "12px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(row.on ? "●" : "○", TOGGLE_WIDTH / 2, y + ROW_HEIGHT / 2);
  ctx.textAlign = "left";
  const relative =
    folder === ALL_LORAS || !row.lora.startsWith(`${folder}/`)
      ? row.lora
      : row.lora.slice(folder.length + 1);
  ctx.fillText(relative, TOGGLE_WIDTH + 4, y + ROW_HEIGHT / 2, nameWidth - 8);
  ctx.textAlign = "center";
  const modelX = TOGGLE_WIDTH + nameWidth;
  ctx.fillText(
    row.strengthModel.toFixed(2),
    modelX + STRENGTH_WIDTH / 2,
    y + 12,
  );
  const clipX = modelX + STRENGTH_WIDTH;
  ctx.fillText(
    row.strengthClip.toFixed(2),
    clipX + STRENGTH_WIDTH / 2,
    y + 12,
  );
  ctx.fillText("⋮", width - MENU_WIDTH / 2, y + 12);
}

function plainRow(value) {
  const strengthModel = clampStrength(value?.strength_model ?? 1);
  const strengthClip = clampStrength(value?.strength_clip ?? 1);
  return {
    on: typeof value?.on === "boolean" ? value.on : true,
    lora: normalizeName(value?.lora ?? ""),
    strengthModel: strengthModel ?? 1,
    strengthClip: strengthClip ?? 1,
  };
}

export function installPowerLoraLoader(node, { restore = false } = {}) {
  if (node?.comfyClass !== NODE_ID) return undefined;
  if (node[installed]) {
    if (restore) node[installed].restore();
    node[installed].refresh();
    return node[installed];
  }

  const folder = node.widgets?.find((widget) => widget.name === "folder");
  const addWidget = node.widgets?.find(
    (widget) => widget.name === "lora_to_add",
  );
  if (!folder || !addWidget) return undefined;

  const allLoras = loraNames(optionValues(addWidget));
  const availableFolders = folderChoices(allLoras);
  const previousFolderLabel = folder.options?.getOptionLabel;
  folder.options ??= {};
  addWidget.options ??= {};
  if (!folder.value) {
    folder.value = availableFolders[1] ?? ALL_LORAS;
  }

  const rows = [];
  const rowWidgets = [];
  const controls = {
    folder,
    addWidget,
    rows,
    rowWidgets,
  };

  const dirty = () => node.setDirtyCanvas?.(true, true);
  const syncWidgetOrder = () => {
    for (const widget of rowWidgets) {
      const index = node.widgets.indexOf(widget);
      if (index >= 0) node.widgets.splice(index, 1);
    }
    const footerIndex = node.widgets.indexOf(controls.footerWidget);
    node.widgets.splice(footerIndex, 0, ...rowWidgets);
    rowWidgets.forEach((widget, index) => {
      widget.name = `lora_${index + 1}`;
    });
  };
  const changed = () => {
    syncWidgetOrder();
    resize(node);
    dirty();
  };
  const choices = () => chooserChoices(allLoras, folder.value);
  const refresh = () => {
    const missing =
      folder.value !== ALL_LORAS && !availableFolders.includes(folder.value);
    folder.options.values = missing
      ? [...availableFolders, folder.value]
      : [...availableFolders];
    folder.options.getOptionLabel = (value) =>
      missing && value === folder.value
        ? `${value} (missing)`
        : previousFolderLabel?.(value) ?? value;
    const filtered = missing ? [] : choices();
    addWidget.options.values = filtered.map(({ value }) => value);
    addWidget.options.getOptionLabel = (value) =>
      filtered.find((choice) => choice.value === value)?.label ?? value;
    if (!addWidget.options.values.includes(addWidget.value)) {
      addWidget.value = addWidget.options.values[0];
    }
    dirty();
  };

  const createRow = (value) => {
    const row = plainRow(value);
    const widget = {
      type: "lfgg_lora_row",
      name: "",
      computeSize: () => [0, ROW_HEIGHT],
      serializeValue: () => rowValue(row),
      draw: (ctx, _node, width, y) =>
        drawRow(ctx, row, width, y, folder.value),
      onPointerDown(pointer, pointerNode) {
        const event = pointer?.eDown;
        const x = event?.canvasX - pointerNode.pos[0];
        if (!Number.isFinite(x)) return false;
        const width = pointerNode.size[0];
        const menuStart = width - MENU_WIDTH;
        const clipStart = menuStart - STRENGTH_WIDTH;
        const modelStart = clipStart - STRENGTH_WIDTH;
        pointer.onClick = (upEvent) => {
          if (x < TOGGLE_WIDTH) {
            row.on = !row.on;
            dirty();
          } else if (x < modelStart) {
            menu(choices(), upEvent, (name) =>
              controls.replace(rows.indexOf(row), name),
            );
          } else if (x < clipStart) {
            numericPrompt(
              node,
              "Model strength",
              row.strengthModel,
              upEvent,
              (number) =>
                controls.setStrength(rows.indexOf(row), "model", number),
            );
          } else if (x < menuStart) {
            numericPrompt(
              node,
              "CLIP strength",
              row.strengthClip,
              upEvent,
              (number) =>
                controls.setStrength(rows.indexOf(row), "clip", number),
            );
          } else {
            const index = rows.indexOf(row);
            const items = [];
            if (index > 0) items.push({ label: "Move up", value: "up" });
            if (index < rows.length - 1) {
              items.push({ label: "Move down", value: "down" });
            }
            items.push({ label: "Remove", value: "remove" });
            menu(items, upEvent, (action) => {
              if (action === "up") controls.move(index, -1);
              if (action === "down") controls.move(index, 1);
              if (action === "remove") controls.remove(index);
            });
          }
        };
        return true;
      },
    };
    rows.push(row);
    rowWidgets.push(widget);
    node.addCustomWidget(widget);
  };

  controls.headerWidget = node.addCustomWidget({
    type: "lfgg_lora_header",
    name: "lfgg_lora_header",
    serialize: false,
    options: { serialize: false },
    computeSize: () => [0, ROW_HEIGHT],
    draw(ctx, _node, width, y) {
      ctx.fillStyle = colors().text;
      ctx.font = "12px sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      const menuStart = width - MENU_WIDTH;
      const clipStart = menuStart - STRENGTH_WIDTH;
      const modelStart = clipStart - STRENGTH_WIDTH;
      ctx.fillText("Toggle all", 8, y + ROW_HEIGHT / 2, modelStart - 16);
      ctx.textAlign = "center";
      ctx.fillText("Model", modelStart + STRENGTH_WIDTH / 2, y + 12);
      ctx.fillText("CLIP", clipStart + STRENGTH_WIDTH / 2, y + 12);
    },
    onPointerDown(pointer) {
      pointer.onClick = () => controls.toggleAll();
      return true;
    },
  });
  controls.footerWidget = node.addCustomWidget({
    type: "lfgg_lora_footer",
    name: "lfgg_lora_footer",
    serialize: false,
    options: { serialize: false },
    computeSize: () => [0, ROW_HEIGHT],
    draw(ctx, drawNode, width, y) {
      ctx.fillStyle = colors().text;
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(
        "Add LoRA",
        (width || drawNode.size[0]) / 2,
        y + ROW_HEIGHT / 2,
      );
    },
    onPointerDown(pointer) {
      pointer.onClick = () => controls.add(addWidget.value);
      return true;
    },
  });

  controls.add = (name) => {
    const normalized = normalizeName(name);
    if (!choices().some((choice) => choice.value === normalized)) return false;
    createRow({
      on: true,
      lora: normalized,
      strength_model: 1,
      strength_clip: 1,
    });
    changed();
    return true;
  };
  controls.replace = (index, name) => {
    const normalized = normalizeName(name);
    if (
      !rows[index] ||
      !choices().some((choice) => choice.value === normalized)
    ) {
      return false;
    }
    rows[index].lora = normalized;
    dirty();
    return true;
  };
  controls.setEnabled = (index, enabled) => {
    if (!rows[index] || typeof enabled !== "boolean") return false;
    rows[index].on = enabled;
    dirty();
    return true;
  };
  controls.setStrength = (index, target, value) => {
    const strength = clampStrength(value);
    if (!rows[index] || strength === undefined) return false;
    if (target === "model") rows[index].strengthModel = strength;
    else if (target === "clip") rows[index].strengthClip = strength;
    else return false;
    dirty();
    return true;
  };
  controls.remove = (index) => {
    if (!rows[index]) return false;
    rows.splice(index, 1);
    const [widget] = rowWidgets.splice(index, 1);
    node.widgets.splice(node.widgets.indexOf(widget), 1);
    changed();
    return true;
  };
  controls.move = (index, offset) => {
    const target = index + offset;
    if (!rows[index] || target < 0 || target >= rows.length) return false;
    [rows[index], rows[target]] = [rows[target], rows[index]];
    [rowWidgets[index], rowWidgets[target]] = [
      rowWidgets[target],
      rowWidgets[index],
    ];
    changed();
    return true;
  };
  controls.toggleAll = () => {
    const enabled = !rows.length || !rows.every((row) => row.on);
    for (const row of rows) row.on = enabled;
    dirty();
  };
  controls.setFolder = (value) => {
    folder.callback(normalizeName(value));
  };
  controls.refresh = refresh;
  controls.restore = () => {
    for (const widget of rowWidgets) {
      node.widgets.splice(node.widgets.indexOf(widget), 1);
    }
    rows.splice(0);
    rowWidgets.splice(0);
    const saved = node.properties?.lfgg_lora_rows;
    if (Array.isArray(saved)) {
      for (const value of saved) createRow(value);
    }
    changed();
  };

  composeCallback(folder, refresh);
  composeCallback(addWidget, dirty);
  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    const savedRows = rows.map(rowValue);
    node.properties ??= {};
    node.properties.lfgg_lora_rows = savedRows;
    serialized.properties ??= {};
    serialized.properties.lfgg_lora_rows = savedRows;
    if (Array.isArray(serialized.widgets_values)) {
      serialized.widgets_values.splice(2);
    }
    return result;
  };

  node[installed] = controls;
  refresh();
  if (restore) controls.restore();
  else changed();
  return controls;
}
