import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { buildInputViewUrl } from "./crop_editor.mjs";
import {
  buildVideoViewUrl,
  installVideoCutter,
} from "./video_cutter.mjs";

const metadata = async (input) => {
  const response = await api.fetchApi("/lfgg/v1/video-metadata", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input }),
  });
  if (!response.ok) throw new Error("Video metadata is unavailable");
  return response.json();
};

const install = (node) =>
  installVideoCutter(node, {
    getGraph: () => app.graph,
    buildViewUrl: (value) => api.apiURL(buildInputViewUrl(value)),
    buildOutputViewUrl: (value) => api.apiURL(buildVideoViewUrl(value)),
    fetchMetadata: metadata,
  });

app.registerExtension({
  name: "lfgg.videoCutter.editor",
  nodeCreated: install,
  loadedGraphNode: install,
});
