# Use a virtual routing organizer

`LFGG_RoutingOrganizer` is a frontend-only virtual node with persisted, labeled
input/output channel pairs because its purpose is workflow layout rather than
execution. This preserves the current ComfyUI and frontend floors and native
reroute-style typing and deletion bypass without introducing a V3 backend
contract; conversion inside groups or subgraphs is deliberately unsupported
because the supported frontend special-cases only native reroutes there.
