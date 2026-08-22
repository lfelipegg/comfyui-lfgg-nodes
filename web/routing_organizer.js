import { app } from "../../scripts/app.js";
import { registerRoutingOrganizer } from "./routing_organizer.mjs";

app.registerExtension({
  name: "lfgg.routingOrganizer",
  registerCustomNodes() {
    registerRoutingOrganizer({ LiteGraph: globalThis.LiteGraph, app });
  },
});
