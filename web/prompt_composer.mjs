const NODE_ID = "LFGG_PromptComposer";
const CONTROLS_HEIGHT = 136;
const installed = Symbol("lfggPromptComposer");

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
    if (
      !entry ||
      typeof entry.name !== "string" ||
      !entry.name ||
      typeof entry.disabled !== "boolean"
    ) {
      throw new Error("The prompt library response is invalid");
    }
    choices.push(option(document, entry.name, entry.disabled));
  }
  return choices;
}

function replaceOptions(select, choices) {
  select.replaceChildren(...choices);
  select.value = "";
}

function filterOptions(select, choices, query) {
  const term = query.trim().toLowerCase();
  replaceOptions(
    select,
    term
      ? [choices[0], ...choices.slice(1).filter(({ textContent }) =>
        textContent.toLowerCase().includes(term))]
      : choices,
  );
}

function unavailable(select, placeholder, document) {
  const item = option(document, "", true);
  item.textContent = placeholder;
  select.replaceChildren(item);
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

function searchableSelect(document, text, role) {
  const group = document.createElement("div");
  const caption = document.createElement("span");
  const search = document.createElement("input");
  const select = document.createElement("select");
  caption.textContent = text;
  search.type = "search";
  search.placeholder = `Search ${text.toLowerCase()}s…`;
  search.disabled = true;
  search.dataset.role = `${role}-search`;
  search.setAttribute("aria-label", `Search ${text.toLowerCase()}s`);
  select.dataset.role = role;
  select.setAttribute("aria-label", text);
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", text);
  Object.assign(group.style, {
    display: "grid",
    gap: "4px",
    minWidth: "0",
  });
  Object.assign(caption.style, {
    fontSize: "11px",
    lineHeight: "1.2",
    opacity: "0.75",
  });
  const controlStyle = {
    width: "100%",
    minWidth: "0",
    maxWidth: "100%",
    height: "28px",
    boxSizing: "border-box",
  };
  Object.assign(search.style, controlStyle);
  Object.assign(select.style, controlStyle);
  group.append(caption, search, select);
  return { group, search, select };
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
  const wildcard = searchableSelect(document, "Wildcard", "wildcards");
  const style = searchableSelect(document, "Style", "styles");
  const refresh = document.createElement("button");
  const status = document.createElement("span");
  Object.assign(root.style, {
    display: "grid",
    gap: "8px",
    width: "100%",
    minWidth: "0",
    height: `${CONTROLS_HEIGHT}px`,
    maxHeight: `${CONTROLS_HEIGHT}px`,
    alignContent: "start",
    padding: "8px",
    boxSizing: "border-box",
  });
  selectors.dataset.role = "selectors";
  Object.assign(selectors.style, {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: "8px",
    minWidth: "0",
  });
  actions.dataset.role = "actions";
  Object.assign(actions.style, {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    minWidth: "0",
  });
  refresh.type = "button";
  refresh.textContent = "Refresh libraries";
  refresh.dataset.role = "refresh";
  Object.assign(refresh.style, {
    flex: "0 0 auto",
    height: "28px",
    padding: "0 10px",
    boxSizing: "border-box",
  });
  status.dataset.role = "status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  Object.assign(status.style, {
    flex: "1 1 auto",
    minWidth: "0",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    fontSize: "11px",
    lineHeight: "1.3",
    opacity: "0.8",
  });
  selectors.append(wildcard.group, style.group);
  actions.append(refresh, status);
  root.append(selectors, actions);

  const setStatus = (message) => {
    status.textContent = message;
    status.title = message;
  };

  let loaded = false;
  let request;
  let domWidget;
  let wildcardOptions;
  let styleOptions;
  const load = () => {
    if (request) return request;
    request = (async () => {
      refresh.disabled = true;
      setStatus("Refreshing…");
      try {
        const result = await fetchLibraries();
        if (
          !result ||
          result.ok !== true ||
          !Array.isArray(result.wildcards) ||
          !Array.isArray(result.styles)
        ) {
          throw new Error(result?.error || "The prompt library response is invalid");
        }
        const nextWildcardOptions = buildOptions(
          "Add wildcard…",
          result.wildcards,
          document,
        );
        const nextStyleOptions = buildOptions(
          "Add style…",
          result.styles,
          document,
        );
        wildcardOptions = nextWildcardOptions;
        styleOptions = nextStyleOptions;
        wildcard.search.disabled = false;
        style.search.disabled = false;
        filterOptions(wildcard.select, wildcardOptions, wildcard.search.value);
        filterOptions(style.select, styleOptions, style.search.value);
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

  wildcard.select.addEventListener("change", () => {
    if (wildcard.select.value) {
      insertToken(node, input, `__${wildcard.select.value}__, `);
      wildcard.select.value = "";
    }
  });
  wildcard.search.addEventListener("input", () => {
    if (wildcardOptions) {
      filterOptions(wildcard.select, wildcardOptions, wildcard.search.value);
    }
  });
  style.select.addEventListener("change", () => {
    if (style.select.value) {
      insertToken(node, input, `[[style:${style.select.value}]], `);
      style.select.value = "";
    }
  });
  style.search.addEventListener("input", () => {
    if (styleOptions) {
      filterOptions(style.select, styleOptions, style.search.value);
    }
  });
  refresh.addEventListener("click", () => {
    domWidget.lfggReady = load();
  });

  domWidget = node.addDOMWidget(
    "lfgg_prompt_composer",
    "lfgg_prompt_composer",
    root,
    {
      serialize: false,
      getMinHeight: () => CONTROLS_HEIGHT,
      getMaxHeight: () => CONTROLS_HEIGHT,
      getHeight: () => CONTROLS_HEIGHT,
    },
  );
  domWidget.computeSize = () => [0, CONTROLS_HEIGHT];
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
  node.setSize?.([
    Math.max(node.size?.[0] ?? 0, 360),
    Math.max(node.size?.[1] ?? 0, 330),
  ]);
  node[installed] = domWidget;
  domWidget.lfggReady = load();
  return domWidget;
}
