# PayOS Signature Troubleshooting

## Correct create-payment signature data

```text
amount=<amount>&cancelUrl=<cancelUrl>&description=<description>&orderCode=<orderCode>&returnUrl=<returnUrl>
```

Example:

```text
amount=10000&cancelUrl=https://bot-production-2dd7.up.railway.app/landing&description=DAAS10K&orderCode=178039665&returnUrl=https://bot-production-2dd7.up.railway.app/landing
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
