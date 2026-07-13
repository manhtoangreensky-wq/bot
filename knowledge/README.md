# TOAN AAS Knowledge Catalog

`knowledge/` is the canonical home for new reusable knowledge.

## Layout

- `catalog.json`: one index for canonical and legacy stores.
- `video/`: reusable video production patterns and workflows.
- `profiles/`: deterministic profile-router inputs.
- `references/`: source-reference classification without creator identity or branding.
- `toan_aas_cskh_aichat_context.md`: existing shared context retained in place.

## Legacy Stores

The following existing stores remain at their current paths because runtime loaders already depend on them:

- `config/video_prompt_vault/`
- `data/prompt_vault/`
- `data/prompt_library/`
- `docs/prompt_vault/`
- `config/cskh_knowledge_base.json`
- `docs/knowledge/`

They are listed in `catalog.json` so the full inventory is visible from this directory. Do not move a legacy store until all of its loaders have been migrated and regression-tested.

## Adding Knowledge

1. Put new video patterns under `knowledge/video/`.
2. Put profile-router records under `knowledge/profiles/`.
3. Add source classifications to `knowledge/references/`.
4. Update `catalog.json` when a new store is introduced.
5. Run `profile_router.validate_knowledge_catalog()` and the KNOWLEDGE1 tests.

Knowledge records must contain reusable production patterns only. Do not store source branding, creator identity, private faces, logos, or proprietary wording.
