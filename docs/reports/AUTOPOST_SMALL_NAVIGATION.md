# AutoPost small navigation fixes — source/test handoff

Scope: embedded AutoPost callback only. No producer changes, no general router refactor and no large AutoPost pipeline work.

- Back from topic/channel/brand entry releases only the corresponding pending flag.
- Returning to AutoPost hub clears those three AutoPost input flags.
- Entering a new supported input mode releases the previous AutoPost prompt.
- Current draft and unrelated job state are preserved.
- Unsupported edit/rewrite/logo/affiliate actions answer with an alert without replacing the current screen or keyboard. This fixes misleading hub fallback only, not the missing feature implementations.

Verification: 3 switching-input failures demonstrated before fix; 20 focused callback/navigation tests passed after correction; compilation and diff check passed. AST comparison confirms no top-level function outside the embedded AutoPost string changed.

An initial patch with generic guide context landed in Video Edit and failed compilation. That insertion was removed before any commit/deploy; final scope is only AutoPost. Future patches must use unique handler context.

Pending: global Home, stale message ownership, functional caption editing, other unimplemented features and runtime/manual verification. No deploy or real Telegram actions performed.

## Follow-up: caption editing and menu exit

Caption editing now uses explicit preview/Save/Cancel, owner and current draft message binding, original draft fingerprint, and a rotating preview token. Old preview buttons cannot save a newer candidate; cancelled/expired sessions cannot overwrite the draft. Plain-text user caption is HTML-escaped for the existing renderer. No publisher/provider/DB calls.

Actual AutoPost callback and message entry delegate to the editor. Menu/start entry clears only AutoPost input flags and edit state, retaining draft and unrelated jobs. Tests compare the entire original menu/start AST body after the two added cleanup statements, against immutable e99226ff.

Previous verification: combined callback/navigation suite 27 passed; added expired-Save-after-exit test, exit suite 3 passed. Final focused run recorded separately before commit.

Still incomplete: rewrite/logo/affiliate remain explicitly unavailable; session edit state is not durable after restart; product-specific old callbacks outside common menu may require additional session isolation. No deployment or real Telegram acceptance. This is not whole-bot closure.

## Cross-chat callback fix

Two failing tests showed that a repeated message ID in another chat could open the editor and another chat could supply caption text. Binding now includes chat ID at draft delivery and redisplay; open, text, save and cancel check the bound chat alongside owner/session token. Missing callback message fails closed. Existing drafts without chat binding need a newly displayed draft.

After fix: editor + exit suites 10 passed (21.60s), py_compile and diff check passed. The runtime seam adds one chat-ID assignment beside the existing draft message-ID assignment. No producer, provider, wallet or publication behavior changed.
