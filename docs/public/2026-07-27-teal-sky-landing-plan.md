# TOAN AAS Public Landing — Implementation Plan

1. Add a static red contract for the public visual/system boundaries.
   It must fail on the current jade/emoji landing before production markup is
   changed.
2. Rebuild `index.html` as one self-contained, safely served landing while
   retaining only the existing `/lead` client payload and valid download/legal
   links that still have a matching route.
3. Add the reviewed `vi`, `en` and `zh` public-copy catalogue with query-string
   locale selection only; no browser account storage or identity inference.
4. Run targeted static contracts, a syntax/route smoke and visual checks at
   desktop and phone widths.  Do not start bot polling, providers, PayOS or
   Telegram live actions.
5. Review the final diff for accidental `bot.py`, pricing/payment or webhook
   edits.  Commit, push, open one landing-only PR, wait for its required check,
   then merge only after it is clean.
