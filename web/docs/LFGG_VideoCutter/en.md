# LFGG Video Cutter

Connect a standard ComfyUI `VIDEO`, then select one contiguous segment in
`Time` or `Frames` mode. Time boundaries are start-inclusive and end-exclusive;
frame indexes are zero-based and inclusive. `-1` selects the source end.

The compact editor shows the native player, the active time/frame boundary
pair, and a summary with explicit endpoint conventions. **Edit selection**
opens the filmstrip, playhead, separate Start/End sliders, nominal
previous/next-frame buttons, Set Start/End buttons, and selection looping.
**Hide selection controls** leaves the segment unchanged.

With focus in the editor, use Space to play or pause, Left/Right to step, and
I/O to set the active boundaries. Native buttons, media controls, and text
fields keep their normal keys. Connected boundaries remain discoverable and
read-only; disconnecting restores saved local values.

Ten thumbnails are captured only while the editor is open and the node is
not collapsed. Completed captures are reused. The strict-Boolean workflow
property `lfgg_editor_expanded` remembers only the open/closed view; it adds no
executable input. Toggling does not reload metadata or change selection values.

Changing modes preserves the same interval. Constant-frame-rate selections are
exact; variable-frame-rate selections use the source's reported FPS as a
nominal grid. The backend keeps primary video and audio synchronized through
native `VideoInput.as_trimmed`; auxiliary tracks are not retained by native
trim encoding.

Before execution, a directly connected native `LoadVideo` (including simple
reroutes) uses ComfyUI's input `/view` endpoint and the confined
`POST /lfgg/v1/video-metadata` endpoint for AVI, MOV/M4V/MP4, MKV, or WebM.
After execution, the direct source remains available for full scrubbing and
the backend's returned boundaries control selection playback. Computed videos
receive a temp MP4 preview only when the selection is at most 30 seconds, 900
nominal frames, and 1920×1080. Preview failure does not invalidate the `VIDEO`
output. Without the frontend extension, the same six standard inputs remain
executable.
