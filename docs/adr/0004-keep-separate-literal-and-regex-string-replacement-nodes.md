# Keep separate literal and regex string-replacement nodes

`LFGG_StringReplace` keeps literal replacement obvious and compact, while
`LFGG_StringReplaceRegex` exposes explicit literal or regular-expression mode
and capture-group replacement. We retain both public contracts rather than one
configurable node so regex behavior is opt-in at node selection; expressions
are locally authored and text sizes are bounded because Python's standard
regular-expression engine has no portable timeout.
