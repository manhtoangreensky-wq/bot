# Video UIFLOW3 State Map

## Current Owners

| State | Owner | Important existing fields |
| --- | --- | --- |
| Scene3 | `context.user_data[VIDEO_PROFILE_STUDIO_SESSION_KEY]` | `step`, `history`, `content_source`, `character_config`, `reference_assets`, `scene_plan`, `postproduction_addons` |
| Storyboard | nested `storyboard2` | `screen`, `history`, `scene_count`, `content`, `scenes`, panel images, transitions |
| Self-shot | product session draft | source segment, local analysis, subject locks, selected content, prompt and tail |
| Frame | Frame session state | ordered images, durations, transition, motion, global music/voice, branding |
| Commercial tail | `video_tail9` | approved content snapshot, branding, Summary, package, invoice, confirmation, status |

## Canonical V3 State

V3 is session state only; it does not require a database migration.

- `flow_schema_version`, `draft_id`, `parent_product`, `entry_mode`, `render_family`
- `source`: raw assets and source metadata
- `format`: ratio, target duration and scene-count policy
- `content`: source, profile/idea, original intent, approved brief, revision and lock
- `needs`: REQUIRED/AUTO/OPTIONAL/SKIP/UNSUPPORTED decisions
- `bible`: characters, narrator, products, locations, props, relationships and continuity
- `references`: role-mapped assets with stable owner IDs
- `scenes`: stable scene IDs and per-scene assignments
- `audio`: dialogue speakers, voice cast, music scope, SFX and ambient plans
- `branding`: logo/watermark planning state
- `capabilities`: truthful public control availability
- `navigation`: current step, visible-step stack, completed steps, return target and dirty sections
- `legacy_compat`: original owner/state references without destructive migration

## Stable IDs

Project-scoped IDs use `char_01`, `loc_01`, `prod_01`, `prop_01`, `scene_01`,
`dlg_01` and `asset_01`. Display order and names may change without changing
relationships.

## Legacy Mapping

- Singular character -> `characters[0]`.
- Singular voice -> narrator/default cast only when old semantics prove owner.
- Singular music -> `music_scope=whole_video`.
- Flat image -> `owner_type=legacy_unassigned`; never guess an owner.
- Existing Review data -> V3 Summary sections.
- Existing profile/idea -> `content.profile_id` / `content.idea_id`.

Legacy state remains readable and legacy callbacks remain aliases. V3 never
deletes uploaded assets when an upstream section becomes dirty.
