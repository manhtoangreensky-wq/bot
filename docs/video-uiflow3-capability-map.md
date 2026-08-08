# Video UIFLOW3 Capability Map

This task stores provider-neutral planning contracts. It does not change a
renderer, worker or provider. A public control is enabled only when the current
runtime contract proves it is consumed.

| Canonical feature | UI/state in V3 | Current execution truth | Public policy |
| --- | --- | --- | --- |
| Multiple characters | planned | singular Scene3 character today | Editor enabled for planning; submit readiness reports renderer gap |
| Character/location/product references | planned | current assets mostly flat | Role editor enabled; preserve legacy-unassigned assets |
| Scene cast/location | planned | current scene plan lacks durable entity IDs | Editor enabled; block approved snapshot if required mapping is incomplete |
| Dialogue speaker mapping | planned | current dubbing is one global stream | Editor enabled; validate every speaker ID |
| Distinct voice per character | planned | current Product Video uses one final voice | Hide/disable final-render claim; require `multi_voice_render` before commercial submit |
| Whole-video music | planned | current global music exists | Enable only when current product capability exposes music mix |
| Per-scene music | planned | renderer accepts one global BGM | Store plan; require `per_scene_music` before commercial submit |
| SFX/ambient by scene | planned | global/partial planning only | Store plan; capability-gate final claim |
| Continuity locks | planned | prompt continuity exists | Enable planning without provider calls |
| Logo/watermark | existing | current tail/frame paths support product-specific branding | Reuse existing editor/capability truth |
| Frame renderer | existing | dedicated Local Worker/FFmpeg family | Preserve; never route through Product Video |
| Long-video execution | existing lock | `PUBLIC_ENABLED=False` | Planning may be visible; submit remains blocked |

Browser SpeechSynthesis voices are not backend-renderable evidence. A voice may
be offered for final MP4 only when it has a stable server voice ID and a proven
audio materialization path. Same-gender characters must never silently share a
voice ID.

Required final comparator: runtime/engine, Video Edit, SubDub, Music/Suno,
PayOS/wallet and database schema diffs must all be empty.
