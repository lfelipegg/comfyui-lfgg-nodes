import { UI, initializeRoot } from "./node_ui.mjs";

const NODE_ID = "LFGG_PromptComposer";
const installed = Symbol("lfggPromptComposer");
const catalogs = new WeakMap();

function loadCatalog(fetchLibraries, refresh) {
  let catalog = catalogs.get(fetchLibraries);
  if (!catalog) {
    catalog = { value: undefined, request: undefined };
    catalogs.set(fetchLibraries, catalog);
  }
  if (catalog.request) return catalog.request;
  if (!refresh && catalog.value) return Promise.resolve(catalog.value);
  catalog.request = (async () => {
    const result = await fetchLibraries();
    if (!result || result.ok !== true ||
        !Array.isArray(result.wildcards) || !Array.isArray(result.styles)) {
      throw new Error(result?.error || "The prompt library response is invalid");
    }
    for (const entries of [result.wildcards, result.styles]) {
      for (const entry of entries) {
        if (!entry || typeof entry.name !== "string" || !entry.name ||
            typeof entry.disabled !== "boolean") {
          throw new Error("The prompt library response is invalid");
        }
      }
    }
    catalog.value = result;
    return result;
  })().finally(() => { catalog.request = undefined; });
  return catalog.request;
}

function option(document, name, disabled = false) {
  const item = document.createElement("option");
  item.value = name;
  item.textContent = name;
  item.disabled = disabled;
  return item;
}

function buildOptions(placeholder, entries, document) {
  const choices = [option(document, "", true)];
  choices[0].textContent = placeholder;
  for (const entry of entries) {
    choices.push(option(document, entry.name, entry.disabled));
  }
  return choices;
}

function replaceOptions(select, choices) {
  select.replaceChildren(...choices);
  select.value = "";
  select.disabled = !choices.some((choice) => !choice.disabled);
}

function unavailable(select, placeholder, document) {
  const item = option(document, "", true);
  item.textContent = placeholder;
  select.replaceChildren(item);
  select.disabled = true;
}

function menu(choices, event, select) {
  const ContextMenu = globalThis.LiteGraph?.ContextMenu;
  if (!ContextMenu || choices.length < 2) return false;
  const items = choices.slice(1).map((choice) => ({
    content: choice.textContent,
    value: choice.value,
    disabled: choice.disabled,
  }));
  new ContextMenu(items, {
    event,
    className: "dark",
    callback: (item) => {
      if (!item?.disabled) select(item?.value ?? item?.content ?? item);
    },
  });
  return true;
}

function wildcardPicker(document, select, insert) {
  const panel = document.createElement("div");
  panel.dataset.role = "wildcard-picker";
  panel.setAttribute("role", "group");
  panel.setAttribute("aria-label", "Select wildcards");
  Object.assign(panel.style, { display: "none", minWidth: "0", gap: `${UI.gap}px` });
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = "Search wildcards…";
  search.setAttribute("aria-label", "Search wildcards");
  const list = document.createElement("div");
  Object.assign(list.style, { maxHeight: "240px", overflowY: "auto", minWidth: "0" });
  const empty = document.createElement("span");
  empty.textContent = "No matching wildcards";
  empty.setAttribute("role", "status");
  const actions = document.createElement("div");
  Object.assign(actions.style, { display: "flex", flexWrap: "wrap", gap: `${UI.gap}px` });
  const commit = document.createElement("button");
  commit.type = "button";
  commit.dataset.role = "insert-wildcards";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = "Cancel";
  for (const control of [search, commit, cancel]) {
    control.style.minHeight = `${UI.controlHeight}px`;
    control.style.minWidth = "0";
  }
  actions.append(commit, cancel);
  panel.append(search, list, empty, actions);
  let rows = [];
  const selected = new Set();
  const update = () => {
    commit.disabled = selected.size === 0;
    commit.textContent = `Insert selected (${selected.size})`;
  };
  const close = (focus = true) => {
    panel.style.display = "none";
    select.setAttribute("aria-expanded", "false");
    selected.clear();
    rows = [];
    list.replaceChildren();
    if (focus) select.focus();
  };
  cancel.addEventListener("click", () => close());
  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  });
  search.addEventListener("input", () => {
    const query = search.value.toLowerCase();
    let matches = 0;
    for (const { label, name } of rows) {
      const visible = name.toLowerCase().includes(query);
      label.style.display = visible ? "flex" : "none";
      if (visible) matches++;
    }
    empty.style.display = matches ? "none" : "block";
  });
  commit.addEventListener("click", () => {
    if (!selected.size) return;
    const tokens = [...selected].map((name) => `__${name}__`);
    insert(tokens.length === 1 ? tokens[0] : `{${tokens.join("|")}}`);
    close(false);
  });
  select.setAttribute("aria-expanded", "false");
  return {
    panel,
    close,
    open(choices) {
      close(false);
      search.value = "";
      for (const choice of choices.slice(1)) {
        const label = document.createElement("label");
        Object.assign(label.style, {
          display: "flex", alignItems: "center", gap: `${UI.gap}px`,
          minHeight: `${UI.controlHeight}px`, overflowWrap: "anywhere",
        });
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = choice.value;
        checkbox.disabled = choice.disabled;
        checkbox.addEventListener("change", () => {
          if (checkbox.disabled) return;
          if (checkbox.checked) selected.add(choice.value);
          else selected.delete(choice.value);
          update();
        });
        const caption = document.createElement("span");
        caption.textContent = choice.textContent;
        label.append(checkbox, caption);
        list.append(label);
        rows.push({ label, name: choice.value });
      }
      update();
      empty.style.display = rows.length ? "none" : "block";
      panel.style.display = "grid";
      select.setAttribute("aria-expanded", "true");
      search.focus();
    },
  };
}

