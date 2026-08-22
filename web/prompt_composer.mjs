const NODE_ID = "LFGG_PromptComposer";
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

function labeledSelect(document, text, role) {
  const label = document.createElement("label");
  const caption = document.createElement("span");
  const select = document.createElement("select");
  caption.textContent = text;
  select.dataset.role = role;
  select.setAttribute("aria-label", text);
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
  const wildcard = labeledSelect(document, "Add wildcard…", "wildcards");
  const style = labeledSelect(document, "Add style…", "styles");
  const refresh = document.createElement("button");
  const status = document.createElement("span");
  refresh.type = "button";
  refresh.textContent = "Refresh libraries";
  refresh.dataset.role = "refresh";
  status.dataset.role = "status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  root.append(wildcard.label, style.label, refresh, status);

  let loaded = false;
  let request;
  let domWidget;
  const load = () => {
    if (request) return request;
    request = (async () => {
      refresh.disabled = true;
      status.textContent = "Refreshing prompt libraries…";
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
        const wildcardOptions = buildOptions(
          "Add wildcard…",
          result.wildcards,
          document,
        );
        const styleOptions = buildOptions(
          "Add style…",
          result.styles,
          document,
        );
        replaceOptions(wildcard.select, wildcardOptions);
        replaceOptions(style.select, styleOptions);
        loaded = true;
        status.textContent = `Loaded ${result.wildcards.length} wildcards and ${result.styles.length} styles.`;
      } catch (error) {
        if (!loaded) {
          unavailable(wildcard.select, "Wildcards unavailable", document);
          unavailable(style.select, "Styles unavailable", document);
        }
        status.textContent = error instanceof Error
          ? error.message
          : "Prompt libraries are unavailable";
      } finally {
        refresh.disabled = false;
        request = undefined;
      }
    })();
    return request;
  };

  wildcard.select.addEventListener("change", () => {
    if (wildcard.select.value) {
      insertToken(node, input, `__${wildcard.select.value}__`);
      wildcard.select.value = "";
    }
  });
  style.select.addEventListener("change", () => {
    if (style.select.value) {
      insertToken(node, input, `[[style:${style.select.value}]]`);
      style.select.value = "";
    }
  });
  refresh.addEventListener("click", () => {
    domWidget.lfggReady = load();
  });

  domWidget = node.addDOMWidget(
    "lfgg_prompt_composer",
    "lfgg_prompt_composer",
    root,
    { serialize: false, getMinHeight: () => 130 },
  );
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
    Math.max(node.size?.[1] ?? 0, 360),
  ]);
  node[installed] = domWidget;
  domWidget.lfggReady = load();
  return domWidget;
}
