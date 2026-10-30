import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { installOutputGallery } from "./output_gallery.mjs";

const fetchJson = async (path, fallback) => {
  const response = await api.fetchApi(path);
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(fallback);
  }
  if (!response.ok) throw new Error(result?.error || fallback);
  return result;
};

const fetchBlob = async (path) => {
  const response = await api.fetchApi(path);
  if (!response.ok) throw new Error(`file request failed with status ${response.status}`);
  return response.blob();
};

const install = (node) => installOutputGallery(node, {
  fetchList: (query) => fetchJson(
    `/lfgg/v1/output-gallery/list?${query}`,
    "Output gallery listing is unavailable",
  ),
  viewUrl: (path) => api.apiURL(path),
  fetchBlob,
  loadFile: (file) => app.handleFile(file),
  isConfiguring: () => app.configuringGraph,
  events: api,
});

app.registerExtension({
  name: "lfgg.outputGallery",
  nodeCreated: install,
  loadedGraphNode: install,
});
