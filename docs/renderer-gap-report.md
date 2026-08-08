# Video UIFLOW3 Renderer Gap Report

UIFLOW3 prepares a canonical plan only. This report is a handoff for the later
RouteEngine task; it does not authorize renderer or worker changes.

| Canonical field | UI implemented | State persisted | Current renderer consumes V3 | Current worker consumes V3 | Public-safe now | Blocking gap |
| --- | --- | --- | --- | --- | --- | --- |
| `characters[]` | Yes | Yes | No | No | Planning only | Product renderer still relies on singular/legacy character state |
| Narrator | Yes | Yes | No | No | Planning only | No V3 narrator/voice adapter |
| Product/prop entities | Yes | Yes | No | No | Planning only | No V3 object-constraint adapter |
| `locations[]` | Yes | Yes | No | No | Planning only | No V3 location adapter |
| Reference owner/role | Yes, including source-intake reuse | Yes | No | No | Planning only | Existing execution mostly consumes flat references; V3 mapping does not duplicate or re-upload the source asset |
| Scene cast IDs | Yes | Yes | No | No | Planning only | Scene executor has no V3 cast contract |
| Scene location ID | Yes | Yes | No | No | Planning only | Scene executor has no V3 location contract |
| Scene narrator/product/prop IDs | Yes | Yes | No | No | Planning only | Scene executor has no V3 optional-actor contract |
| Scene framing/movement/light/mood | Yes | Yes | Partial legacy prompt fields | No direct V3 contract | Planning only | Prompt compiler must consume the compact V3 direction fields |
| Series/Episode/effective Episode | Yes | Yes | No canonical V3 handoff | No | Planning only | Renderer must consume locked Episode Content plus character/location/product/prop/continuity overrides through Series -> Episode -> Scene inheritance without drifting stable IDs |
| Dialogue speaker ID | Yes | Yes | No | No | Planning only | Current dubbing path is global, not per-speaker/per-scene |
| Voice cast | Yes | Yes | No | No | No final claim | Requires verified server-renderable, distinct voice inventory and materialization |
| Whole-video music | Capability-gated | Yes | Legacy global path only | Legacy path only | Only after an adapter proves consumption | V3 snapshot is not wired to the existing mixer |
| Per-scene music | Capability-gated | Yes | No | No | No | Renderer currently accepts one global BGM |
| Scene SFX | Contract only | Yes | No | No | Hidden | No scene SFX consumer |
| Scene ambient | Contract only | Yes | No | No | Hidden | No scene ambient consumer |
| Continuity locks | Yes | Yes | Partial legacy prompt use | No direct V3 contract | Planning only | Prompt compiler must consume stable V3 entities/locks |
| First/last frame | Source assets only | Yes | Product-specific legacy paths | Product-specific paths | Product-specific only | No shared V3 frame-role adapter |
| Logo/watermark | Yes | Yes | Product-specific legacy paths | Product-specific paths | Only through proven product tail | V3 branding handoff is not connected |
| Frame render family | Preserved | Yes | Existing Frame renderer | Existing local worker | Existing path only | Must not be routed through Product Video |
| Long-video submit | Planning only | Yes; Summary can save a snapshot | Existing public lock | Existing queue lock | No | Saved snapshot is not handed to execution; keep submit disabled until the runtime lock changes independently |

## Release Rule

An approved V3 snapshot may be handed to RouteEngine only after each required
row has a tested adapter. Until then, Summary reports a friendly missing
capability and no provider call, job, outbox entry, charge or fake success is
created.
