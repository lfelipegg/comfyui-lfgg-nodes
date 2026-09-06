const EXPANDED = "lfgg_editor_expanded";

// This controller never reads or writes executable widgets or media sources.
export function createEditorView(node, { isConfiguring = () => false, changed }) {
  let lastFit;
  let configuring = false;
  let repaint;
  const dirty = () => {
    node.setDirtyCanvas?.(true, true);
    if (globalThis.requestAnimationFrame && repaint == null) {
      repaint = requestAnimationFrame(() => {
        repaint = undefined;
        node.setDirtyCanvas?.(true, true);
      });
    }
  };
  const view = {
    get expanded() { return node.properties?.[EXPANDED] === true; },
    fit(allowShrink = false) {
      if (node.flags?.collapsed || !node.computeSize || !node.setSize) return;
      const minimum = node.computeSize()[1];
      const current = node.size[1];
      const owned = lastFit !== undefined && Math.abs(current - lastFit) < 1;
      const shrink = allowShrink && owned && !configuring && !isConfiguring();
      const height = shrink ? minimum : Math.max(current, minimum);
      if (height !== current) {
        node.setSize([node.size[0], height]);
        dirty();
      }
      if (height === minimum && (!configuring && !isConfiguring())) lastFit = height;
      else if (!owned) lastFit = undefined;
    },
    setExpanded(value) {
      if (typeof value !== "boolean") return;
      node.properties ??= {};
      node.properties[EXPANDED] = value;
      changed(value);
      view.fit(true);
      dirty();
    },
    restore() {
      configuring = true;
      lastFit = undefined;
      try { changed(view.expanded); view.fit(false); }
      finally { configuring = false; }
    },
  };
  const configure = node.onConfigure;
  node.onConfigure = function (...args) {
    const result = configure?.apply(this, args);
    view.restore();
    return result;
  };
  const removed = node.onRemoved;
  node.onRemoved = function (...args) {
    if (repaint != null) cancelAnimationFrame(repaint);
    return removed?.apply(this, args);
  };
  return view;
}

export function omitPresentationValues(node, serialized, widgets) {
  const values = serialized.widgets_values;
  if (!Array.isArray(values)) return;
  let retained = 0;
  let positionalLength = 0;
  node.widgets.forEach((widget, index) => {
    if (widget.serialize !== false) {
      retained += 1;
      positionalLength = index + 1;
    }
  });
  // Positional serializers omit trailing skipped widgets, but leave middle holes.
  if (values.length === retained || (values.length !== positionalLength && values.length !== node.widgets.length)) return;
  const indexes = widgets.map(widget => node.widgets.indexOf(widget)).filter(index => index >= 0).sort((a, b) => b - a);
  for (const index of indexes) serialized.widgets_values.splice(index, 1);
}
