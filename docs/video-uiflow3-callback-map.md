# Video UIFLOW3 Callback And Navigation Map

## Existing Owners

| Prefix | Owner |
| --- | --- |
| `vproduct|` | `handle_video_product_callback` |
| `vprofile|` | `handle_video_profile_studio_callback` |
| `vtrend|` | `handle_video_trend2_callback` |
| `vstory|` | `handle_storyboard2_callback` |
| `videoidea|` | `handle_video_idea_callback` / dynamic idea owner |
| `framevideo|` | Frame callback owners |
| `longvideo|` | `handle_long_video_callback` |

`videoedit|` remains exclusively owned by Video Edit and is excluded.

## V3 Namespace

V3 reserves one short owner prefix: `vid3|`. Existing prefixes are not removed.
Safe legacy entry callbacks may redirect to the same V3 adapter, but no callback
is shared by two handlers.

`videoidea|` remains the read-only idea catalog owner and the standalone
`video_idea` public route still enters at `videoidea|start`. A V3 Content Hub
uses its own scoped `vid3|idea_catalog` launcher first. That launcher records
the exact draft, parent product, user, owning chat and return step, then renders
the existing catalog without changing a catalog record. Catalog navigation
continues to use its existing owner; `videoidea|continue` accepts the selected
candidate into that same V3 draft at `content_lock`. It cannot create a second
draft, switch product, call a provider, create a job or mutate a wallet.

Every V3 callback must validate:

1. current user and owning-chat identity;
2. the short draft-and-visible-state token embedded in every non-entry/non-resume V3 button;
3. exact parent product;
4. action relevance for the current visible step;
5. exact action arity before callback claim or mutation;
6. duplicate callback idempotency;
7. zero provider/job/wallet side effects.

Leaving V3 through another callback or slash command clears only an active
pending text/media intake and increments `ui_revision`. The canonical draft,
current logical step and non-input child editor are preserved for Resume, while
every button on the screen that was left becomes stale and cannot mutate the
draft from another menu.

## Deterministic Navigation

- Forward navigation pushes only visible steps.
- AUTO/SKIP/UNSUPPORTED steps never enter the visible stack.
- Back pops exactly one visible step and preserves all inputs.
- Summary edit sets `return_to=summary`; Save/Cancel trim the nested editor
  history and return to Summary.
- Summary exposes only its explicit editor allowlist. Forged targets cannot
  enter Source or another unrelated canonical step.
- Format edits from Summary return directly to Summary. A ratio revision updates
  every existing scene; a duration revision preserves scene IDs/data and asks
  the user to reconfirm scene count before reopening Scene Plan.
- Prompt reconciliation is an explicit Summary action; there is no dirty-state
  dead end with no visible way to clear it.
- Summary `Luu ke hoach` may persist a planning-only approved snapshot. When
  any renderer/capability blocker remains it stays on Summary and keeps
  `commercial_tail_ready=false`; saving never implies a job or charge.
- Summary has no legacy restart action. Every visible editor stays inside the
  same draft and returns to this one hub.
- Resume renders `navigation.current_step`, not Menu Video.
- Menu Video and `/video` expose the unscoped Resume action only while a valid
  V3 draft exists; the no-draft menu remains unchanged.
- Unknown/stale actions fail closed by re-rendering the current step.
- Back from a catalog opened by V3 returns to the same draft's Content Hub.
  A selected idea returns to that draft's Content Lock; the standalone Idea
  menu and legacy parent handoff keep their existing behavior.
- A token from an older screen in the same draft also fails closed after any
  navigation or state change; it cannot target a replacement entity.
- Any non-`vid3|` callback or slash command invalidates all buttons from the V3
  screen being left. `vid3|resume` is the only unscoped continuation action.
- Opening a child view clears the prior view's active character/location/scene
  context before installing the new owner context.
- Resume drops a child view or pending input whose owner step, draft, user,
  private chat, entity or scene no longer matches the canonical state; stale
  text/media cannot mutate another editor.
- Resume also drops a child view whose required character, location, product,
  prop or scene owner is missing or no longer exists, while preserving the
  exact canonical parent step.
- Owner-filtered reference galleries return to that exact character, location
  or compact actor editor. The unfiltered gallery can map an existing source
  asset to a stable owner without re-upload. Prompt Advanced returns to its
  scene or scene list.
- Scene Plan exposes a provider-free, non-destructive rule draft. Approve is
  absent until every scene has an idea, one main action and a completion state.
- The dialogue editor lists lines owned by the active scene and removes a line
  only when both `scene_id` and stable `dialogue_id` match.
- Long video follows `series_goal -> format -> content_hub -> content_lock ->
  production_bible -> episode -> scene_count`. `episode_identity` and
  `episode_content` own only Episode pending input and always return to Episode.
- `episode_entities` is a compact child of Episode. Its character, location,
  product and prop toggles accept only existing Series Bible IDs. Episode
  continuity toggles are also local overrides, while `episode_inherit` clears
  both override maps to inherit current Series defaults again. Back returns to
  Episode; Back from Scene Count also returns to Episode with locked content
  and explicit empty overrides preserved.
- A child editor cannot change `parent_product` or cross into another flow.
- Home is explicit; Back never silently becomes Home.

The existing `VIDEO_STEP_BACK_MATRIX` remains a legacy comparator. V3 does not
use its incidental history fallback.

Admin route, callback and Back audits derive each V3 product's first step,
visible child callbacks and initial Back target from the provider-free rendered
entry screen. They do not apply `VIDEO_STEP_BACK_MATRIX` to a `vid3|` route.

## Required Route Tests

For all seven creation adapters: entry, forward, back, AUTO/SKIP back, resume,
Summary edit return, stale callback, duplicate callback and legacy alias.
`Ý tưởng video` remains the independent read-only catalog at `videoidea|start`;
the V3 parent launcher/return contract is tested separately.
Tests also assert callback length <= 64 bytes and one registered owner per prefix.
