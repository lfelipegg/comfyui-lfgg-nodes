import { app } from "../../scripts/app.js";
import { extendSwitches } from "./switches.mjs";

app.registerExtension({
  name: "lfgg.switches",
  beforeRegisterNodeDef(nodeType, nodeData) {
    extendSwitches(nodeType, nodeData, { LiteGraph: globalThis.LiteGraph });
  },
});
