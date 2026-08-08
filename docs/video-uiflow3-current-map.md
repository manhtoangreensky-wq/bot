# Video UIFLOW3 Current Flow Map

Base: `origin/main` at `0cec502a6abe302e4cf5eb2f3abf1265261277c1`.

Scope is seven creation entries plus the unchanged read-only Video Idea catalog.
Video Edit, SubDub, RouteEngine, workers, pricing, wallet and provider execution
are outside this task.

## Public Entries

| Product | Current owner | Current first meaningful input | Current planning path | UIFLOW3 insertion |
| --- | --- | --- | --- | --- |
| Video theo trend | `vtrend` + Product Video | Trend source | Trend -> scene count -> ratio -> content | Keep trend source, then enter Content Hub |
| Video AI chan that | `vproduct` + `vprofile` | Prompt/image/video mode | Scene count -> ratio -> source -> character | Keep source mode, then Content Hub before characters/scenes |
| Kich ban -> Video | `vproduct` + `vprofile` | Script text | Scene count -> ratio -> content -> character | Preserve script, lock content, extract Bible, then scenes |
| Ghep anh thanh video | `framevideo` | Uploaded images | Images -> duration -> motion/audio | Preserve Frame renderer; add content/classification after raw upload |
| Video tu quay | `vproduct|ss2/ss3` | Source video/segment | Local analysis -> subject -> content | Reuse source analysis, then canonical Content Lock/Bible |
| Storyboard | `vstory` | Generate/upload mode | Count/panels -> ratio -> content | Preserve raw panels; move semantic scene approval after Content Lock/Bible |
| Video dai tap | `longvideo` | Internal series input | Separate long planning flow | Planning only; preserve public execution lock |
| Y tuong video | `videoidea` | Idea catalog | Existing read-only catalog/handoff | Keep standalone `videoidea|start` and every catalog owner unchanged; V3 uses a parent-bound launcher/return and never edits catalog internals |

## Existing Good Components To Reuse

- `services/video_profile_catalog.py`: canonical 32-content catalog.
- `services/video_idea_catalog.py` and `services/video_idea_handoff.py`: idea data and parent ownership.
- `services/video_scene3_flow.py`: provider-free planning metadata and existing editors.
- `services/video_storyboard2.py`: storyboard panel and asset ownership.
- `services/video_selfshotflow4.py`: self-shot local analysis/content contracts.
- `services/frame_video_flow.py`: separate Frame render-family UI contract.
- `services/video_tail9.py`: commercial tail and one shared Summary direction.
- `services/video_uifreeze1.py`: frozen public menu, packages and long-video lock.

## Confirmed Gaps

1. Character state is singular (`character_config`), so multiple people cannot
   retain stable identity, references or distinct voices.
2. Scene3 references are a flat asset list. They do not carry a durable
   character/location/product owner.
3. Voice and music are global post-production entries. Scene speaker and
   per-scene music ownership are absent.
4. Scene count is requested before content in several creation flows.
5. Navigation mixes static matrices and incidental history fallback. This can
   return to a sibling or stale screen after AUTO/SKIP steps.
6. Review and Summary concepts overlap across Scene3, Storyboard, Self-shot and
   `video_tail9`.

## Target Order

`entry/source -> format target -> Content Hub -> Content Lock -> Production
Bible -> references/continuity -> scene proposal -> scene assignment ->
dialogue/voice/audio -> prompt preview -> branding -> one Summary -> existing
commercial tail`.

Raw source media may be collected before Content Lock. Character, location and
semantic scene decisions may not be requested before Content Lock.
