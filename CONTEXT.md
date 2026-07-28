# LFGG Nodes

This context defines the language used while replacing the retired LFGG
custom-node pack.

## Language

**Legacy node**:
A node from the retired `lfgg_nodes` pack, used as reference evidence rather
than as a compatibility contract.
_Avoid_: Old node, original node

**Successor node**:
A newly designed node that replaces useful legacy behavior under a corrected,
explicit public contract.
_Avoid_: Remade node, rewritten node

**Sizing successor**:
A successor node that computes pixel width and height under a sizing policy
without resizing an image or creating a latent.
_Avoid_: Latent sizing node

**Resize successor**:
A successor node that resamples an image to dimensions selected by a sizing
policy without enlarging either source axis.
_Avoid_: Upscaler, sizing successor

**Ratio preview**:
A visual representation of the requested width-to-height proportion, independent
of the aligned dimensions produced during execution.
_Avoid_: Dimension preview, output preview

**Crop frame**:
A movable, resizable region over a source image whose fixed aspect ratio defines
the pixels retained in the cropped image.
_Avoid_: Ratio box, selection box

**Crop ratio**:
The width-to-height proportion enforced by a crop frame, expressed as two
positive components and independent of the cropped image's pixel dimensions.
_Avoid_: Output size, crop dimensions

**Cropped image**:
The contiguous whole-pixel region retained from a source image by a crop frame,
without resizing or resampling.
_Avoid_: Resized image, fitted image

**Latent initializer**:
A ComfyUI node that creates an empty latent in the format required by a model
family. Sizing successors leave this job to native ComfyUI nodes.
_Avoid_: Generic latent output

**Successor pack**:
The MIT-licensed public Comfy Registry package `lfgg-nodes`, published by
`lfelipegg` and displayed as `LFGG Nodes`, that contains accepted successor
nodes. Only newly written or provenance-cleared code belongs in it.
_Avoid_: New pack, modernized legacy pack
