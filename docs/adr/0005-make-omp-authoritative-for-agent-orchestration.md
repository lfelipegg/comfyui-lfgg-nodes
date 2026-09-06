# Make OMP authoritative for agent orchestration

OMP is the primary agent runtime, using its bundled agents, project settings, and role aliases instead of project-specific copies of built-in roles. Root `AGENTS.md` remains the portable policy source, while three lean Codex profiles preserve secondary compatibility. This trades exact cross-runtime parity for one OMP-native orchestration model with less duplicated policy and fewer mandatory handoffs.
