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

`videoidea|` remains the unchanged read-only idea catalog owner. The public
`video_idea` route and the Content Hub button still call `videoidea|start`
directly. V3 does not register, rewrite or mutate a catalog callback; any
selected-idea return continues through the existing `video_idea_handoff`
contract owned by that flow.

Every V3 callback must validate:

1. current user/session ownership;
2. exact parent product;
3. action relevance for the current visible step;
4. duplicate callback idempotency;
5. zero provider/job/wallet side effects.

## Deterministic Navigation

- Forward navigation pushes only visible steps.
- AUTO/SKIP/UNSUPPORTED steps never enter the visible stack.
- Back pops exactly one visible step and preserves all inputs.
- Summary edit sets `return_to=summary`; Save/Cancel both return to Summary.
- Resume renders `navigation.current_step`, not Menu Video.
- Unknown/stale actions fail closed by re-rendering the current step.
- A child editor cannot change `parent_product` or cross into another flow.
- Home is explicit; Back never silently becomes Home.

The existing `VIDEO_STEP_BACK_MATRIX` remains a legacy comparator. V3 does not
use its incidental history fallback.

## Required Route Tests

For all seven creation adapters: entry, forward, back, AUTO/SKIP back, resume,
Summary edit return, stale callback, duplicate callback and legacy alias.
`Ý tưởng video` remains the independent read-only catalog at `videoidea|start`.
Tests also assert callback length <= 64 bytes and one registered owner per prefix.
