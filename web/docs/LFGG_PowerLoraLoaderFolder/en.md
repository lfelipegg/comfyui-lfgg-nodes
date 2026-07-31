# LFGG Power LoRA Loader (Folder)

Connect `model` and `clip`, then use `folder` to limit future LoRA choices.
Parent folders include all descendants recursively, and `All LoRAs` shows the
complete catalog. Changing folders never removes or changes existing rows.

Choose a LoRA and click `Add LoRA`. Each row has an enabled toggle, separate
model and CLIP strengths, and a menu to move up, move down, or remove it.
Use the arrows around either strength for 0.05 adjustments, or click its value
for direct numeric entry. Click the filename to replace it from the current
folder choices. Toggle all is available above the rows.

One combined strength is shown by default and applies to both model and CLIP.
Enable `Separate Model and Clip strength` in the node settings to show and edit
the two strengths independently. The option is saved with the workflow.

Enabled rows run from top to bottom. A row is skipped when disabled or when
both strengths are zero. The outputs are the final `model` and `clip` after
every active row has been applied.

Refresh node definitions after adding or removing LoRA files. A missing saved
folder stays visible with no add choices, and existing rows remain unchanged.
A missing selected file fails execution with an actionable `LFGG` error.
