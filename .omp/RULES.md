# LFGG Non-Negotiables

- Never treat `reference/custom-nodes/` as project source; verify provenance before reuse.
- Never use runtime package installation, monkey-patching, `eval`, `exec`, or obfuscation.
- Preserve persisted workflow contracts and tensor batch, device, dtype, and latent metadata invariants.
- Obtain explicit user approval before destructive actions, public workflow contract or registration-ID changes, compatibility-floor changes, release, or publication.
- The primary agent owns integration and final verification; never claim an unrun check passed.
- Always ask user questions through OMP's `ask` UI, including clarification, approvals, and skill-driven interviews; never use chat-only question lists. Group independent questions and mark recommended options.
