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

**Source video**:
A standard ComfyUI `VIDEO` value supplied to a node for temporal selection.
_Avoid_: Input file, video path

**Video cutter**:
A successor node that visually selects and returns one video segment from a
standard ComfyUI source video. Stable ID: `LFGG_VideoCutter`.
_Avoid_: Video editor, file trimmer

**Video segment**:
A standard ComfyUI `VIDEO` value restricted to one contiguous interval of a
source video, with source audio restricted to the same interval when present.
_Avoid_: Cut file, saved clip

**Selection mode**:
The active representation, either time or frames, of one video segment's
boundaries; changing it does not change the selected interval.
_Avoid_: Cut type, trim method

**Frame index**:
The zero-based position of a frame in a source video; the first frame has index
`0`.
_Avoid_: Frame number

**Frame range**:
A contiguous, inclusive pair of first and last frame indexes that defines a
video segment.
_Avoid_: Frame slice, frame count

**Time range**:
A start-inclusive, end-exclusive interval, measured in seconds, that defines a
video segment.
_Avoid_: Duration range, timestamp pair

**Frame-aligned time**:
A time value snapped to the nearest interval of `1 ÷ reported FPS`, keeping
time and frame selections on the same nominal frame boundaries.
_Avoid_: Millisecond precision, arbitrary timestamp

**Timecode**:
The `HH:MM:SS.mmm` display form used to read and edit a frame-aligned time.
_Avoid_: Timestamp, duration string

**Nominal frame boundary**:
A boundary derived from reported FPS; it identifies an exact frame boundary for
constant-frame-rate video but only an approximation for variable-frame-rate video.
_Avoid_: Exact timestamp

**Source end**:
The open-ended boundary that resolves to a source video's final time or final
frame; persisted manual values represent it as `-1`.
_Avoid_: Unlimited duration, maximum timestamp

**Connected boundary**:
A segment boundary supplied by another workflow node rather than edited locally;
its selector handle is read-only once connected.
_Avoid_: Dynamic range, locked value

**Valid selection**:
A selection within video bounds that contains at least one frame.
_Avoid_: Empty segment, clamped range

**Video bounds**:
The duration, reported FPS, and nominal frame count that constrain a source
video's selectable range.
_Avoid_: Video properties, file metadata

**Playhead**:
The current position in a source-video preview, used to inspect the video and
set either boundary of a video segment.
_Avoid_: Cursor, slider handle

**Thumbnail filmstrip**:
A bounded set of sampled source-video frames shown across the selector to give
visual context for its timeline.
_Avoid_: Contact sheet, extracted frames

**Preview source**:
A browser-playable representation of a source video used only by the visual
editor; it is not the video segment returned to the workflow, and its absence
does not invalidate that segment.
_Avoid_: Output video, saved segment

**Selection playback**:
Preview playback constrained to the selected interval, looping by default while
leaving unrestricted source scrubbing available.
_Avoid_: Segment output, render preview

**Latent initializer**:
A ComfyUI node that creates an empty latent in the format required by a model
family. Sizing successors leave this job to native ComfyUI nodes.
_Avoid_: Generic latent output

**Successor pack**:
The MIT-licensed public Comfy Registry package `lfgg-nodes`, published by
`lfelipegg` and displayed as `LFGG Nodes`, that contains accepted successor
nodes. Only newly written or provenance-cleared code belongs in it.
_Avoid_: New pack, modernized legacy pack
