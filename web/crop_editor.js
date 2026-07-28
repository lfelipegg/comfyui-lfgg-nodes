import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { buildInputViewUrl, installCropEditor } from "./crop_editor.mjs";

const install = (node) =>
  installCropEditor(node, {
    buildViewUrl: (value) => api.apiURL(buildInputViewUrl(value)),
    getGraph: () => app.graph,
    isConfiguring: () => app.configuringGraph,
  });

app.registerExtension({
  name: "lfgg.loadAndCropImage.editor",
  nodeCreated: install,
  loadedGraphNode: install,
});
