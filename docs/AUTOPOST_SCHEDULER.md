# AutoPost Scheduler & Queue Recovery

- **Timezone**: Stored in UTC, presented in user timezone.
- **Idempotency Key**: `sha256(content_id:platform:channel:schedule_slot)[:16]`.
- **States**: `QUEUED` -> `PREPARING` -> `READY` -> `PUBLISHING` -> `PUBLISHED`.
- **Failures**: `AUTH_BLOCKED`, `POLICY_BLOCKED`, `RETRY_WAIT`, `FAILED_FINAL`.