function insertToken(node, input, token) {
  const widget = node.widgets?.find(({ name }) => name === "prompt_template");
  if (!widget) return;
  const current = String(input?.value ?? widget.value ?? "");
  const start = Number.isInteger(input?.selectionStart)
    ? input.selectionStart
    : current.length;
  const end = Number.isInteger(input?.selectionEnd)
    ? input.selectionEnd
    : start;
  const value = `${current.slice(0, start)}${token}${current.slice(end)}`;
  widget.value = value;
  if (input) {
    input.value = value;
    const caret = start + token.length;
    input.setSelectionRange?.(caret, caret);
    input.focus?.();
  }
  widget.callback?.(value);
  node.setDirtyCanvas?.(true, true);
}

function labeledSelect(document, text, role) {
  const label = document.createElement("label");
  const caption = document.createElement("span");
  const select = document.createElement("select");
  caption.textContent = text;
  select.dataset.role = role;
  select.setAttribute("aria-label", text);
  select.title = `${text} at the prompt caret; replaces selected text.`;
  select.setAttribute("aria-description", select.title);
  Object.assign(label.style, {
    display: "grid",
    gap: `${UI.tightGap}px`,
    minWidth: "0",
    flex: "1 1 140px",
  });
  Object.assign(caption.style, {
    display: "flex",
    alignItems: "center",
    minWidth: "0",
    fontSize: `${UI.secondarySize}px`,
    lineHeight: "1.3",
  });
  Object.assign(select.style, {
    width: "100%",
    minWidth: "0",
    maxWidth: "100%",
    minHeight: `${UI.controlHeight}px`,
  });
  label.append(caption, select);
  return { label, select };
}

