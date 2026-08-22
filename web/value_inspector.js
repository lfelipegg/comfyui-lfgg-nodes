import { app } from "../../scripts/app.js";
import { installValueInspector } from "./value_inspector.mjs";

app.registerExtension({
  name: "lfgg.valueInspector",
  nodeCreated: installValueInspector,
  loadedGraphNode: installValueInspector,
});
