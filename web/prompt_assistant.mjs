import { createEditorView, omitPresentationValues } from "./editor_view.mjs";
import { UI, initializeRoot } from "./node_ui.mjs";

export const PROMPT_ASSISTANT_ID = "LFGG_PromptAssistant";
export const PROMPT_ASSISTANT_NAME = "LFGG Prompt Assistant";
export const SERVER_DEFAULT_MODEL = "server default";
const INITIAL_REPORT = "Run to generate a prompt";
const installed = Symbol("lfggPromptAssistant");

// ---------------------------------------------------------------------------
// Pure selection helpers: the `skills` text is the only state they touch.
// ---------------------------------------------------------------------------

export function parseSelection(text) {
  return String(text ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((raw) => {
      const index = raw.indexOf("/");
      return index < 0
        ? { skill: raw, file: null, raw }
        : { skill: raw.slice(0, index), file: raw.slice(index + 1), raw };
    });
}

export function formatSelection(entries) {
  return entries.map((entry) => entry.raw).join("\n");
}

function withoutDuplicates(entries) {
  const seen = new Set();
  return entries.filter((entry) => !seen.has(entry.raw) && seen.add(entry.raw));
}

export function setSkill(text, skill, checked) {
  const entries = parseSelection(text);
  if (!checked) return formatSelection(entries.filter((entry) => entry.skill !== skill));
  if (entries.some((entry) => entry.skill === skill && entry.file === null)) return formatSelection(entries);
  return formatSelection(withoutDuplicates([...entries, { skill, file: null, raw: skill }]));
}

export function setFile(text, skill, file, checked) {
  const raw = `${skill}/${file}`;
  const entries = parseSelection(text);
  if (!checked) return formatSelection(entries.filter((entry) => entry.raw !== raw));
  return formatSelection(withoutDuplicates([...entries, { skill, file, raw }]));
}

export function setAllFiles(text, skill, files, checked) {
  return files.reduce((current, file) => setFile(current, skill, file, checked), text);
}

export function selectionSummary(text, catalog) {
  const entries = parseSelection(text);
  const skills = new Map((catalog?.skills ?? []).map((skill) => [skill.name, skill]));
  const selectedSkills = new Set(entries.map((entry) => entry.skill));
  let bytes = 0;
  const unknown = [];
  for (const name of selectedSkills) {
    const skill = skills.get(name);
    if (!skill?.available) unknown.push(name);
    else bytes += skill.skill_size ?? 0;
  }
  let files = 0;
  for (const entry of entries) {
    if (entry.file === null) continue;
    files += 1;
    const size = skills.get(entry.skill)?.files?.find((item) => item.path === entry.file)?.size;
    if (size === undefined) {
      if (!unknown.includes(entry.raw)) unknown.push(entry.raw);
    } else bytes += size;
  }
  return { skills: selectedSkills.size, files, bytes, unknown };
}

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const kib = bytes / 1024;
  return `${kib < 10 ? kib.toFixed(1) : Math.round(kib)} KiB`;
}

function linked(node, name) {
  return node?.inputs?.find((input) => input.name === name)?.link != null;
}

function widgetNamed(node, name) {
  return node.widgets?.find((widget) => widget.name === name);
}

function button(document, label, role) {
  const element = document.createElement("button");
  element.type = "button";
  element.textContent = label;
  element.dataset.role = role;
  Object.assign(element.style, { minHeight: `${UI.controlHeight}px`, padding: `0 ${UI.gap}px` });
  return element;
}

function statusLine(document, role) {
  const element = document.createElement("span");
  element.dataset.role = role;
  element.setAttribute("role", "status");
  element.setAttribute("aria-live", "polite");
  Object.assign(element.style, {
    minWidth: "0", flex: "1 1 120px", color: "var(--lfgg-secondary)",
    fontSize: `${UI.secondarySize}px`, overflowWrap: "anywhere",
  });
  return element;
}

function row(document, role, gap = UI.gap) {
  const element = document.createElement("div");
  element.dataset.role = role;
  Object.assign(element.style, {
    display: "flex", alignItems: "center", flexWrap: "wrap", gap: `${UI.tightGap}px ${gap}px`, minWidth: "0",
  });
  return element;
}

