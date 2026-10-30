import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { installPromptAssistant } from "./prompt_assistant.mjs";

const fetchJson = async (path, fallback) => {
  const response = await api.fetchApi(path);
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(fallback);
  }
  if (!response.ok) throw new Error(result?.error || fallback);
  return result;
};

const install = (node) => installPromptAssistant(node, {
  fetchSkills: () => fetchJson("/lfgg/v1/prompt-assistant/skills", "Skills are unavailable"),
  fetchModels: () => fetchJson("/lfgg/v1/prompt-assistant/models", "Models are unavailable"),
  nodeOutputs: () => app.nodeOutputs,
});

app.registerExtension({
  name: "lfgg.promptAssistant",
  nodeCreated: install,
  loadedGraphNode: install,
});
