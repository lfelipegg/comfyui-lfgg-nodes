# LFGG Load and Crop Image

Choose one still image from ComfyUI's input directory, then move or resize the
crop frame. Corner drags preserve the exact ratio; the visible X, Y, and width
controls provide keyboard editing, while height is derived.

Local ratio values and connected Primitive values update immediately. For
other connected values, run the workflow when the editor says
`Run to resolve connected ratio`; the backend returns a centered crop that can
then be edited and rerun.

The crop persists when the same workflow, image, and resolved ratio are
reloaded. Selecting another image or changing the ratio resets it. Without the
frontend extension, the seven standard inputs still provide the numeric
fallback.

The packaged example workflow requires `load_and_crop_image.png`. Copy
`workflows/load_and_crop_image.png` from the node pack to
`ComfyUI/input/load_and_crop_image.png` before running it.