export function installPromptComposer(
  node,
  { document = globalThis.document, fetchLibraries } = {},
) {
  if (
    node.comfyClass !== NODE_ID ||
    node[installed] ||
    !document ||
    typeof fetchLibraries !== "function"
  ) {
    return node[installed];
  }

  const promptWidget = node.widgets?.find(
    ({ name }) => name === "prompt_template",
  );
  if (!promptWidget) return;
  const input = promptWidget.inputEl;
  const root = document.createElement("div");
  const selectors = document.createElement("div");
  const actions = document.createElement("div");
  const wildcard = labeledSelect(document, "Insert wildcard", "wildcards");
  const style = labeledSelect(document, "Insert style", "styles");
  const refresh = document.createElement("button");
  const status = document.createElement("span");
  Object.assign(root.style, {
    display: "grid",
    gap: `${UI.gap}px`,
    width: "100%",
    minWidth: "0",
    height: "auto",
    alignContent: "start",
    padding: `${UI.inset}px`,
    boxSizing: "border-box",
  });
  selectors.dataset.role = "selectors";
  Object.assign(selectors.style, {
    display: "flex",
    flexWrap: "wrap",
    gap: `${UI.gap}px`,
    minWidth: "0",
  });
  actions.dataset.role = "actions";
  Object.assign(actions.style, {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: `${UI.tightGap}px ${UI.gap}px`,
    minWidth: "0",
  });
  refresh.type = "button";
  refresh.textContent = "Refresh libraries";
  refresh.dataset.role = "refresh";
  Object.assign(refresh.style, {
    minHeight: `${UI.controlHeight}px`,
    padding: `0 ${UI.gap}px`,
    flexShrink: "0",
  });
  status.dataset.role = "status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  Object.assign(status.style, {
    display: "block",
    minWidth: "0",
    flex: "1 1 120px",
    color: "var(--lfgg-secondary)",
    fontSize: `${UI.secondarySize}px`,
    whiteSpace: "normal",
    overflowWrap: "anywhere",
  });
  selectors.append(wildcard.label, style.label);
  actions.append(refresh, status);
  const picker = wildcardPicker(document, wildcard.select, (token) => {
    insertToken(node, input, `${token}, `);
  });
  root.append(selectors, picker.panel, actions);
  initializeRoot(node, root, document, wildcard.label.children[0]);

  const setStatus = (message) => {
    status.textContent = message;
  };

  let loaded = false;
  let request;
  let domWidget;
  let wildcardOptions;
  let styleOptions;
  unavailable(wildcard.select, "Loading wildcards…", document);
  unavailable(style.select, "Loading styles…", document);
  const load = (refreshCatalog = false) => {
    if (request) return request;
    request = (async () => {
      refresh.disabled = true;
      setStatus("Refreshing prompt libraries…");
      try {
        const result = await loadCatalog(fetchLibraries, refreshCatalog);
        const nextWildcardOptions = buildOptions(
          result.wildcards.some((entry) => !entry.disabled)
            ? "Choose wildcard…" : "No usable wildcards",
          result.wildcards,
          document,
        );
        const nextStyleOptions = buildOptions(
          result.styles.some((entry) => !entry.disabled)
            ? "Choose style…" : "No usable styles",
          result.styles,
          document,
        );
        wildcardOptions = nextWildcardOptions;
        styleOptions = nextStyleOptions;
        picker.close(false);
        replaceOptions(wildcard.select, wildcardOptions);
        replaceOptions(style.select, styleOptions);
        loaded = true;
        const wildcardCount = result.wildcards.filter((entry) => !entry.disabled).length;
        const styleCount = result.styles.filter((entry) => !entry.disabled).length;
        const wildcardLabel = wildcardCount === 1 ? "wildcard" : "wildcards";
        const styleLabel = styleCount === 1 ? "style" : "styles";
        setStatus(`${wildcardCount} ${wildcardLabel} · ${styleCount} ${styleLabel}`);
      } catch (error) {
        if (!loaded) {
          unavailable(wildcard.select, "Wildcards unavailable", document);
          unavailable(style.select, "Styles unavailable", document);
        }
        setStatus(error instanceof Error
          ? error.message
          : "Prompt libraries are unavailable");
      } finally {
        refresh.disabled = false;
        request = undefined;
      }
    })();
    return request;
  };

  const insertWildcard = (value) => {
    if (value) insertToken(node, input, `__${value}__, `);
    wildcard.select.value = "";
  };
  const insertStyle = (value) => {
    if (value) insertToken(node, input, `[[style:${value}]], `);
    style.select.value = "";
  };
  const openWildcards = (event) => {
    if (wildcard.select.disabled || !wildcardOptions) return;
    event.preventDefault?.();
    picker.open(wildcardOptions);
  };
  wildcard.select.addEventListener("pointerdown", openWildcards);
  wildcard.select.addEventListener("keydown", (event) => {
    if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) {
      openWildcards(event);
    }
  });
  wildcard.select.addEventListener("change", () => {
    insertWildcard(wildcard.select.value);
  });
  style.select.addEventListener("pointerdown", (event) => {
    if (!style.select.disabled && styleOptions && menu(styleOptions, event, insertStyle)) {
      event.preventDefault?.();
    }
  });
  style.select.addEventListener("change", () => {
    insertStyle(style.select.value);
  });
  refresh.addEventListener("click", () => {
    domWidget.lfggReady = load(true);
  });

  const contentHeight = () => {
    // Restore mounts the panel before its host container has a width.
    // Measuring then mistakes padding-only text wrapping for required height.
    const measured = root.parentElement?.clientWidth
      ? Math.ceil(root.scrollHeight)
      : 0;
    return 2 * (domWidget?.margin ?? 10) + (measured || (
      UI.inset * 2
      + UI.controlHeight * 2
      + UI.secondarySize * 2
      + UI.gap * 2
    ));
  };
  domWidget = node.addDOMWidget(
    "lfgg_prompt_composer",
    "lfgg_prompt_composer",
    root,
    {
      serialize: false,
      getMinHeight: contentHeight,
      getHeight: contentHeight,
    },
  );
  domWidget.computeSize = () => [0, contentHeight()];
  domWidget.serialize = false;
  domWidget.options.serialize = false;
  const domIndex = node.widgets.indexOf(domWidget);
  const seedIndex = node.widgets.findIndex(({ name }) => name === "seed");
  if (domIndex >= 0 && seedIndex >= 0 && domIndex > seedIndex) {
    node.widgets.splice(domIndex, 1);
    node.widgets.splice(seedIndex, 0, domWidget);
  }
  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    if (
      Array.isArray(serialized.widgets_values) &&
      serialized.widgets_values.length === node.widgets.length
    ) {
      serialized.widgets_values.splice(node.widgets.indexOf(domWidget), 1);
    }
    return result;
  };
  let fittedHeight;
  const observer = typeof ResizeObserver === "function" ? new ResizeObserver(() => {
    if (!root.parentElement?.clientWidth) return;
    const height = contentHeight();
    if (height === fittedHeight) return;
    fittedHeight = height;
    node.setSize([
      node.size[0],
      Math.max(node.size[1], node.computeSize()[1]),
    ]);
    node.setDirtyCanvas?.(true, true);
  }) : undefined;
  observer?.observe(root);
  const removed = node.onRemoved;
  node.onRemoved = function (...args) {
    observer?.disconnect();
    return removed?.apply(this, args);
  };
  node[installed] = domWidget;
  domWidget.lfggReady = load();
  return domWidget;
}
