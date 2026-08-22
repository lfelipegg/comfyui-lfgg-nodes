import { app } from "../../scripts/app.js";
import { extendStringJoin } from "./string_join.mjs";

app.registerExtension({
  name: "lfgg.string_join",
  beforeRegisterNodeDef(nodeType, nodeData) {
    extendStringJoin(nodeType, nodeData, { LiteGraph: globalThis.LiteGraph });
  },
});
