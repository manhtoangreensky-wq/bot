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
- `series`: stable series ID, series-wide goal and revision for `multi_scene_film`
- `episode`: stable episode ID, number/title, separately locked episode content,
  entity overrides and continuity overrides
- `needs`: REQUIRED/AUTO/OPTIONAL/SKIP/UNSUPPORTED decisions
- `bible`: characters, narrator, products, locations, props, relationships and continuity;
  character/location totals carry explicit confirmation flags, including an intentional zero
- `references`: role-mapped assets with stable owner IDs
- `scenes`: stable scene IDs and per-scene assignments
- `audio`: dialogue speakers, voice cast, music scope, SFX and ambient plans
- `branding`: logo/watermark planning state
- `capabilities`: truthful public control availability
- `navigation`: current step, visible-step stack, completed steps, return target and dirty sections
- `ui_revision`: monotonic visible-session revision used only to invalidate buttons
  after the user leaves UIFLOW3 for another menu or command
- `id_counters`: last allocated source/reference/entity/scene/dialogue ordinals;
  deleted IDs are never assigned to a later object in the same draft
- `legacy_compat`: original owner/state references without destructive migration

Long-video planning keeps the series-wide Content Lock and Production Bible as
defaults. The active episode then supplies its own locked content and optional
character/location/product/prop or continuity overrides. `effective_episode` is
derived when planning or snapshotting; it is not a second mutable source of
truth. An absent override inherits the Series Bible, while an explicit empty
override intentionally selects no entity of that kind for the episode.
`reset_episode_overrides` clears both override maps and derives the latest
Series defaults again; it does not recreate entities or change stable IDs.

Opening the read-only Idea catalog from Content Hub adds a transient
`video_idea_parent_handoff` in Telegram session data. It binds the V3 draft ID,
parent product, owner user, owner chat and return step. The catalog itself is
not copied into V3 state. Accepting a candidate writes only `content.source`,
`content.idea_id`, profile, intent and approved brief, then returns to
`content_lock` with the existing draft and zero execution/billing side effects.

The long-video order is deterministic:
`series_goal -> format -> content_hub -> content_lock -> production_bible ->
episode -> scene_count -> scene_plan`. Scene planning uses the locked Episode
Content, not the broader series goal. Series character IDs and voice IDs remain
stable when an episode title, content or override changes.

Format revisions are non-destructive after Content Lock. Ratio changes update
the ratio copied into every existing scene and invalidate Prompt/Summary.
Duration changes keep stable scene IDs and user-entered scene data, clear only
`scene_count_confirmed`, and invalidate the dependent scene/dialogue/prompt
sections until the user reconciles the count.

Music scope, whole-video music, per-scene music and continuity changes invalidate
Prompt/Summary consistently. Per-scene music is stored in `audio.music_plan`
and mirrored by the scene's `music_policy`, so later adapters do not need to
guess which record is authoritative.

Frame source images and detected Storyboard panels are rejected before they can
exceed the product's maximum scene count. Existing files are preserved; V3 never
silently clamps source units and leaves one without a representable scene.
After Content Lock, an existing `source.assets[]` row can be mapped into
`references[]` by stable source ID. The raw source row, Telegram file ID and
fingerprint remain unchanged, while the reference records its entity owner,
role, optional scene scope and `source=source_intake`; no re-upload is required.

`planning_readiness_errors` contains only defects that make the canonical plan
invalid. Renderer-only gaps remain in `readiness_errors` and are copied to the
snapshot's `render_blockers`. Summary may therefore persist a valid
`legacy_compat.approved_snapshot`, while every remaining render blocker keeps
`legacy_compat.commercial_tail_ready=false`. Saving that provider-neutral plan
does not create or authorize a job, provider call, outbox row, wallet mutation
or charge.

Summary renders a bounded content preview and at most twelve translated
readiness labels, followed by the count of remaining checks. The message stays
inside Telegram's 4,096-character limit without hiding that more work remains.

## Stable IDs

Project-scoped IDs use `char_01`, `loc_01`, `prod_01`, `prop_01`, `scene_01`,
`dlg_01` and `asset_01`. Display order and names may change without changing
relationships.

Telegram shows `NV1`, `NV2`, and so on for compact input and scene assignment.
Those ordinals are display selectors only: they resolve to the character ID at
the time of the valid input, while relationships persist the stable ID. A
deleted `char_02` is therefore never confused with a later visible `NV2` whose
durable ID is `char_03`.

Character/location count reduction and scene reduction keep retained objects in
the user's current order. Later expansion allocates fresh ordinals instead of
reusing removed IDs. Combined with a visible-state callback token, an old
Telegram button cannot silently target a replacement entity or scene.

Scene planning records `planning_source`, `planning_confidence` and
`locked_by_user`. The provider-free rule draft fills only blank semantic/action/
completion fields. It never overwrites user text, and each following scene's
`start_state` is linked to the previous scene's `completion_state` after draft,
manual edit or reorder.

## Legacy Mapping

- Singular character -> `characters[0]`.
- Singular voice -> narrator/default cast only when old semantics prove owner.
- Singular music -> `music_scope=whole_video`.
- Flat image -> `owner_type=legacy_unassigned`; never guess an owner.
- Existing Review data -> V3 Summary sections.
- Existing profile/idea -> `content.profile_id` / `content.idea_id`.

Legacy state remains readable and legacy callbacks remain aliases. V3 never
deletes uploaded assets when an upstream section becomes dirty.
