import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { installPromptComposer } from "./prompt_composer.mjs?v=1.5.0-search";

const libraries = async () => {
  const response = await api.fetchApi("/lfgg/v1/prompt-composer/libraries");
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error("Prompt libraries are unavailable");
  }
  if (!response.ok) throw new Error(result?.error || "Prompt libraries are unavailable");
  return result;
};

const install = (node) => installPromptComposer(node, { fetchLibraries: libraries });

app.registerExtension({
  name: "lfgg.promptComposer.libraries",
  nodeCreated: install,
  loadedGraphNode: install,
});
