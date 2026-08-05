# Persist dual video-selection representations

`LFGG_VideoCutter` accepts `video`, `selection_mode`, `start_time`, `end_time`,
`first_frame`, and `last_frame`, in that order, and returns one `video`. Although
only the active mode's pair defines the segment, both numeric pairs remain in
the persisted workflow contract so they stay normally connectable and the node
remains usable without its frontend extension; the player, playhead, range
slider, thumbnail filmstrip, and loop preference are UI state only.
