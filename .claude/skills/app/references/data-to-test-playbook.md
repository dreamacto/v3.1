# Data-to-test playbook

Use this reference when converting manifest fields, recovered source, captured traffic, roles, and
workflow/device observations into concrete, bounded tests. Keep client, owned backend, platform, and
third-party services separate. Testing remains low-rate and read-only by default; device-based checks
stop at approval gates.

## Start from recovered facts

For every candidate test, record this chain in `review_ledger.csv` or a linked note:

`source -> extracted fact -> hypothesis -> payload family -> expected secure behavior -> observation -> disposition`

Useful sources include AndroidManifest fields (permissions, exported components, intent-filters,
allowBackup, debuggable, networkSecurityConfig), Info.plist entries, recovered java source, request
wrappers and signing code, constants and config files (assets, shared_prefs defaults), storage keys,
SDK declarations, captured traffic, webview URLs, deeplink handlers, and role-specific screens.

## Decode and triage before dynamic testing

Use local/offline decoding first:

- Package/manifest: recover package name, version, signing clues, component declarations, permission
  lists, scheme/universal-link declarations, and cleartext/NSC configuration.
- Recovered source: recover API base URLs, request wrappers, signing/nonce logic, storage keys, feature
  flags, and environment selectors.
- Traffic export or Burp history: recover hosts, paths, methods, auth hints, object IDs, roles, content
  types, and state-changing endpoints (structure only, no sensitive values).
- Device observations (operator-supplied cache/backup/material): recover shared_prefs/db/plist artifacts,
  snapshot clues, and update/download paths.
- Webview URLs and deeplinks: separate browser-origin behavior from native behavior.

Record successful and failed decoding attempts in `artifacts/decoding-ledger.csv`.

## Convert data shapes into test ideas

| Recovered data | Test direction | Safe default |
|---|---|---|
| `userId`, `uid`, `memberId`, `tenantId`, `orgId` | Object and tenant authorization, predictable IDs | Compare only authorized test users/tenants; do not touch real third-party data |
| Exported activity/receiver/provider without permission protection | IPC boundary, intent-triggered behavior | Static inventory first; actually firing write components is approval-gated |
| Custom scheme / universal link carrying IDs or tokens | Deep-link parameter trust and sensitive-param exposure | Open own/test links only; never launch third-party records |
| `allowBackup=true`, debuggable, cleartext permitted | Local exposure and transport posture (signal, not finding) | Record as signal; impact needs device/backup evidence |
| Token/session in shared_prefs, db, or keychain | Token persistence and logout cleanup | Use operator-supplied material; never copy token values into artifacts |
| Hardcoded AK/SK, jpush/umeng/map keys | Secret candidate triage by reachability and privilege | `secret_candidate` red line: no validity probing, no requests |
| Nonce/timestamp/signature code paths | Replay window, canonicalization, binding scope | Offline hypothesis + observation only; never auto-replay |
| Carrier one-click-login token, device-id, Android ID/IDFA/IDFV | Credential discipline, binding basis | Treat as credentials; never into reports/ledgers/handoffs |
| WebView allowlist domains, JS bridge methods | Origin boundary and bridge capability exposure | Offline inventory; no cookie/token injection or replay |
| Order, coupon, points, entitlement state | Business state-transition and replay logic | Sandbox or disposable test data only |
| Upload/download/preview keys | File authorization and storage boundaries | Operator-provided or disposable files only |
| Push/analytics/map/payment SDK endpoints | Third-party boundary attribution | Classify against hosts.csv; do not actively test unless in scope |

## Build a compact role and object matrix

For each recovered endpoint, component, cloud function, page, or webview workflow, identify:

- Actors: anonymous launch, own test user, second test user, low-privilege role, privileged role when
  supplied; designated test device as a separate dimension (rooted/jailbroken only after approval).
- Objects: own object, second test user's object, nonexistent object, public object, expired or
  completed object.
- Tenant or organization: own tenant, second authorized tenant when supplied, invalid tenant.
- Client route and backend endpoint: route parameters, request wrapper defaults, state-changing flags,
  component/deeplink entry points.
- Expected secure behavior: allow, deny, same-user only, same-tenant only, one-time only, server-side
  validation.

Only run the cells needed to prove or reject a hypothesis. Mark unavailable cells as `blocked` or
`approval_required` with the exact missing account, role, device, backend scope, sandbox, or approval.

## Choose payload families by context

Select the payload family from the recovered parameter type, request context, role, workflow state, and
server behavior:

- Authorization: ID substitution, role comparison, tenant boundary, hidden page or function call,
  method override.
- Session/auth: replay of stale token metadata, logout invalidation, timestamp/nonce handling,
  signature mismatch (offline hypotheses only; never auto-replay any request).
- Input handling: type confusion, length boundary, delimiter/encoding edge, benign syntax probe,
  reflected marker.
- File handling: filename normalization, extension/MIME mismatch, preview/download authorization, size
  boundary.
- Business logic: duplicate submit, sequence skip, coupon/points/price mismatch, order/refund entitlement.
- Webview/bridge: origin checks, deep-link trust, postMessage/native bridge exposure, URL parameter trust.
- IPC/component: exported-component reachability, permission enforcement, deeplink parameter trust
  (static inventory first; live triggering of write components is approval-gated).
- Cloud/storage: function permission boundary, storage object ACL, environment separation.
- Transport: cleartext presence, pinning posture, certificate-error handling — observation only; any
  bypass is approval-gated and is a test technique, not a finding.

Do not send a generic payload list blindly. Prefer paired positive and negative controls: a useful
control (own-object success + foreign-object expected denial) is worth more than a larger payload set.

## Canary discipline

- Canary values (markers, harmless callbacks, synthetic records) are used only where ROE-class rules
  allow and only with operator approval for anything state-changing or outbound.
- A canary must be inert: no credential material, no real user data, no side effects beyond the
  disposable test object.
- Record every canary value, where it was placed, and where it was observed, so cleanup is verifiable.
- Never use production users, real orders, or third-party records as canaries.

## Keep testing bounded

- Configure low concurrency, delays (same-host serial, ≥2s interval), short queues, response-size
  limits, and backoff (429/5xx → 10s; 5 consecutive errors → stop that host) before automation.
- Keep automated runs read-only unless a named write or state change has explicit operator approval.
- Stop after minimum proof. Do not export bulk data, retain sensitive identifiers, or keep unnecessary
  responses.
- Redact or summarize cookies, tokens, one-click tokens, device IDs, phone numbers, order details,
  messages, and business records in prompts, ledgers, screenshots, and reports.
- If a test would create, modify, delete, upload, transact, execute code, change account/session/device
  state, or affect a real user, record it as `approval_required` until the operator approves the exact
  action and cleanup plan.

## Record dispositions

Use these outcomes consistently:

- `rejected`: the boundary behaved securely or the candidate was a false positive.
- `needs_manual_validation`: evidence is incomplete but the branch is safe to continue later.
- `approval_required`: the next step is state-changing, sensitive, high-volume, or out of current scope.
- `confirmed`: the finding has minimal, redacted evidence and demonstrated impact.
- `accepted_risk`, `fixed`, `retest_failed`, `retest_passed`: use only after operator or retest evidence supports it.
