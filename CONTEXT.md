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

**Ratio preview**:
A visual representation of the requested width-to-height proportion, independent
of the aligned dimensions produced during execution.
_Avoid_: Dimension preview, output preview

**Latent initializer**:
A ComfyUI node that creates an empty latent in the format required by a model
family. Sizing successors leave this job to native ComfyUI nodes.
_Avoid_: Generic latent output

**Successor pack**:
The MIT-licensed public Comfy Registry package `lfgg-nodes`, published by
`lfelipegg` and displayed as `LFGG Nodes`, that contains accepted successor
nodes. Only newly written or provenance-cleared code belongs in it.
_Avoid_: New pack, modernized legacy pack
