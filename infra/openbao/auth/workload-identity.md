# OpenBao Workload Identity Contract

## Security invariant

No long-lived broker secret is stored in Git, container images, CI variables, prompts, dashboards or application configuration.

## Authentication flow

1. Runtime obtains a short-lived OIDC/JWT workload identity from the platform identity provider.
2. OpenBao validates issuer, audience, subject and environment claims.
3. Role binding maps workload identity to the minimum policy required for that environment.
4. OpenBao issues short-lived credentials with bounded TTL and no renewal beyond the configured maximum.
5. Application receives only the credential class needed for the current operation.
6. PROD identities and TESTNET identities are separate principals with separate roles, policies and secret paths.

## Mandatory claims

- `sub`: immutable workload identity
- `aud`: exact OpenBao audience
- `environment`: `PAPER`, `TESTNET` or `PROD`
- `service`: approved service identity
- `repository`: expected repository provenance
- `ref`: approved deployment ref

## Fail-closed rules

- Missing or unverifiable identity -> deny.
- Environment mismatch -> deny.
- Requested role broader than mapped workload -> deny.
- Expired token -> deny.
- PROD token presented to TESTNET role or vice versa -> deny.
- Withdrawal-capable credentials -> forbidden for trading runtime.

Actual issuer URLs, role IDs, secret names and credentials must be injected outside Git and are intentionally absent from this repository.
