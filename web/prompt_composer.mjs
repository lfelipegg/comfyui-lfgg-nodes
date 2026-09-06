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
}

function unavailable(select, placeholder, document) {
  const item = option(document, "", true);
  item.textContent = placeholder;
  select.replaceChildren(item);
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
  const caretHint = document.createElement("span");
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
  caretHint.dataset.role = "caret-hint";
  caretHint.textContent = "Inserts at the prompt caret and replaces selected text.";
  Object.assign(caretHint.style, {
    color: "var(--lfgg-secondary)",
    fontSize: `${UI.secondarySize}px`,
    lineHeight: "1.4",
    overflowWrap: "anywhere",
  });
  actions.dataset.role = "actions";
  Object.assign(actions.style, {
    display: "flex",
    alignItems: "center",
    minWidth: "0",
  });
  refresh.type = "button";
  refresh.textContent = "Refresh libraries";
  refresh.dataset.role = "refresh";
  Object.assign(refresh.style, {
    minHeight: `${UI.controlHeight}px`,
    padding: `0 ${UI.gap}px`,
  });
  status.dataset.role = "status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  Object.assign(status.style, {
    display: "block",
    minWidth: "0",
    whiteSpace: "normal",
    overflowWrap: "anywhere",
  });
  selectors.append(wildcard.label, style.label);
  actions.append(refresh);
  root.append(selectors, caretHint, actions, status);
  initializeRoot(node, root, document, wildcard.label.children[0]);

  const setStatus = (message) => {
    status.textContent = message;
  };

  let loaded = false;
  let request;
  let domWidget;
  let wildcardOptions;
  let styleOptions;
  const load = (refreshCatalog = false) => {
    if (request) return request;
    request = (async () => {
      refresh.disabled = true;
      setStatus("Refreshing prompt libraries…");
      try {
        const result = await loadCatalog(fetchLibraries, refreshCatalog);
        const nextWildcardOptions = buildOptions(
          "Choose wildcard…",
          result.wildcards,
          document,
        );
        const nextStyleOptions = buildOptions(
          "Choose style…",
          result.styles,
          document,
        );
        wildcardOptions = nextWildcardOptions;
        styleOptions = nextStyleOptions;
        replaceOptions(wildcard.select, wildcardOptions);
        replaceOptions(style.select, styleOptions);
        loaded = true;
        const wildcardLabel = result.wildcards.length === 1 ? "wildcard" : "wildcards";
        const styleLabel = result.styles.length === 1 ? "style" : "styles";
        setStatus(`${result.wildcards.length} ${wildcardLabel} · ${result.styles.length} ${styleLabel}`);
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
  wildcard.select.addEventListener("pointerdown", (event) => {
    if (wildcardOptions && menu(wildcardOptions, event, insertWildcard)) {
      event.preventDefault?.();
    }
  });
  wildcard.select.addEventListener("change", () => {
    insertWildcard(wildcard.select.value);
  });
  style.select.addEventListener("pointerdown", (event) => {
    if (styleOptions && menu(styleOptions, event, insertStyle)) {
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
    const measured = Math.ceil(
      root.scrollHeight
      || root.getBoundingClientRect?.().height
      || 0,
    );
    return measured || (
      UI.inset * 2
      + UI.controlHeight * 2
      + UI.secondarySize * 3
      + UI.gap * 3
    );
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
  node[installed] = domWidget;
  domWidget.lfggReady = load();
  return domWidget;
}
