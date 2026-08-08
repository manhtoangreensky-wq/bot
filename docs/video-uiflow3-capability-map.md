# Video UIFLOW3 Capability Map

This task stores provider-neutral planning contracts. It does not change a
renderer, worker or provider. A public control is enabled only when the current
runtime contract proves it is consumed.

| Canonical feature | UI/state in V3 | Current execution truth | Public policy |
| --- | --- | --- | --- |
| Read-only Idea catalog reuse | parent-bound Content Hub launcher and candidate return | existing `videoidea|` catalog remains its own owner | Preserve the exact V3 draft/user/chat; write only a content candidate and keep all catalog/provider/job/wallet side effects at zero |
| Multiple characters | planned | singular Scene3 character today | Editor enabled for planning; submit readiness reports renderer gap |
| Character/location/product references | planned | current assets mostly flat | Role editor enabled; preserve legacy-unassigned assets and map existing source intake by identity without re-upload |
| Scene cast/location | planned | current scene plan lacks durable entity IDs | Editor enabled; block approved snapshot if required mapping is incomplete |
| Dialogue speaker mapping | planned | current dubbing is one global stream | Editor enabled; validate every speaker ID |
| Distinct voice per character | two female + two male planning slots, plus custom | current Product Video uses one final voice | Ask/retain character gender first, show only that gender's unused slots, reject cross-cast reuse, clear a stale voice when gender changes, and require verified materialization + `multi_voice_render` before commercial submit |
| Whole-video music | planned | current global music exists | Show the music launcher only when this/per-scene music is supported or an old unsupported plan must be cleared; enable this choice only when current product capability exposes music mix |
| Per-scene music | planned | renderer accepts one global BGM | Store plan; hide the choice and per-scene launcher until `per_scene_music` is true |
| SFX/ambient by scene | capability-gated editor + plan | global/partial planning only | Hide editor unless the matching scene capability is true; still capability-gate final claim |
| Continuity locks | planned | prompt continuity exists | Enable planning without provider calls |
| Scene camera/movement/light | compact per-scene planning editor | partial legacy prompt fields | Persist for later compiler; no provider or render claim |
| Series/Episode inheritance | planning contract with stable entity/voice IDs | current renderer has no canonical Episode handoff | Derive Series defaults -> Episode character/location/product/prop/continuity overrides -> Scene overrides; one reset restores inheritance and execution stays locked |
| Logo/watermark | existing | current tail/frame paths support product-specific branding | Reuse existing editor/capability truth |
| Frame renderer | existing | dedicated Local Worker/FFmpeg family | Preserve; never route through Product Video |
| Long-video execution | existing lock | `PUBLIC_ENABLED=False` | Summary may save the approved planning snapshot, but `commercial_tail_ready=false` and submit remains blocked |

Browser SpeechSynthesis voices are not backend-renderable evidence. A voice may
be offered for final MP4 only when it has a stable server voice ID and a proven
audio materialization path. Same-gender characters must never silently share a
voice ID.

A renderer-only gap does not corrupt an otherwise valid provider-neutral plan.
Summary can save that plan with the exact gaps in `render_blockers`, but cannot
mark the commercial tail ready until the list is empty.

Required final comparator: runtime/engine, Video Edit, SubDub, Music/Suno,
PayOS/wallet and database schema diffs must all be empty.
