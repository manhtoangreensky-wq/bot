# Video UIFLOW3 Web Parity

Telegram is the first client, but Web must consume the same provider-neutral
state. Do not create a second Web-only schema.

## Canonical Identity

- Schema: `flow_schema_version=3`
- Draft owner: `draft_id`, authenticated user/session and `parent_product`
- Stable entities: `char_01`, `loc_01`, `prod_01`, `prop_01`, `scene_01`,
  `dlg_01`, `asset_01`
- Catalog IDs: reuse exact `services.video_profile_catalog.PROFILE_SEEDS`
- Idea catalog: read-only dependency owned by `videoidea|`; a selected idea is
  input to a parent product, never a separate render or checkout state

## Shared Visible Steps

`entry`, `source`, `format`, `content_hub`, `content_lock`,
`production_bible`, `references`, `continuity`, `scene_count`, `scene_plan`,
`scene_assignment`, `prompts`, `branding`, `summary`, then the existing
commercial `package`, `invoice`, `confirmation`, `status` tail.

Web navigation must use `navigation.current_step`, `visible_step_stack` and
`return_to`. Back restores the previous visible step and input state. Summary
edit returns directly to Summary.

## Shared State Sections

| Section | Required Web representation |
| --- | --- |
| `source` | Ordered raw assets, fingerprints, source metadata and completion |
| `format` | Ratio, target duration, scene-count policy and confirmed count |
| `content` | Source, exact profile/idea ID, original intent, approved brief, revision and lock |
| `series` | Stable series ID, series-wide goal and revision |
| `episode` | Stable episode ID, number/title, locked episode content and entity/continuity overrides |
| `effective_episode` | Derived Series defaults plus Episode overrides; read-only projection for planning/snapshot |
| `needs` | `REQUIRED/AUTO/OPTIONAL/SKIP/UNSUPPORTED` per module |
| `bible` | Characters, explicit count confirmations, narrator, products, locations, props, relationships and continuity |
| `references` | Asset role plus stable owner type/ID for character, location, product and prop; never a flat unowned upload |
| `scenes` | Ordered semantic plan, planning source/confidence/user lock, cast, narrator, product/prop IDs, location, dialogue IDs, music/SFX/ambient and continuity links |
| `audio` | Dialogue speakers, voice cast, whole/per-scene music, SFX and ambient plans |
| `branding` | Optional logo/watermark metadata |
| `capabilities` | Runtime truth controlling whether a final control is enabled |
| `navigation` | Current step, visible history, completed/dirty sections and Summary return |
| `ui_revision` | Invalidate controls from a screen left for another menu while preserving Resume |

## Display Contract

- Ask for content before character or scene configuration.
- Opening Idea Catalog from Content Hub must retain the exact draft, parent
  product and owner session. Back returns to that Content Hub; accepting one
  candidate sets `content.source=idea_catalog` and opens Content Lock without
  mutating the catalog or creating provider/job/payment state.
- Long video asks for the Series goal first, locks the Series content and Bible,
  then asks for the active Episode identity/content before Scene Count. Web Back
  from Scene Count must restore Episode, not Production Bible or a generic menu.
- Episode controls are compact toggles over stable character, location, product
  and prop IDs plus the four continuity flags. An omitted override inherits
  Series defaults; an explicit empty selection means none for that episode.
  One reset action clears both override maps to inherit current Series defaults
  again. Scene-specific choices remain the final override.
- Character editor is grouped: total count, then gender, description, image and
  voice per stable character.
- Compact labels such as `NV1` resolve to the current visible character and
  persist its stable ID; Web must not store the display ordinal as identity.
- Same-gender casts can select distinct planning slots; those slots are not
  backend-renderable evidence until a later runtime adapter proves them. Only
  slots matching the character's selected gender are shown.
- Scene editor is grouped: cast, location, dialogue/speaker, voice owner and
  available audio; optional narrator/product/prop assignments stay in one
  collapsed actor editor.
- Existing dialogue lines remain visible inside their scene editor and use
  scene-owned deletion; another scene can never delete them by ID alone.
- Scene Plan may fill missing fields with the same provider-free rule outline,
  but must preserve user fields and link the next `start_state` to the previous
  `completion_state`. Approve stays unavailable while any required field is blank.
- Scene Advanced is a real compact framing/movement/lighting/mood editor and
  returns to the exact scene or Advanced scene list that opened it.
- Reference galleries filter by owner and return to that owner's editor.
- A source asset uploaded before Content Lock remains immutable intake data.
  The References editor may add an owner/role mapping using the same file ID and
  fingerprint; Web must not require the user to upload that asset again.
- Public copy uses `NV1`/`BC1` plus names and friendly reference-role labels;
  stable entity/asset IDs and Telegram file IDs remain internal state only.
- Unassigned scenes use deterministic round-robin order; never hidden random.
- Music scope is `none`, `whole_video` or `per_scene`.
- Music and continuity revisions invalidate compiled prompts and Summary; Web
  must mirror the same dependency behavior and per-scene `music_policy` value.
- A music launcher is absent when neither whole-video nor per-scene music is a
  proven capability. The sole exception is an existing unsupported plan, where
  the launcher remains available so the user can select `none` and recover.
- One Summary shows content, format, Bible, references, scenes, dialogue,
  voices, audio, continuity and branding.
- Summary content/readiness copy is bounded for Telegram and should use the
  same preview/remainder semantics on Web. Format and Prompt are explicit
  Summary editors, and only the published editor allowlist may be opened.

## Capability Semantics

Every optional final control has `supported`, `planned` and `hidden_reason`.
Web may display a read-only planned value, but it must not enable a render claim
when `supported=false`. Browser SpeechSynthesis is not proof of a backend voice.
Web must distinguish planning defects from render blockers. It may save the
same approved snapshot when `planning_readiness_errors` is empty, must preserve
all renderer-only gaps in `render_blockers`, and must keep
`commercial_tail_ready=false` while any blocker remains.
No provider, worker, job, wallet or billing call is permitted from this planning
contract.
