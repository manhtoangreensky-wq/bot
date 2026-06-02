# PayOS Signature Troubleshooting

## Correct create-payment signature data

```text
amount=<amount>&cancelUrl=<cancelUrl>&description=<description>&orderCode=<orderCode>&returnUrl=<returnUrl>
```

Example:

```text
amount=10000&cancelUrl=https://bot-production-2dd7.up.railway.app/landing&description=AAS10K&orderCode=178039665&returnUrl=https://bot-production-2dd7.up.railway.app/landing
```

## Common mistakes

- Wrong field order.
- Using `orderCode` first.
- URL encoding values before signing.
- Using checksum key from a different PayOS channel.
- Extra whitespace in Railway Variables.
- Missing `cancelUrl` or `returnUrl`.
- Description too long or contains unsafe characters.

## Safe debug

- Do not log `PAYOS_CHECKSUM_KEY`.
- Do not log `PAYOS_API_KEY`.
- It is acceptable to log the signed data string because it does not contain secrets.

## After fix

Redeploy Railway and test `/naptien` again. If signature is still invalid, confirm `PAYOS_CLIENT_ID`, `PAYOS_API_KEY`, and `PAYOS_CHECKSUM_KEY` are from the same PayOS channel and have no leading/trailing spaces.

Admin can run `/payos_debug_create` before a real payment test to see the HTTP status, PayOS code/desc/message, and exact signature data string without exposing secrets.

`/payos_debug_create` tests multiple create-payment signature variants:

- `standard_sorted`: `amount,cancelUrl,description,orderCode,returnUrl`
- `faq_order`: `amount,orderCode,description,returnUrl,cancelUrl`
- `payload_order`: `orderCode,amount,description,cancelUrl,returnUrl`
- `sorted_all_payload_keys`: alphabetical payload keys excluding `signature`

If a variant creates a checkout URL, the bot stores that working variant for later PayOS create-payment requests. Admin can run `/payos_env_check` to confirm PayOS ENV variables are configured by length only; it never prints key values.
