# Smart Context Translation

The confirmed Smart subtitle preparation scopes its detected source language
through the existing ContextVar while translating. Each cue temporarily supplies
up to two preceding/following original cues, bounded to3000 characters. The scope
is restored after success/failure and at preparation return. Parallel jobs cannot
share this context. No shared function signature or default request changes.

DeepL requests for this scope include `context` and a supported known `source_lang`.
Unknown language stays automatic. `text` remains the exact cue, so the provider
does not translate context into the cue or change cue identity/timestamps. This
uses the same configured single provider and same per-cue request count, no retry.
Non-Smart DeepL calls retain the original request body.

Primary API reference: https://developers.deepl.com/api-reference/translate/request-translation
Context influences interpretation without being translated; it is not billed as
text. Request correctness is verified offline, not a claim that every provider
translation or song lyric becomes semantically perfect.
