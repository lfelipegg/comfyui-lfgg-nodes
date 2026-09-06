import { UI, canvasTheme, drawIdentity, fitText, nativePrompt, resolvedWidth } from "./node_ui.mjs";

export const ALL_LORAS = "All LoRAs";

const NODE_ID = "LFGG_PowerLoraLoaderFolder";
const NO_LORAS = "<no LoRAs found>";
const TOGGLE_WIDTH = UI.controlHeight;
const STRENGTH_WIDTH = 112;
const STRENGTH_ARROW_WIDTH = UI.controlHeight;
const STRENGTH_STEP = 0.05;
const MENU_WIDTH = UI.controlHeight;
const ROW_INSET = UI.inset;
const MIN_NAME_WIDTH = 160;
const CHECK_SIZE = 14;
const SEPARATE_STRENGTHS = "Separate Model and Clip strength";
const installed = Symbol("lfggPowerLoraLoader");

function normalizeName(value) {
  return String(value).replaceAll("\\", "/");
}

function basename(value) {
  const name = normalizeName(value);
  return name.slice(name.lastIndexOf("/") + 1);
}

function dirname(value) {
  const name = normalizeName(value);
  const slash = name.lastIndexOf("/");
  return slash < 0 ? "(root)" : name.slice(0, slash);
}

function rect(x, y, width, height) {
  return { x, y, width: Math.max(0, width), height };
}

function contains(target, x, y) {
  return (
    target.width > 0 &&
    x >= target.x &&
    x < target.x + target.width &&
    y >= target.y &&
    y < target.y + target.height
  );
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
  if (minimumHeight > node.size[1]) {
    node.setSize([node.size[0], minimumHeight]);
  }
}

function clampStrength(value) {
  const number = Number(value);
  return Number.isFinite(number)
    ? Math.max(-100, Math.min(100, number))
    : undefined;
}

const colors = canvasTheme;

function menu(items, event, select) {
  const ContextMenu = globalThis.LiteGraph?.ContextMenu;
  if (!ContextMenu || !items.length) return false;
  new ContextMenu(
    items.map((item) => ({
      content: item.label,
      value: item.value,
      disabled: item.disabled === true,
    })),
    {
      event: event?.eDown ?? event?.e ?? event,
      className: "dark",
      callback: (item) => {
        if (!item?.disabled) select(item?.value ?? item?.content ?? item);
      },
    },
  );
  return true;
}

function primaryPointer(pointer) {
  const button = pointer?.eDown?.button;
  return button == null || button === 0;
}

function pointerPosition(pointer, node, canvas, originY = 0) {
  const event = pointer?.eDown;
  const widgetCanvas =
    pointer?.element && canvas?.canvas && pointer.element !== canvas.canvas;
  if (widgetCanvas) {
    return {
      x: Number(event?.offsetX),
      y: Number(event?.offsetY) - originY,
    };
  }
  return {
    x: Number(event?.canvasX) - node.pos[0],
    y: Number(event?.canvasY) - node.pos[1] - originY,
  };
}

