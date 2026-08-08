# Video UIFLOW3 Renderer Gap Report

UIFLOW3 prepares a canonical plan only. This report is a handoff for the later
RouteEngine task; it does not authorize renderer or worker changes.

| Canonical field | UI implemented | State persisted | Current renderer consumes V3 | Current worker consumes V3 | Public-safe now | Blocking gap |
| --- | --- | --- | --- | --- | --- | --- |
| `characters[]` | Yes | Yes | No | No | Planning only | Product renderer still relies on singular/legacy character state |
| `locations[]` | Yes | Yes | No | No | Planning only | No V3 location adapter |
| Reference owner/role | Yes | Yes | No | No | Planning only | Existing execution mostly consumes flat references |
| Scene cast IDs | Yes | Yes | No | No | Planning only | Scene executor has no V3 cast contract |
| Scene location ID | Yes | Yes | No | No | Planning only | Scene executor has no V3 location contract |
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
| Long-video submit | Planning only | Yes | Existing public lock | Existing queue lock | No | Keep submit disabled until existing runtime lock changes independently |

## Release Rule

An approved V3 snapshot may be handed to RouteEngine only after each required
row has a tested adapter. Until then, Summary reports a friendly missing
capability and no provider call, job, outbox entry, charge or fake success is
created.
