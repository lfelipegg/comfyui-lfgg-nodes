# Use a virtual routing organizer

`LFGG_RoutingOrganizer` is a virtual node with persisted, labeled input/output
channel pairs because its purpose is workflow layout rather than execution. A
minimal V1 definition supplies its package, display name, category, and help
metadata; frontend behavior supplies the dynamic channels and keeps the node
out of prompt execution. This preserves the current ComfyUI and frontend floors
and native reroute-style typing and deletion bypass without introducing V3;
conversion inside groups or subgraphs is deliberately unsupported because the
supported frontend special-cases only native reroutes there.