function searchableCombo(widget, choices) {
  widget.onPointerDown = function (pointer, node, canvas) {
    if (!primaryPointer(pointer)) return false;
    const { x } = pointerPosition(pointer, node, canvas);
    const widgetCanvas =
      pointer?.element && canvas?.canvas && pointer.element !== canvas.canvas;
    const width =
      (widgetCanvas ? pointer.element.clientWidth : undefined) ||
      this.width ||
      node.size[0];
    if (!Number.isFinite(x) || x < 40 || x > width - 40) return false;
    pointer.onClick = (event) =>
      menu(choices(), event, (value) => {
        if (typeof this.setValue === "function") {
          this.setValue(value, { e: pointer.eDown, node, canvas });
        } else {
          this.callback(value);
        }
      });
    return true;
  };
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


function rowValue(row) {
  return {
    on: row.on,
    lora: row.lora,
    strength_model: row.strengthModel,
    strength_clip: row.strengthClip,
  };
}

function drawStrength(ctx, value, target, y, label, enabled, theme) {
  const top = y + target.y;
  ctx.fillStyle = theme.background;
  ctx.fillRect?.(target.x, top, target.width, target.height);
  ctx.strokeStyle = theme.outline;
  ctx.strokeRect?.(
    target.x + 0.5,
    top + 0.5,
    target.width - 1,
    target.height - 1,
  );
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = theme.secondary;
  ctx.font = `${UI.secondarySize - 2}px system-ui, sans-serif`;
  ctx.fillText(label, target.x + target.width / 2, top + 8);
  ctx.font = `${UI.fontSize}px system-ui, sans-serif`;
  ctx.fillText("◀", target.x + STRENGTH_ARROW_WIDTH / 2, top + 23);
  ctx.fillStyle = enabled ? theme.text : theme.secondary;
  ctx.fillText(value.toFixed(2), target.x + target.width / 2, top + 23);
  ctx.fillStyle = theme.secondary;
  ctx.fillText(
    "▶",
    target.x + target.width - STRENGTH_ARROW_WIDTH / 2,
    top + 23,
  );
}

function rowLayout(width, separateStrengths, hasContext = false) {
  const strengthCount = separateStrengths ? 2 : 1;
  const contentStart = ROW_INSET;
  const contentEnd = Math.max(contentStart, width - ROW_INSET);
  const contentWidth = Math.max(0, contentEnd - contentStart);
  const strengthsWidth =
    STRENGTH_WIDTH * strengthCount +
    UI.tightGap * Math.max(0, strengthCount - 1);
  const wideMinimum =
    TOGGLE_WIDTH +
    UI.tightGap +
    MIN_NAME_WIDTH +
    UI.gap +
    strengthsWidth +
    UI.gap +
    MENU_WIDTH;
  const wide = contentWidth >= wideMinimum;

  if (wide) {
    const height = hasContext ? 56 : UI.rowHeight;
    const controlY = (height - UI.controlHeight) / 2;
    const menuRect = rect(
      contentEnd - MENU_WIDTH,
      controlY,
      MENU_WIDTH,
      UI.controlHeight,
    );
    const clipX = menuRect.x - UI.gap - STRENGTH_WIDTH;
    const modelX = separateStrengths
      ? clipX - UI.tightGap - STRENGTH_WIDTH
      : clipX;
    const toggleRect = rect(
      contentStart,
      controlY,
      TOGGLE_WIDTH,
      UI.controlHeight,
    );
    const nameX = toggleRect.x + toggleRect.width + UI.tightGap;
    return {
      height,
      wide,
      contentStart,
      contentEnd,
      contentWidth,
      toggle: toggleRect,
      name: rect(nameX, 0, modelX - UI.gap - nameX, height),
      model: rect(modelX, controlY, STRENGTH_WIDTH, UI.controlHeight),
      clip: separateStrengths
        ? rect(clipX, controlY, STRENGTH_WIDTH, UI.controlHeight)
        : undefined,
      menu: menuRect,
    };
  }

  const fileY = UI.tightGap;
  const strengthY = fileY + UI.controlHeight + UI.gap;
  const verticalStrengths =
    separateStrengths && strengthsWidth > contentWidth;
  const strengthLines = verticalStrengths ? strengthCount : 1;
  const height =
    strengthY +
    strengthLines * UI.controlHeight +
    (strengthLines - 1) * UI.tightGap +
    UI.tightGap;
  const toggleRect = rect(
    contentStart,
    fileY,
    TOGGLE_WIDTH,
    UI.controlHeight,
  );
  const menuRect = rect(
    contentEnd - MENU_WIDTH,
    fileY,
    MENU_WIDTH,
    UI.controlHeight,
  );
  const modelX = contentStart + Math.max(
    0,
    (contentWidth - (verticalStrengths ? STRENGTH_WIDTH : strengthsWidth)) / 2,
  );
  const clipX = verticalStrengths
    ? modelX
    : modelX + STRENGTH_WIDTH + UI.tightGap;
  return {
    height,
    wide,
    contentStart,
    contentEnd,
    contentWidth,
    toggle: toggleRect,
    name: rect(
      toggleRect.x + toggleRect.width + UI.tightGap,
      fileY,
      menuRect.x -
        UI.tightGap -
        (toggleRect.x + toggleRect.width + UI.tightGap),
      UI.controlHeight,
    ),
    model: rect(modelX, strengthY, STRENGTH_WIDTH, UI.controlHeight),
    clip: separateStrengths
      ? rect(
          clipX,
          verticalStrengths
            ? strengthY + UI.controlHeight + UI.tightGap
            : strengthY,
          STRENGTH_WIDTH,
          UI.controlHeight,
        )
      : undefined,
    menu: menuRect,
  };
}

function drawRow(ctx, row, display, width, y, separateStrengths) {
  const theme = colors();
  const layout = rowLayout(width, separateStrengths, Boolean(display.context));
  ctx.fillStyle = theme.background;
  ctx.fillRect?.(
    layout.contentStart,
    y,
    layout.contentWidth,
    layout.height,
  );

  const checkX = layout.toggle.x + (layout.toggle.width - CHECK_SIZE) / 2;
  const checkY =
    y + layout.toggle.y + (layout.toggle.height - CHECK_SIZE) / 2;
  ctx.strokeStyle = theme.outline;
  ctx.strokeRect?.(checkX + 0.5, checkY + 0.5, CHECK_SIZE - 1, CHECK_SIZE - 1);
  ctx.font = `${UI.fontSize}px system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = theme.text;
  if (row.on) {
    ctx.fillText("✓", checkX + CHECK_SIZE / 2, checkY + CHECK_SIZE / 2);
  }

  const nameX = layout.name.x;
  const nameWidth = layout.name.width;
  ctx.textAlign = "left";
  ctx.fillStyle = row.on ? theme.text : theme.secondary;
  ctx.font = `${UI.fontSize}px system-ui, sans-serif`;
  if (display.context) {
    const primaryY = y + layout.name.y + layout.name.height / 2 - 7;
    const contextY = primaryY + 16;
    ctx.fillText(fitText(ctx, display.basename, nameWidth), nameX, primaryY);
    ctx.fillStyle = theme.secondary;
    ctx.font = `${UI.secondarySize}px system-ui, sans-serif`;
    ctx.fillText(fitText(ctx, display.context, nameWidth), nameX, contextY);
  } else {
    ctx.fillText(
      fitText(ctx, display.basename, nameWidth),
      nameX,
      y + layout.name.y + layout.name.height / 2,
    );
  }

  drawStrength(
    ctx,
    row.strengthModel,
    layout.model,
    y,
    separateStrengths ? "Model" : "Strength",
    row.on,
    theme,
  );
  if (layout.clip) {
    drawStrength(
      ctx,
      row.strengthClip,
      layout.clip,
      y,
      "CLIP",
      row.on,
      theme,
    );
  }
  ctx.fillStyle = row.on ? theme.text : theme.secondary;
  ctx.font = `${UI.fontSize}px system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.fillText(
    "⋮",
    layout.menu.x + layout.menu.width / 2,
    y + layout.menu.y + layout.menu.height / 2,
  );
  ctx.fillStyle = theme.outline;
  ctx.fillRect?.(
    layout.contentStart,
    y + layout.height - 1,
    layout.contentWidth,
    1,
  );
  return layout;
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

  const catalogByBasename = new Map();
  for (const name of allLoras) {
    const key = basename(name);
    if (!catalogByBasename.has(key)) catalogByBasename.set(key, new Set());
    catalogByBasename.get(key).add(name);
  }
  const rows = [];
  const rowWidgets = [];
  const displayByRow = new Map();
  const controls = {
    folder,
    addWidget,
    rows,
    rowWidgets,
  };
  Object.defineProperty(controls, "separateStrengths", {
    get: () => node.properties[SEPARATE_STRENGTHS] === true,
  });

  const rebuildDisplayIndex = () => {
    const selectedByBasename = new Map();
    for (const row of rows) {
      const key = basename(row.lora);
      if (!selectedByBasename.has(key)) {
        selectedByBasename.set(key, new Set());
      }
      selectedByBasename.get(key).add(row.lora);
    }
    displayByRow.clear();
    const activeFolder = normalizeName(folder.value);
    const prefix = `${activeFolder}/`;
    for (const row of rows) {
      const key = basename(row.lora);
      const duplicate =
        (catalogByBasename.get(key)?.size ?? 0) > 1 ||
        (selectedByBasename.get(key)?.size ?? 0) > 1;
      const outside =
        activeFolder !== ALL_LORAS && !row.lora.startsWith(prefix);
      displayByRow.set(row, {
        basename: key,
        context: duplicate || outside ? dirname(row.lora) : "",
      });
    }
  };
  const displayFor = (row) =>
    displayByRow.get(row) ?? { basename: basename(row.lora), context: "" };
  const dirty = () => {
    node.setDirtyCanvas?.(true, true);
    controls.headerWidget?.triggerDraw?.();
    for (const widget of rowWidgets) widget.triggerDraw?.();
    controls.footerWidget?.triggerDraw?.();
  };
  // Canvas adapters bind by slot name; move row data, not widget identities.
  const syncWidgetOrder = () => {
    for (const widget of rowWidgets) {
      const index = node.widgets.indexOf(widget);
      if (index >= 0) node.widgets.splice(index, 1);
    }
    const footerIndex = node.widgets.indexOf(controls.footerWidget);
    node.widgets.splice(footerIndex, 0, ...rowWidgets);
    rowWidgets.forEach((widget, index) => {
      widget.lfggRow = rows[index];
    });
  };
  const changed = () => {
    rebuildDisplayIndex();
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
    rebuildDisplayIndex();
    resize(node);
    dirty();
  };

  const showFullPath = (row, event) => {
    nativePrompt(node, "Full LoRA path", row.lora, event);
  };
  const openReplacement = (row, event) =>
    menu(choices(), event, (name) =>
      controls.replace(rows.indexOf(row), name),
    );

  const createRow = (value) => {
    const row = plainRow(value);
    let widget;
    const definition = {
      type: "lfgg_lora_row",
      name: `lora_${rowWidgets.length + 1}`,
      lfggRow: row,
      options: {},
      computeSize: (reportedWidth) => [
        0,
        rowLayout(
          resolvedWidth(
            node,
            reportedWidth,
            (widget ?? definition).bridgeWidth,
          ),
          controls.separateStrengths,
          Boolean(displayFor((widget ?? definition).lfggRow).context),
        ).height,
      ],
      serializeValue: () => rowValue((widget ?? definition).lfggRow),
      draw(ctx, drawNode, reportedWidth, y) {
        const concrete = widget ?? definition;
        const row = concrete.lfggRow;
        concrete.bridgeWidth = concrete.y === 0 && y === 1;
        concrete.last_y = y;
        concrete.width = resolvedWidth(drawNode, reportedWidth, concrete.bridgeWidth);
        concrete.layout = drawRow(
          ctx,
          row,
          displayFor(row),
          concrete.width,
          y,
          controls.separateStrengths,
        );
      },
      onPointerDown(pointer, pointerNode, canvas) {
        if (!primaryPointer(pointer)) return false;
        const row = (widget ?? definition).lfggRow;
        const { x, y } = pointerPosition(
          pointer,
          pointerNode,
          canvas,
          (widget ?? definition).last_y,
        );
        if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
        const layout = (widget ?? definition).layout;
        if (!layout) return false;
        const target = [
          ["toggle", layout.toggle],
          ["name", layout.name],
          ["model", layout.model],
          ["clip", layout.clip],
          ["menu", layout.menu],
        ].find(([, targetRect]) => targetRect && contains(targetRect, x, y))?.[0];
        if (
          !target ||
          (!row.on && ["name", "model", "clip"].includes(target))
        ) {
          return false;
        }

        pointer.onClick = (upEvent) => {
          const index = rows.indexOf(row);
          if (index < 0) return;
          const adjustStrength = (strengthTarget, value, targetRect) => {
            const offset = x - targetRect.x;
            const direction =
              offset < STRENGTH_ARROW_WIDTH
                ? -1
                : offset >= targetRect.width - STRENGTH_ARROW_WIDTH
                  ? 1
                  : 0;
            if (direction) {
              controls.setStrength(
                index,
                strengthTarget,
                Math.round((value + direction * STRENGTH_STEP) * 100) / 100,
              );
            } else {
              nativePrompt(
                node,
                controls.separateStrengths
                  ? `${strengthTarget === "model" ? "Model" : "CLIP"} strength`
                  : "Strength",
                value,
                upEvent,
                (number) =>
                  controls.setStrength(index, strengthTarget, number),
              );
            }
          };
          if (target === "toggle") {
            controls.setEnabled(index, !row.on);
          } else if (target === "name") {
            openReplacement(row, upEvent);
          } else if (target === "model") {
            adjustStrength("model", row.strengthModel, layout.model);
          } else if (target === "clip") {
            adjustStrength("clip", row.strengthClip, layout.clip);
          } else {
            const items = [
              { label: "Show full path", value: "path" },
              { label: "Move up", value: "up", disabled: index === 0 },
              {
                label: "Move down",
                value: "down",
                disabled: index === rows.length - 1,
              },
              { label: "Remove", value: "remove" },
            ];
            menu(items, upEvent, (action) => {
              if (action === "path") showFullPath(row, upEvent);
              if (action === "up") controls.move(index, -1);
              if (action === "down") controls.move(index, 1);
              if (action === "remove") controls.remove(index);
            });
          }
        };
        return true;
      },
    };
    widget = node.addCustomWidget(definition) ?? definition;
    rows.push(row);
    rowWidgets.push(widget);
  };

  let headerWidget;
  const headerDefinition = {
    type: "lfgg_lora_header",
    name: "lfgg_lora_header",
    serialize: false,
    options: { serialize: false },
    computeSize: () => [0, UI.controlHeight],
    draw(ctx, drawNode, reportedWidth, y) {
      const concrete = headerWidget ?? headerDefinition;
      concrete.bridgeWidth = concrete.y === 0 && y === 1;
      concrete.last_y = y;
      concrete.layoutWidth = resolvedWidth(
        drawNode,
        reportedWidth,
        concrete.bridgeWidth,
      );
      concrete.width = concrete.layoutWidth;
      const theme = colors();
      drawIdentity(ctx, ROW_INSET, y + 10, theme.background);
      ctx.fillStyle = theme.text;
      ctx.font = `600 ${UI.fontSize}px system-ui, sans-serif`;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(
        "Toggle all",
        ROW_INSET + 3 + UI.gap,
        y + UI.controlHeight / 2,
      );
      ctx.fillStyle = theme.outline;
      ctx.fillRect?.(
        ROW_INSET,
        y + UI.controlHeight - 1,
        Math.max(0, concrete.layoutWidth - ROW_INSET * 2),
        1,
      );
    },
    onPointerDown(pointer, pointerNode, canvas) {
      if (!primaryPointer(pointer)) return false;
      const concrete = headerWidget ?? headerDefinition;
      const { x, y } = pointerPosition(
        pointer,
        pointerNode,
        canvas,
        concrete.last_y,
      );
      const target = rect(
        ROW_INSET,
        0,
        concrete.layoutWidth - ROW_INSET * 2,
        UI.controlHeight,
      );
      if (!Number.isFinite(x) || !Number.isFinite(y) || !contains(target, x, y)) {
        return false;
      }
      pointer.onClick = () => controls.toggleAll();
      return true;
    },
  };
  headerWidget = node.addCustomWidget(headerDefinition) ?? headerDefinition;
  controls.headerWidget = headerWidget;

  let footerWidget;
  const footerDefinition = {
    type: "lfgg_lora_footer",
    name: "lfgg_lora_footer",
    serialize: false,
    options: { serialize: false },
    computeSize: () => [0, UI.controlHeight],
    draw(ctx, drawNode, reportedWidth, y) {
      const concrete = footerWidget ?? footerDefinition;
      concrete.bridgeWidth = concrete.y === 0 && y === 1;
      concrete.last_y = y;
      concrete.layoutWidth = resolvedWidth(
        drawNode,
        reportedWidth,
        concrete.bridgeWidth,
      );
      concrete.width = concrete.layoutWidth;
      ctx.fillStyle = colors().text;
      ctx.font = `${UI.fontSize}px system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(
        "Add LoRA",
        concrete.layoutWidth / 2,
        y + UI.controlHeight / 2,
      );
    },
    onPointerDown(pointer, pointerNode, canvas) {
      if (!primaryPointer(pointer)) return false;
      const concrete = footerWidget ?? footerDefinition;
      const { x, y } = pointerPosition(
        pointer,
        pointerNode,
        canvas,
        concrete.last_y,
      );
      const target = rect(
        ROW_INSET,
        0,
        concrete.layoutWidth - ROW_INSET * 2,
        UI.controlHeight,
      );
      if (!Number.isFinite(x) || !Number.isFinite(y) || !contains(target, x, y)) {
        return false;
      }
      pointer.onClick = () => controls.add(addWidget.value);
      return true;
    },
  };
  footerWidget = node.addCustomWidget(footerDefinition) ?? footerDefinition;
  controls.footerWidget = footerWidget;

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
    changed();
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
    const widget = rowWidgets.pop();
    node.widgets.splice(node.widgets.indexOf(widget), 1);
    changed();
    return true;
  };
  controls.move = (index, offset) => {
    const target = index + offset;
    if (!rows[index] || target < 0 || target >= rows.length) return false;
    [rows[index], rows[target]] = [rows[target], rows[index]];
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
  searchableCombo(folder, () =>
    folder.options.values.map((value) => ({
      label: folder.options.getOptionLabel(value),
      value,
    })),
  );
  searchableCombo(addWidget, choices);
  const originalMenu = node.getExtraMenuOptions;
  node.getExtraMenuOptions = function (canvas, options) {
    const result = originalMenu?.apply(this, arguments);
    const items = [
      {
        content: "Add selected LoRA",
        disabled: !choices().some(({ value }) => value === addWidget.value),
        callback: () => controls.add(addWidget.value),
      },
      {
        content: "Toggle all LoRAs",
        disabled: rows.length === 0,
        callback: controls.toggleAll,
      },
    ];
    for (const [index, row] of rows.entries()) {
      const display = displayFor(row);
      const suffix = display.context
        ? `${display.basename} — ${display.context}`
        : display.basename;
      items.push(
        null,
        { content: `LoRA ${index + 1}: ${suffix}`, disabled: true },
        {
          content: `Show LoRA ${index + 1} full path`,
          callback: (_item, _options, event) => showFullPath(row, event),
        },
        {
          content: `Replace LoRA ${index + 1}`,
          disabled: !row.on || choices().length === 0,
          callback: (_item, _options, event) =>
            openReplacement(row, event),
        },
        {
          content: `${row.on ? "Disable" : "Enable"} LoRA ${index + 1}`,
          callback: () => controls.setEnabled(index, !row.on),
        },
      );
      if (controls.separateStrengths) {
        items.push(
          {
            content: `Set LoRA ${index + 1} Model strength`,
            disabled: !row.on,
            callback: (_item, _options, event) =>
              nativePrompt(
                node,
                "Model strength",
                row.strengthModel,
                event,
                (value) => controls.setStrength(index, "model", value),
              ),
          },
          {
            content: `Set LoRA ${index + 1} CLIP strength`,
            disabled: !row.on,
            callback: (_item, _options, event) =>
              nativePrompt(
                node,
                "CLIP strength",
                row.strengthClip,
                event,
                (value) => controls.setStrength(index, "clip", value),
              ),
          },
        );
      } else {
        items.push({
          content: `Set LoRA ${index + 1} strength`,
          disabled: !row.on,
          callback: (_item, _options, event) =>
            nativePrompt(
              node,
              "Strength",
              row.strengthModel,
              event,
              (value) => controls.setStrength(index, "model", value),
            ),
        });
      }
      items.push(
        {
          content: `Move LoRA ${index + 1} up`,
          disabled: index === 0,
          callback: () => controls.move(index, -1),
        },
        {
          content: `Move LoRA ${index + 1} down`,
          disabled: index === rows.length - 1,
          callback: () => controls.move(index, 1),
        },
        {
          content: `Remove LoRA ${index + 1}`,
          callback: () => controls.remove(index),
        },
      );
    }
    options.unshift(...items, null);
    return result;
  };
  const originalPropertyChanged = node.onPropertyChanged;
  node.onPropertyChanged = function (name, value) {
    const result = originalPropertyChanged?.apply(this, arguments);
    if (result === false) return false;
    if (name === SEPARATE_STRENGTHS) {
      node.properties[SEPARATE_STRENGTHS] = Boolean(value);
      if (!value) {
        for (const row of rows) row.strengthClip = row.strengthModel;
      }
      resize(node);
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
