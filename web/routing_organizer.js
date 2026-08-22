import { app } from "../../scripts/app.js";
import { extendRoutingOrganizer } from "./routing_organizer.mjs";

app.registerExtension({
  name: "lfgg.routingOrganizer",
  beforeRegisterNodeDef(nodeType, nodeData) {
    extendRoutingOrganizer(nodeType, nodeData, {
      LiteGraph: globalThis.LiteGraph,
      app,
    });
  },
});
