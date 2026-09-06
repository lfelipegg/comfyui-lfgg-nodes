# LFGG Load and Crop Image

Choose one still image from ComfyUI's input directory, then move or resize the
crop frame, including in the compact view. Corner drags preserve the exact
ratio. **Edit crop** opens a larger preview and the native X/Y/width controls
for keyboard editing; height remains derived and read-only. The caption reports
source pixels. **Hide crop controls** changes no crop values.

Local ratio values and connected Primitive values update immediately. For
other connected values, run the workflow when the editor says
`Run to resolve connected ratio`; the backend returns a centered crop that can
then be edited and rerun.

The crop persists when the same workflow, image, and resolved ratio are
reloaded. Selecting another image or changing the ratio resets it. Without the
frontend extension, the seven standard inputs still provide the numeric
fallback.
The strict-Boolean workflow property `lfgg_editor_expanded` remembers only
whether the editor is open. Missing or malformed values open compact. Resizing
or toggling the editor does not reload the source or reset the crop.

Editing is locked while the selected image loads. Failed previews preserve
the saved numeric values and show a recovery message; reselect or upload the
image to retry. A successful execution received during image loading is applied
when that image becomes ready.

The packaged example workflow requires `load_and_crop_image.png`. Copy
`workflows/load_and_crop_image.png` from the node pack to
`ComfyUI/input/load_and_crop_image.png` before running it.
