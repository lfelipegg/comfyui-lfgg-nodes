import { app } from "../../scripts/app.js";
import { installPowerLoraLoader } from "./power_lora_loader.mjs";

app.registerExtension({
  name: "lfgg.powerLoraLoaderFolder",
  nodeCreated: (node) => installPowerLoraLoader(node),
  loadedGraphNode: (node) =>
    installPowerLoraLoader(node, { restore: true }),
});
