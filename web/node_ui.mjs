export const UI = Object.freeze({ inset: 12, gap: 8, tightGap: 4, controlHeight: 32, rowHeight: 40, fontSize: 13, secondarySize: 12 });

export function resolvedWidth(node, reportedWidth, preferReported = false) {
  const reported = Number(reportedWidth);
  if (preferReported && Number.isFinite(reported) && reported > 0) return reported;
  const current = Number(node?.size?.[0]);
  if (Number.isFinite(current) && current > 0) return current;
  return Number.isFinite(reported) && reported > 0 ? reported : 0;
}

export function nativePrompt(node, label, value, event, apply = () => {}, canvas = globalThis.LGraphCanvas?.active_canvas) {
  const dialog = globalThis.comfyAPI?.app?.app?.extensionManager?.dialog;
  if (dialog?.prompt) {
    return dialog.prompt({
      title: node.title ?? "LFGG",
      message: label,
      defaultValue: String(value),
    }).then(value => {
      if (value != null) apply(value);
    });
  }
  canvas?.prompt?.(label, String(value), apply, event?.eDown ?? event?.e ?? event);
}

export function setWidgetHidden(node, widget, hidden) {
  if (widget.hidden === hidden && widget.options?.hidden === hidden) return;
  widget.hidden = hidden;
  widget.options ??= {};
  widget.options.hidden = hidden;
  // Concrete widgets expose option changes to Nodes 2.0 when registered.
  widget.setNodeId?.(node.id);
}

export function canvasTheme() {
  const host = globalThis.LiteGraph ?? {};
  return {
    background: host.WIDGET_BGCOLOR ?? "#202020",
    outline: host.WIDGET_OUTLINE_COLOR ?? "#808080",
    text: host.WIDGET_TEXT_COLOR ?? "#eeeeee",
    secondary: host.WIDGET_SECONDARY_TEXT_COLOR ?? "#b0b0b0",
  };
}

function luminance(color) {
  const hex = /^#([\da-f]{3}|[\da-f]{6})$/i.exec(color.trim());
  const rgb = hex
    ? (hex[1].length === 3 ? [...hex[1]].map(c => c + c).join("") : hex[1]).match(/../g).map(c => parseInt(c, 16))
    : color.match(/[\d.]+/g)?.slice(0, 3).map(Number);
  if (!rgb || rgb.length !== 3) return 0;
  return rgb.map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
    .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
}

export function identityColor(surface) {
  const lightness = luminance(surface);
  const contrast = color => {
    const value = luminance(color);
    return (Math.max(value, lightness) + 0.05) / (Math.min(value, lightness) + 0.05);
  };
  return contrast("#70B8AE") >= contrast("#327D73") ? "#70B8AE" : "#327D73";
}

export function drawIdentity(ctx, x, y, surface = canvasTheme().background) {
  ctx.fillStyle = identityColor(surface);
  ctx.fillRect(x, y, 3, 12);
}

export function fitText(ctx, text, width) {
  if (width <= 0) return "";
  if (ctx.measureText(text).width <= width) return text;
  const letters = Array.from(text);
  let low = 0;
  let high = letters.length;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (ctx.measureText(letters.slice(0, mid).join("") + "…").width <= width) low = mid;
    else high = mid - 1;
  }
  return ctx.measureText("…").width <= width ? letters.slice(0, low).join("") + "…" : "";
}

export function initializeRoot(node, root, document, markerParent) {
  root.className = `${root.className || ""} lfgg-node-ui`.trim();
  Object.assign(root.style, {
    fontFamily: "inherit", fontSize: `${UI.fontSize}px`, color: "var(--lfgg-text, inherit)",
    boxSizing: "border-box", minWidth: "0",
  });
  if (root.style.setProperty) {
    const values = {
      inset: `${UI.inset}px`, gap: `${UI.gap}px`, tight: `${UI.tightGap}px`,
      "control-height": `${UI.controlHeight}px`,
      surface: "var(--comfy-input-bg, #202020)", text: "var(--input-text, #eeeeee)",
      secondary: "var(--descrip-text, var(--input-text, #b0b0b0))",
      border: "var(--border-color, #808080)",
    };
    for (const [name, value] of Object.entries(values)) root.style.setProperty(`--lfgg-${name}`, value);
  }
  if (document.head && !document.querySelector('link[data-lfgg-node-ui]')) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = new URL("./node_ui.css", import.meta.url).href;
    link.dataset.lfggNodeUi = "true";
    document.head.append(link);
  }
  const marker = document.createElement("span");
  if (markerParent.prepend) markerParent.prepend(marker);
  else markerParent.append(marker);
  marker.className = "lfgg-identity";
  Object.assign(marker.style, { display: "inline-block", width: "3px", height: "12px", marginRight: `${UI.gap}px`, flexShrink: "0" });
  marker.setAttribute("aria-hidden", "true");
  const update = () => {
    const style = document.defaultView?.getComputedStyle(root);
    const surface = style?.getPropertyValue("--comfy-input-bg")?.trim() || canvasTheme().background;
    marker.style.backgroundColor = identityColor(surface);
  };
  const settings = globalThis.comfyAPI?.app?.app?.ui?.settings;
  let frame;
  const scheduleUpdate = () => {
    if (frame != null) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => { frame = undefined; update(); });
  };
  settings?.addEventListener("Comfy.ColorPalette.change", scheduleUpdate);
  settings?.addEventListener("Comfy.CustomColorPalettes.change", scheduleUpdate);
  queueMicrotask(update);
  const removed = node.onRemoved;
  node.onRemoved = function (...args) {
    if (frame != null) cancelAnimationFrame(frame);
    settings?.removeEventListener("Comfy.ColorPalette.change", scheduleUpdate);
    settings?.removeEventListener("Comfy.CustomColorPalettes.change", scheduleUpdate);
    return removed?.apply(this, args);
  };
  return marker;
}
