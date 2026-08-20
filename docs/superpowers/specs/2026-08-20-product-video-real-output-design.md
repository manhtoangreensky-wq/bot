# Product Video Real Output Design

## Goal

Complete the locked Video AI Realistic Product Video path for one and multiple
scenes. A confirmed request must keep the user's approved Add-on choices, use
one durable request and one durable internal job, render a real MP4, validate
the artifact, deliver it to Telegram, persist a delivery receipt, and only then
be eligible for charging.

## Scope

This work owns only these surfaces:

- Video AI Realistic shared-tail state preservation for a two-scene flow.
- Subtitle, dubbing, music, SFX, text, logo, watermark, and transition handoff
  from the approved Add-on state into the Product Video render manifest.
- Product Video public quality names, public price ordering, and unit economics.
- Promotion of the same preflight Job ID into dispatch after admission passes.
- Product Video one-scene and multi-scene execution, MP4 validation, Telegram
  delivery, receipt persistence, and post-delivery charge eligibility.
- Status/debug evidence for request ID, job ID, provider task ID, artifact,
  delivery receipt, and charge count.

All other Video product UI flows, Video Edit, Frame Video, SubDub, Music/Suno,
PayOS, wallet policy, credentials, database schema, and unrelated menus are
protected.

## Public Flow Contract

The existing Video AI Realistic UI remains in its approved order. The audited
two-scene path is:

```text
approved two-scene plan
-> Add-on
-> Review
-> Quality
-> Invoice
-> Confirmation
-> Status
-> real MP4 delivery
```

Logo and watermark remain optional. A user can add either item, choose one of
nine positions, save it, and return to Add-on. Moving through logo, watermark,
text, or transitions must not erase any earlier Add-on choice.

## State Ownership

The UI draft ID is the stable owner of Add-on choices. The approved snapshot
hash is a content revision, not a new Add-on session. When branding or scene
transitions change the snapshot hash within the same draft:

- preserve `audio_config`, `addon_config`, automatic text, logo, and watermark;
- rebuild scene content and prompt-derived fields from the latest snapshot;
- invalidate downstream review, quality, invoice, and confirmation state;
- never restore the original empty audio snapshot over explicit user choices.

When dubbing uses subtitle content, it inherits the subtitle target language.
Changing the subtitle language later updates the inherited dubbing language
unless the user explicitly chose a different dubbing language.

## Add-on Materialization

The worker must never silently ignore a selected Add-on.

- Subtitle: build and burn a valid subtitle artifact from approved scene text.
- Dubbing: use the existing canonical TTS/dubbing adapter and produce a real
  audio artifact before composition.
- Music: resolve the selected stock asset to a stable asset identity and local
  file before composition. AI music remains outside this Product Video task.
- SFX: resolve the selected stock asset to a stable asset identity and local
  file before composition.
- Logo: download the saved Telegram image and overlay it at the saved position.
- Watermark: burn the saved text at the saved position.
- Text overlays and transitions: carry the approved scene-level values into the
  render manifest and compositor.

Tests use local fixture assets and make zero external provider calls. At
runtime, a selected Add-on whose required artifact cannot be materialized is a
preflight blocker with no provider submit and no charge.

## Quality Catalog

Internal tier IDs and provider route keys remain stable. Public rows are sorted
by `unit_xu` ascending, with a deterministic tier-ID tie breaker.

Owner-locked public identities:

- 80 Xu per scene: `Nhanh gon` (public Vietnamese copy: `Nhanh gọn`).
- 200 Xu per scene: `Can bang ro net` (public Vietnamese copy:
  `Cân bằng rõ nét`).

Every other public package keeps a name that describes its existing model
characteristics. Invoice, confirmation, guide, and button labels all consume
the same canonical catalog. No screen may sort by internal tier ID.

Unit economics reports both:

- expected route cost from the first eligible provider; and
- conservative fallback cost from the most expensive eligible provider.

Revenue uses 100 VND per Xu and includes the existing multi-scene discount.
PASS requires positive gross profit at the maximum published discount for the
80-Xu and 200-Xu packages, before separately priced Add-ons.

## One Request And One Job

Confirmation already creates a durable public request and internal preflight
job before provider checks. Admission must promote that exact Job ID:

```text
precheck_running
-> precheck_blocked | ready_to_submit
-> queued
-> processing
-> completed | failed_no_charge
```

The promotion transaction validates the authoritative admission snapshot,
updates the existing job and project, creates scene rows, and creates one
dispatch outbox record. It must not insert a replacement job. Repeated confirm
or promotion callbacks return the same request ID and Job ID and cannot create
duplicate provider submissions.

## Render And Delivery Contract

One scene uses the canonical one-scene Product Video route. Two scenes use the
canonical per-scene route and ordered compositor. Both routes must:

1. persist provider intent before submission;
2. save every provider task ID;
3. poll only accepted task identities;
4. validate each scene clip;
5. compose all required scenes in order;
6. apply every selected Add-on;
7. probe and decode the final MP4;
8. send the actual MP4 to Telegram;
9. persist message ID, Telegram file ID, artifact hash, bytes, duration, and
   stream metadata as the delivery receipt;
10. expose charge eligibility only after the receipt is durable.

An absent or invalid artifact, missing scene, missing requested Add-on, failed
delivery, uncertain delivery, or missing receipt ends in a no-charge state.

## Safety And Gates

- Default-off feature flags stay default-off in code.
- Tests use mocks/local fixtures and assert provider calls and wallet mutations
  are zero.
- No credentials or environment variables are changed by implementation.
- Only `selfless-abundance / production / bot` may be deployed.
- Deployment and ENV changes require a separate current Owner approval.
- The first paid provider submission requires a separate current Owner approval
  immediately before the call.
- No wallet mutation is authorized by this design. Live proof must use the
  Owner/admin no-charge path unless the Owner separately approves a charge.

## Verification

Targeted tests must prove:

- two-scene Add-on state survives logo, watermark, and transition callbacks;
- dubbing inherits subtitle language;
- stock music and SFX have stable asset identities or block before submit;
- quality rows are price-sorted and have the locked 80/200 names everywhere;
- unit economics uses provider evidence and remains profitable under the
  maximum scene discount;
- admission promotes the existing Job ID and creates exactly one outbox;
- one-scene and two-scene local-fixture renders produce decodable MP4 files;
- selected subtitle, dubbing, music, SFX, logo, watermark, and transition
  effects are present in the final render manifest/artifact;
- invalid output or failed delivery leaves charge count at zero;
- request, job, provider task, artifact, delivery, receipt, and charge evidence
  agree across status/debug surfaces.

Live proof, after all Owner gates, must include the exact runtime SHA, request
ID, Job ID, provider task IDs, two-scene coverage, MP4 probe, Telegram message
ID/file ID, receipt ID, and charge count.

## Explicit Non-Goals

- Redesigning any locked Video UI.
- Changing another Video product flow.
- Rewriting the provider router or renderer from scratch.
- Enabling automatic provider retry or fallback.
- Calling AI Music/Suno for background music.
- Changing wallet, refund, discount, PayOS, or top-up policy.
- Creating another Railway project, service, or volume.
