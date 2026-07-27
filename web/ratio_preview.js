import { app } from "../../scripts/app.js";
import { installRatioPreview } from "./ratio_preview.mjs";

const install = (node) =>
  installRatioPreview(node, { isConfiguring: () => app.configuringGraph });

app.registerExtension({
  name: "lfgg.dimensionsByAspectRatio.preview",
  nodeCreated: install,
  loadedGraphNode: install,
});
