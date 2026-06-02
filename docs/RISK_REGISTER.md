# Risk Register

| Risk | Severity | Probability | Current Mitigation | Next Action |
| --- | --- | --- | --- | --- |
| SQLite data loss on Railway without persistent volume | High | Medium | Local SQLite file exists; docs now warn about volume risk. | Configure Railway Volume or add tested `DB_FILE` ENV support. |
| PayOS webhook bypass or incorrect credit if checksum logic is wrong | Critical | Low | Signature verification and duplicate order table exist. | Test real paid, wrong signature, wrong amount, duplicate, expired. |
| Monolithic `bot.py` crash from syntax error | High | Medium | `py_compile` and pytest are required after edits. | Extract config and DB gradually. |
| No automated backup | High | Medium | Manual awareness only. | Add backup plan before scaling. |
| No production health alert | Medium | Medium | `/runtime` exists and `/health` is now local-only. | Add external monitor/admin alert after deployment verifies route. |
| AI API quota/key failure | Medium | High | Gemini/OpenAI fallback exists. | Add admin quota alerts and clear user messages. |
| RemoveBG/Cutout failure | Medium | Medium | Fallback pattern exists. | Test paid-first/fallback-second and refund behavior. |
| Deepgram failure | Medium | Medium | Deepgram key/path exists. | Verify refund behavior on real audio error. |
| Social platform ban from spam/auto-publish | High | Medium | Auto-publish should remain approval-gated. | Keep manual review and platform-specific posting limits. |
| Deepfake or AI likeness risk | High | Medium | Current plan bans impersonation and non-consensual likeness. | Add policy checks to Video Factory prompts. |
| API key leakage through screenshots/logs | Critical | Medium | ENV-driven secrets and no deliberate key logging. | Rotate any exposed keys and avoid screenshots with visible values. |
| Worker overload on video requests | Medium | Medium | Operator tasks exist, not full worker automation. | Add queue limits before real video rendering. |
| Missing audit log for admin actions | Medium | Medium | Credit events exist for money movement. | Add audit log foundation in a later approved task. |
| Missing approval for dangerous actions | High | Medium | Admin commands exist; auto-publish not approved. | Keep approve gate for publish, paid API calls, and external actions. |
