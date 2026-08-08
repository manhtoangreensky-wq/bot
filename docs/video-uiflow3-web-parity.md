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
| `needs` | `REQUIRED/AUTO/OPTIONAL/SKIP/UNSUPPORTED` per module |
| `bible` | Characters, narrator, products, locations, props, relationships and continuity |
| `references` | Asset role plus stable owner type/ID; never a flat unowned upload |
| `scenes` | Ordered semantic plan, cast, location, dialogue IDs and continuity links |
| `audio` | Dialogue speakers, voice cast, whole/per-scene music, SFX and ambient plans |
| `branding` | Optional logo/watermark metadata |
| `capabilities` | Runtime truth controlling whether a final control is enabled |
| `navigation` | Current step, visible history, completed/dirty sections and Summary return |

## Display Contract

- Ask for content before character or scene configuration.
- Character editor is grouped: total count, then gender, description, image and
  voice per stable character.
- Scene editor is grouped: cast, location, dialogue/speaker, voice owner and
  available audio.
- Unassigned scenes use deterministic round-robin order; never hidden random.
- Music scope is `none`, `whole_video` or `per_scene`.
- One Summary shows content, format, Bible, references, scenes, dialogue,
  voices, audio, continuity and branding.

## Capability Semantics

Every optional final control has `supported`, `planned` and `hidden_reason`.
Web may display a read-only planned value, but it must not enable a render claim
when `supported=false`. Browser SpeechSynthesis is not proof of a backend voice.
No provider, worker, job, wallet or billing call is permitted from this planning
contract.
