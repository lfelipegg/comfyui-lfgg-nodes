# Use V1 lazy generic switches

`LFGG_BooleanSwitch` and `LFGG_IndexSwitch` use V1 wildcard switch branches,
frontend-propagated shared wire typing, and lazy evaluation so only the selected
branch executes. The index switch persists its bounded dynamic branch count and
resolved wire type; experimental V3 matching types are deferred to preserve the
pack's current compatibility floor and saved-workflow contract.