function checkbox(document, role, label, id) {
  const wrapper = document.createElement("label");
  const input = document.createElement("input");
  const text = document.createElement("span");
  input.type = "checkbox";
  input.dataset.role = role;
  input.dataset.id = id;
  text.textContent = label;
  Object.assign(wrapper.style, { display: "flex", alignItems: "center", gap: `${UI.tightGap}px`, minHeight: `${UI.controlHeight}px`, minWidth: "0" });
  Object.assign(text.style, { minWidth: "0", overflowWrap: "anywhere" });
  wrapper.append(input, text);
  return { wrapper, input, text };
}

// ---------------------------------------------------------------------------
// Installation
// ---------------------------------------------------------------------------

export function installPromptAssistant(
  node,
  { document = globalThis.document, fetchSkills, fetchModels, nodeOutputs } = {},
) {
  if (
    node.comfyClass !== PROMPT_ASSISTANT_ID || node[installed] || !document
    || typeof fetchSkills !== "function" || typeof fetchModels !== "function"
  ) {
    return node[installed];
  }
  const skillsWidget = widgetNamed(node, "skills");
  const modelWidget = widgetNamed(node, "model");
  if (!skillsWidget || !modelWidget) return;

  // --- Skills picker -------------------------------------------------------
  const root = document.createElement("div");
  const heading = row(document, "heading");
  const title = document.createElement("span");
  const disclosure = button(document, "Expand", "disclosure");
  const refreshSkills = button(document, "Refresh skills", "refresh-skills");
  const summary = statusLine(document, "summary");
  const locks = statusLine(document, "locks");
  const list = document.createElement("div");
  const skillsStatus = statusLine(document, "skills-status");
  title.dataset.role = "title";
  title.textContent = "Skills";
  Object.assign(title.style, { display: "flex", alignItems: "center", fontSize: "14px", fontWeight: "600", lineHeight: "1.2" });
  disclosure.setAttribute("aria-expanded", "false");
  list.dataset.role = "skill-list";
  Object.assign(list.style, { display: "grid", gap: `${UI.tightGap}px`, minWidth: "0", maxHeight: "360px", overflow: "auto" });
  Object.assign(root.style, {
    display: "grid", gap: `${UI.gap}px`, width: "100%", minWidth: "0", height: "auto",
    alignContent: "start", padding: `${UI.inset}px`, boxSizing: "border-box",
  });
  heading.append(title, disclosure, refreshSkills);
  const modelRow = row(document, "model-row");
  const refreshModels = button(document, "Refresh models", "refresh-models");
  const modelStatus = statusLine(document, "model-status");
  modelRow.append(refreshModels, modelStatus);
  root.append(heading, summary, locks, list, skillsStatus, modelRow);
  initializeRoot(node, root, document, title);

  let catalog;
  let catalogError;
  let lockedSkills = false;
  let expanded = false;
  const skillsText = () => String(skillsWidget.value ?? "");
  const writeSkills = (text) => {
    if (lockedSkills || text === skillsText()) return;
    skillsWidget.value = text;
    skillsWidget.callback?.(text);
    if (skillsWidget.inputEl) skillsWidget.inputEl.value = text;
    node.setDirtyCanvas?.(true, true);
    render();
  };

  const renderSummary = () => {
    if (!catalog) {
      summary.textContent = catalogError ?? "Loading skills…";
      return;
    }
    const info = selectionSummary(skillsText(), catalog);
    const limit = catalog.limits?.total;
    const parts = [
      `${info.skills} ${info.skills === 1 ? "skill" : "skills"}`,
      `${info.files} ${info.files === 1 ? "reference" : "references"}`,
      `≈ ${formatBytes(info.bytes)}${limit ? ` of ${formatBytes(limit)}` : ""}`,
    ];
    if (info.unknown.length) parts.push(`unresolved: ${info.unknown.join(", ")}`);
    summary.dataset.over = String(Boolean(limit) && info.bytes > limit);
    summary.textContent = parts.join(" · ") + (summary.dataset.over === "true" ? " · over the limit" : "");
  };

  const renderLocks = () => {
    const connected = ["master_prompt", "request", "skills"].filter((name) => linked(node, name));
    lockedSkills = connected.includes("skills");
    locks.textContent = connected.length
      ? `Connected upstream: ${connected.join(", ")}. Disconnect to edit here.`
      : "";
    locks.hidden = connected.length === 0;
  };

  const fileExpanded = new Set();
  const renderList = () => {
    list.replaceChildren();
    list.hidden = !expanded;
    if (!expanded) return;
    if (!catalog) {
      const note = document.createElement("div");
      note.dataset.role = "empty";
      note.textContent = catalogError ?? "Loading skills…";
      list.append(note);
      return;
    }
    const entries = parseSelection(skillsText());
    const selectedSkills = new Set(entries.map((entry) => entry.skill));
    const selectedFiles = new Set(entries.filter((entry) => entry.file !== null).map((entry) => entry.raw));
    const missingRoots = (catalog.roots ?? []).filter((item) => !item.available).map((item) => item.path);
    if (!catalog.skills?.length) {
      const note = document.createElement("div");
      note.dataset.role = "empty";
      note.textContent = "No allowlisted skills were found. Check prompt_assistant.skills_roots in config.json.";
      list.append(note);
    }
    for (const skill of catalog.skills ?? []) {
      const item = document.createElement("div");
      item.dataset.role = "skill";
      item.dataset.name = skill.name;
      Object.assign(item.style, { display: "grid", gap: `${UI.tightGap}px`, minWidth: "0" });
      const head = row(document, "skill-head", UI.tightGap);
      const box = checkbox(document, "skill-toggle", skill.name, skill.name);
      box.input.checked = selectedSkills.has(skill.name);
      box.input.disabled = lockedSkills || !skill.available;
      box.input.addEventListener("change", () => writeSkills(setSkill(skillsText(), skill.name, box.input.checked)));
      head.append(box.wrapper);
      const hint = document.createElement("span");
      hint.dataset.role = "skill-hint";
      Object.assign(hint.style, { color: "var(--lfgg-secondary)", fontSize: `${UI.secondarySize}px`, overflowWrap: "anywhere", minWidth: "0" });
      if (!skill.available) {
        hint.textContent = `unavailable · roots searched: ${(catalog.roots ?? []).map((r) => r.path).join(", ") || "none"}`;
      } else {
        hint.textContent = skill.root;
        const files = skill.files ?? [];
        if (files.length) {
          const toggleFiles = button(document, fileExpanded.has(skill.name) ? "Hide references" : `References (${files.length})`, "files-toggle");
          toggleFiles.dataset.name = skill.name;
          toggleFiles.setAttribute("aria-expanded", String(fileExpanded.has(skill.name)));
          toggleFiles.addEventListener("click", () => {
            if (fileExpanded.has(skill.name)) fileExpanded.delete(skill.name);
            else fileExpanded.add(skill.name);
            render();
          });
          const all = button(document, "All references", "all-files");
          all.dataset.name = skill.name;
          all.disabled = lockedSkills;
          all.addEventListener("click", () => writeSkills(
            setAllFiles(skillsText(), skill.name, files.map((file) => file.path), true),
          ));
          head.append(toggleFiles, all);
          if (fileExpanded.has(skill.name)) {
            const fileList = document.createElement("div");
            fileList.dataset.role = "file-list";
            Object.assign(fileList.style, { display: "grid", gap: "0", minWidth: "0", paddingLeft: `${UI.inset}px` });
            for (const file of files) {
              const raw = `${skill.name}/${file.path}`;
              const fileBox = checkbox(document, "file-toggle", `${file.path} (${formatBytes(file.size)})`, raw);
              fileBox.input.checked = selectedFiles.has(raw);
              fileBox.input.disabled = lockedSkills;
              fileBox.input.addEventListener("change", () => writeSkills(
                setFile(skillsText(), skill.name, file.path, fileBox.input.checked),
              ));
              fileList.append(fileBox.wrapper);
            }
            item.append(head, hint, fileList);
            list.append(item);
            continue;
          }
        }
      }
      item.append(head, hint);
      list.append(item);
    }
    if (missingRoots.length) {
      const note = document.createElement("div");
      note.dataset.role = "missing-roots";
      Object.assign(note.style, { color: "var(--lfgg-secondary)", fontSize: `${UI.secondarySize}px`, overflowWrap: "anywhere" });
      note.textContent = `Missing roots on this machine: ${missingRoots.join(", ")}`;
      list.append(note);
    }
  };

  let domWidget;
  const render = () => {
    renderLocks();
    renderSummary();
    renderList();
    disclosure.textContent = expanded ? "Collapse" : "Expand";
    disclosure.setAttribute("aria-expanded", String(expanded));
    view?.fit(true);
  };

  let skillsRequest;
  const loadSkills = () => {
    if (skillsRequest) return skillsRequest;
    skillsRequest = (async () => {
      refreshSkills.disabled = true;
      skillsStatus.textContent = "Refreshing skills…";
      try {
        const result = await fetchSkills();
        if (!result || !Array.isArray(result.skills)) throw new Error("Skills are unavailable");
        catalog = result;
        catalogError = undefined;
        const available = result.skills.filter((skill) => skill.available).length;
        const missing = result.skills.length - available;
        skillsStatus.textContent = `${available} available${missing ? ` · ${missing} missing` : ""}`
          + (result.warnings?.length ? ` · ${result.warnings.length} warning${result.warnings.length === 1 ? "" : "s"} in the server log` : "");
      } catch (error) {
        catalogError = error instanceof Error ? error.message : "Skills are unavailable";
        skillsStatus.textContent = catalog ? `${catalogError} · showing previous skills.` : catalogError;
      } finally {
        refreshSkills.disabled = false;
        skillsRequest = undefined;
        render();
      }
    })();
    return skillsRequest;
  };
  refreshSkills.addEventListener("click", () => { domWidget.lfggReady = loadSkills(); });

  // --- Model refresh ------------------------------------------------------
  const renderModelStatus = (message) => {
    const values = modelWidget.options?.values ?? [];
    const current = String(modelWidget.value ?? SERVER_DEFAULT_MODEL);
    const missing = current !== SERVER_DEFAULT_MODEL && !values.includes(current);
    modelStatus.dataset.missing = String(missing);
    modelStatus.textContent = missing
      ? `${message ? `${message} · ` : ""}saved model "${current}" is not listed on the server; refresh or pick another.`
      : message;
  };
  let modelsRequest;
  const loadModels = () => {
    if (modelsRequest) return modelsRequest;
    modelsRequest = (async () => {
      refreshModels.disabled = true;
      renderModelStatus("Refreshing models…");
      try {
        const result = await fetchModels();
        if (!result || !Array.isArray(result.models)) throw new Error("Models are unavailable");
        const ids = result.models.map((model) => String(model.id)).filter(Boolean);
        modelWidget.options ??= {};
        modelWidget.options.values = [SERVER_DEFAULT_MODEL, ...ids];
        const loaded = result.models.filter((model) => model.status === "loaded").map((model) => model.id);
        renderModelStatus(
          `${ids.length} ${ids.length === 1 ? "model" : "models"} · ${result.mode === "single" ? "single-model" : "router"} mode`
          + (loaded.length ? ` · loaded: ${loaded.join(", ")}` : ""),
        );
      } catch (error) {
        renderModelStatus(error instanceof Error ? error.message : "Models are unavailable");
      } finally {
        refreshModels.disabled = false;
        modelsRequest = undefined;
        node.setDirtyCanvas?.(true, true);
      }
    })();
    return modelsRequest;
  };
  refreshModels.addEventListener("click", () => { domWidget.lfggModelsReady = loadModels(); });
  renderModelStatus("");

  // --- Result report ------------------------------------------------------
  const reportRoot = document.createElement("div");
  const reportHeading = document.createElement("div");
  const report = document.createElement("pre");
  const reportStatus = statusLine(document, "report-status");
  reportHeading.dataset.role = "report-heading";
  reportHeading.textContent = "Generated prompt";
  Object.assign(reportHeading.style, { display: "flex", alignItems: "center", fontSize: "14px", fontWeight: "600", lineHeight: "1.2" });
  Object.assign(reportRoot.style, {
    display: "grid", gridTemplateRows: "auto minmax(0, 1fr) auto", gap: `${UI.gap}px`, width: "100%",
    height: "100%", minWidth: "0", minHeight: "0", padding: `${UI.inset}px`, boxSizing: "border-box", overflow: "hidden",
  });
  report.dataset.role = "report";
  report.dataset.stale = "false";
  report.tabIndex = 0;
  report.setAttribute("role", "region");
  report.setAttribute("aria-label", "Generated prompt");
  report.textContent = INITIAL_REPORT;
  Object.assign(report.style, {
    width: "100%", minWidth: "0", minHeight: "0", maxHeight: "360px", margin: "0", overflow: "auto",
    whiteSpace: "pre-wrap", overflowWrap: "anywhere",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    fontSize: `${UI.secondarySize}px`, lineHeight: "1.4", userSelect: "text", boxSizing: "border-box",
  });
  reportRoot.append(reportHeading, report, reportStatus);
  initializeRoot(node, reportRoot, document, reportHeading);
  let lastReport;
  const renderReport = (state, message) => {
    report.dataset.stale = String(state === "stale");
    report.textContent = lastReport ?? INITIAL_REPORT;
    reportStatus.dataset.state = state;
    reportStatus.textContent = message;
  };
  const restoreReport = () => {
    const text = nodeOutputs?.()?.[String(node.id)]?.text?.[0];
    if (typeof text === "string") {
      lastReport = text;
      renderReport("current", "Restored from the last execution.");
    }
  };
  renderReport("waiting", "Waiting for execution.");
  restoreReport();

  const originalExecutionStart = node.onExecutionStart;
  node.onExecutionStart = function (...args) {
    const result = originalExecutionStart?.apply(this, args);
    renderReport(
      lastReport === undefined ? "waiting" : "stale",
      lastReport === undefined ? "Generating…" : "Generating · showing previous prompt.",
    );
    return result;
  };
  const originalExecuted = node.onExecuted;
  node.onExecuted = function (message) {
    const result = originalExecuted?.apply(this, arguments);
    const next = message?.text?.[0];
    if (typeof next === "string") {
      lastReport = next;
      renderReport("current", "Current prompt.");
    } else {
      renderReport(
        lastReport === undefined ? "waiting" : "stale",
        lastReport === undefined ? "No prompt received." : "No prompt received · showing previous prompt.",
      );
    }
    return result;
  };
  const originalExecutionError = node.onExecutionError;
  node.onExecutionError = function (...args) {
    const result = originalExecutionError?.apply(this, args);
    renderReport(
      lastReport === undefined ? "waiting" : "stale",
      lastReport === undefined ? "Execution failed before a prompt was available." : "Execution failed · showing previous prompt.",
    );
    return result;
  };

  // --- Widgets, placement, serialization, and graph events ----------------
  const contentHeight = () => {
    const measured = root.parentElement?.clientWidth ? Math.ceil(root.scrollHeight) : 0;
    return 2 * (domWidget?.margin ?? 10) + (measured || (
      UI.inset * 2 + UI.controlHeight * 2 + UI.secondarySize * 3 + UI.gap * 4
    ));
  };
  domWidget = node.addDOMWidget("lfgg_prompt_assistant_skills", "lfgg_prompt_assistant_skills", root, {
    serialize: false, getMinHeight: contentHeight, getHeight: contentHeight,
  });
  domWidget.computeSize = () => [0, contentHeight()];
  domWidget.serialize = false;
  domWidget.options.serialize = false;
  const reportWidget = node.addDOMWidget("lfgg_prompt_assistant_report", "lfgg_prompt_assistant_report", reportRoot, {
    serialize: false, getMinHeight: () => 104,
  });
  reportWidget.serialize = false;
  reportWidget.options.serialize = false;
  const domIndex = node.widgets.indexOf(domWidget);
  const skillsIndex = node.widgets.indexOf(skillsWidget);
  if (domIndex >= 0 && skillsIndex >= 0 && domIndex !== skillsIndex + 1) {
    node.widgets.splice(domIndex, 1);
    node.widgets.splice(skillsIndex + 1, 0, domWidget);
  }
  const originalSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalSerialize?.apply(this, arguments);
    omitPresentationValues(node, serialized, [domWidget, reportWidget]);
    return result;
  };
  const view = createEditorView(node, {
    changed: (value) => { expanded = value; render(); },
  });
  const originalConfigure = node.onConfigure;
  node.onConfigure = function (...args) {
    const result = originalConfigure?.apply(this, args);
    restoreReport();
    render();
    return result;
  };
  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function (...args) {
    const result = originalConnectionsChange?.apply(this, args);
    render();
    return result;
  };
  const originalCallback = skillsWidget.callback;
  skillsWidget.callback = function (...args) {
    const result = originalCallback?.apply(this, args);
    render();
    return result;
  };
  skillsWidget.inputEl?.addEventListener?.("input", () => {
    skillsWidget.value = skillsWidget.inputEl.value;
    render();
  });
  disclosure.addEventListener("click", () => view.setExpanded(!expanded));

  node[installed] = domWidget;
  expanded = view.expanded;
  render();
  domWidget.lfggReady = loadSkills();
  domWidget.lfggReport = reportWidget;
  return domWidget;
}
