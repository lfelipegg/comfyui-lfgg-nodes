export const ALL_LORAS = "All LoRAs";

const NODE_ID = "LFGG_PowerLoraLoaderFolder";
const NO_LORAS = "<no LoRAs found>";
const ROW_HEIGHT = 24;
const TOGGLE_WIDTH = 24;
const STRENGTH_WIDTH = 84;
const STRENGTH_ARROW_WIDTH = 18;
const STRENGTH_STEP = 0.05;
const MENU_WIDTH = 24;
const ROW_INSET = 10;
const ENABLED_COLOR = "#66bb6a";
const DISABLED_COLOR = "#ef5350";
const DISABLED_OVERLAY = "rgba(0, 0, 0, 0.35)";
const SEPARATE_STRENGTHS = "Separate Model and Clip strength";
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
      callback: (item) => {
        select(item?.value ?? item?.content ?? item);
      },
    },
  );
}

function primaryPointer(pointer) {
  const button = pointer?.eDown?.button;
  return button == null || button === 0;
}

function migrateStrengthSetting(node) {
  node.properties ??= {};
  const separate =
    node.properties[SEPARATE_STRENGTHS] ??
    (node.properties.lfgg_link_strengths === false);
  node.properties[SEPARATE_STRENGTHS] = Boolean(separate);
  delete node.properties.lfgg_link_strengths;
  return Boolean(separate);
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

function drawStrength(ctx, value, x, y, enabled, theme) {
  ctx.fillStyle = theme.secondary;
  ctx.fillText("◀", x + STRENGTH_ARROW_WIDTH / 2, y + ROW_HEIGHT / 2);
  ctx.fillStyle = enabled ? theme.text : theme.secondary;
  ctx.fillText(value.toFixed(2), x + STRENGTH_WIDTH / 2, y + ROW_HEIGHT / 2);
  ctx.fillStyle = theme.secondary;
  ctx.fillText(
    "▶",
    x + STRENGTH_WIDTH - STRENGTH_ARROW_WIDTH / 2,
    y + ROW_HEIGHT / 2,
  );
}

function rowLayout(width, separateStrengths) {
  const strengthCount = separateStrengths ? 2 : 1;
  const contentWidth = Math.max(0, width - ROW_INSET * 2);
  const nameWidth = Math.max(
    40,
    contentWidth -
      TOGGLE_WIDTH -
      STRENGTH_WIDTH * strengthCount -
      MENU_WIDTH,
  );
  const toggleStart = ROW_INSET;
  const modelStart = toggleStart + TOGGLE_WIDTH + nameWidth;
  const clipStart = modelStart + STRENGTH_WIDTH;
  return {
    contentStart: ROW_INSET,
    contentEnd: width - ROW_INSET,
    contentWidth,
    nameWidth,
    toggleStart,
    modelStart,
    clipStart,
    menuStart: clipStart + (separateStrengths ? STRENGTH_WIDTH : 0),
  };
}

function drawRow(ctx, row, width, y, folder, separateStrengths) {
  const theme = colors();
  const layout = rowLayout(width, separateStrengths);
  ctx.fillStyle = theme.background;
  ctx.fillRect?.(ROW_INSET, y, layout.contentWidth, ROW_HEIGHT);
  if (!row.on) {
    ctx.fillStyle = DISABLED_OVERLAY;
    ctx.fillRect?.(ROW_INSET, y, layout.contentWidth, ROW_HEIGHT);
  }
  ctx.strokeStyle = theme.outline;
  ctx.strokeRect?.(ROW_INSET, y, layout.contentWidth, ROW_HEIGHT);
  ctx.fillStyle = row.on ? ENABLED_COLOR : DISABLED_COLOR;
  ctx.font = "12px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(
    "●",
    layout.toggleStart + TOGGLE_WIDTH / 2,
    y + ROW_HEIGHT / 2,
  );
  ctx.fillStyle = row.on ? theme.text : theme.secondary;
  ctx.textAlign = "left";
  const relative =
    folder === ALL_LORAS || !row.lora.startsWith(`${folder}/`)
      ? row.lora
      : row.lora.slice(folder.length + 1);
  ctx.fillText(
    relative,
    layout.toggleStart + TOGGLE_WIDTH + 4,
    y + ROW_HEIGHT / 2,
    layout.nameWidth - 8,
  );
  ctx.textAlign = "center";
  drawStrength(ctx, row.strengthModel, layout.modelStart, y, row.on, theme);
  if (separateStrengths) {
    drawStrength(ctx, row.strengthClip, layout.clipStart, y, row.on, theme);
  }
  ctx.fillStyle = row.on ? theme.text : theme.secondary;
  ctx.fillText("⋮", layout.menuStart + MENU_WIDTH / 2, y + 12);
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

  const separateStrengths = migrateStrengthSetting(node);
  node.constructor[`@${SEPARATE_STRENGTHS}`] ??= { type: "boolean" };
  node.properties[SEPARATE_STRENGTHS] = Boolean(separateStrengths);
  delete node.properties.lfgg_link_strengths;

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
  Object.defineProperty(controls, "separateStrengths", {
    get: () => node.properties[SEPARATE_STRENGTHS] === true,
  });

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
      draw: (ctx, drawNode, _width, y) =>
        drawRow(
          ctx,
          row,
          drawNode.size[0],
          y,
          folder.value,
          controls.separateStrengths,
        ),
      onPointerDown(pointer, pointerNode) {
        if (!primaryPointer(pointer)) return false;
        const event = pointer?.eDown;
        const x = event?.canvasX - pointerNode.pos[0];
        if (!Number.isFinite(x)) return false;
        const width = pointerNode.size[0];
        const layout = rowLayout(width, controls.separateStrengths);
        if (x < layout.contentStart || x >= layout.contentEnd) return false;
        pointer.onClick = (upEvent) => {
          const adjustStrength = (target, value, start) => {
            const offset = x - start;
            const direction =
              offset < STRENGTH_ARROW_WIDTH
                ? -1
                : offset >= STRENGTH_WIDTH - STRENGTH_ARROW_WIDTH
                  ? 1
                  : 0;
            if (direction) {
              controls.setStrength(
                rows.indexOf(row),
                target,
                Math.round((value + direction * STRENGTH_STEP) * 100) / 100,
              );
            } else {
              numericPrompt(
                node,
                controls.separateStrengths
                  ? `${target === "model" ? "Model" : "CLIP"} strength`
                  : "Strength",
                value,
                upEvent,
                (number) =>
                  controls.setStrength(rows.indexOf(row), target, number),
              );
            }
          };
          if (x < layout.toggleStart + TOGGLE_WIDTH) {
            row.on = !row.on;
            dirty();
          } else if (x < layout.modelStart) {
            menu(choices(), upEvent, (name) =>
              controls.replace(rows.indexOf(row), name),
            );
          } else if (x < layout.clipStart) {
            adjustStrength("model", row.strengthModel, layout.modelStart);
          } else if (x < layout.menuStart) {
            adjustStrength("clip", row.strengthClip, layout.clipStart);
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
    draw(ctx, drawNode, _width, y) {
      ctx.fillStyle = colors().text;
      ctx.font = "12px sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      const layout = rowLayout(drawNode.size[0], controls.separateStrengths);
      ctx.fillText(
        "Toggle all",
        ROW_INSET + 8,
        y + ROW_HEIGHT / 2,
        layout.modelStart - 16,
      );
      ctx.textAlign = "center";
      ctx.font = "10px sans-serif";
      ctx.fillText(
        controls.separateStrengths ? "Model strength" : "Strength",
        layout.modelStart + STRENGTH_WIDTH / 2,
        y + 12,
      );
      if (controls.separateStrengths) {
        ctx.fillText(
          "CLIP strength",
          layout.clipStart + STRENGTH_WIDTH / 2,
          y + 12,
        );
      }
    },
    onPointerDown(pointer) {
      if (!primaryPointer(pointer)) return false;
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
    draw(ctx, drawNode, _width, y) {
      ctx.fillStyle = colors().text;
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(
        "Add LoRA",
        drawNode.size[0] / 2,
        y + ROW_HEIGHT / 2,
      );
    },
    onPointerDown(pointer) {
      if (!primaryPointer(pointer)) return false;
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
    if (target !== "model" && target !== "clip") return false;
    if (!controls.separateStrengths) {
      rows[index].strengthModel = strength;
      rows[index].strengthClip = strength;
    } else if (target === "model") rows[index].strengthModel = strength;
    else rows[index].strengthClip = strength;
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
    migrateStrengthSetting(node);
    for (const widget of rowWidgets) {
      node.widgets.splice(node.widgets.indexOf(widget), 1);
    }
    rows.splice(0);
    rowWidgets.splice(0);
    const saved = node.properties?.lfgg_lora_rows;
    if (Array.isArray(saved)) {
      for (const value of saved) createRow(value);
    }
    if (!controls.separateStrengths) {
      for (const row of rows) row.strengthClip = row.strengthModel;
    }
    changed();
  };

  composeCallback(folder, refresh);
  composeCallback(addWidget, dirty);
  const originalPropertyChanged = node.onPropertyChanged;
  node.onPropertyChanged = function (name, value) {
    const result = originalPropertyChanged?.apply(this, arguments);
    if (result === false) return false;
    if (name === SEPARATE_STRENGTHS) {
      node.properties[SEPARATE_STRENGTHS] = Boolean(value);
      if (!value) {
        for (const row of rows) row.strengthClip = row.strengthModel;
      }
      dirty();
    }
    return result;
  };
  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    const savedRows = rows.map(rowValue);
    node.properties.lfgg_lora_rows = savedRows;
    serialized.properties ??= {};
    serialized.properties.lfgg_lora_rows = savedRows;
    serialized.properties[SEPARATE_STRENGTHS] =
      controls.separateStrengths;
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
