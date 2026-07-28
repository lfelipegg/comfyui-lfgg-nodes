import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { installCropEditor } from "./crop_editor.mjs";

const buildViewUrl = (value) => {
  const normalized = String(value).replace(/\s+\[input\]$/, "").replaceAll("\\", "/");
  const slash = normalized.lastIndexOf("/");
  const query = new URLSearchParams({
    filename: normalized.slice(slash + 1),
    subfolder: slash < 0 ? "" : normalized.slice(0, slash),
    type: "input",
  });
  return api.apiURL(`/view?${query}`);
};

const install = (node) =>
  installCropEditor(node, {
    buildViewUrl,
    getGraph: () => app.graph,
    isConfiguring: () => app.configuringGraph,
  });

app.registerExtension({
  name: "lfgg.loadAndCropImage.editor",
  nodeCreated: install,
  loadedGraphNode: install,
});
