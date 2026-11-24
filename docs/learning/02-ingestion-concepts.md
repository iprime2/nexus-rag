# Phase 2: Ingestion Concepts

One section per step. Each has the concepts, how the code works, what breaks if it is done wrong, exercises, and interview questions.

---

## Step 2.1: Tenant authentication with API keys

### Why authentication comes before ingestion
Every document belongs to a tenant. If the tenant came from the request (`X-Tenant-ID: acme`), anyone could upload to, or later read, any tenant's data by changing one header. **The tenant must come from a credential the server verifies** (ADR-0008, layer 1). Users and logins (JWT) arrive in Phase 5; machine API keys are enough to enforce the rule now.

### How it works
| Piece | File | Role |
|---|---|---|
| Key format + hashing | `app/auth/api_keys.py` | `nxr_` + 256 random bits; store only SHA-256; parse `Authorization: ApiKey <key>` |
| `api_keys` table | `app/db/models/api_key.py`, migration | `key_hash` UNIQUE (also the lookup index); `revoked_at`; cascade delete with the tenant |
| Service | `app/auth/service.py` | create tenant, issue / revoke / look up keys. No HTTP, no commits. |
| Dependency | `app/api/dependencies/auth.py` | header → key → tenant → `TenantContext`; binds `tenant_id` into the logs |
| `TenantContext` | `app/core/tenancy.py` | The only way tenant-scoped code learns the tenant |
| CLI | `app/cli.py` | `create-tenant`, `create-api-key` (shown once), `revoke-api-key` |

Request flow: `Authorization` header → format check (no DB hit for garbage) → `SHA-256` → one indexed lookup joined with `tenants` → 401 / 403 / `TenantContext`.

### Key decisions
| Decision | Why |
|---|---|
| Store only `SHA-256(key)` | A database leak doesn't leak usable keys (tested: the key never appears in the row) |
| SHA-256, not argon2/bcrypt | Slow hashes protect *guessable* passwords. 256 random bits can't be guessed, and a fast hash keeps every request cheap. |
| One identical 401 for missing, malformed, unknown and revoked keys | Callers can't probe which keys exist |
| 403 only for a suspended tenant | The key is valid, so telling its holder why is safe |
| `nxr_` prefix | Secret scanners and humans recognise a leaked key |
| Format check before the DB lookup | Junk requests cost nothing |
| Keys shown once, revocable, never recoverable | Standard practice (GitHub, Stripe, AWS) |
| `NestJS` comparison | The dependency is a `Guard` + a custom `@CurrentTenant()` param decorator in one |

### What breaks if done wrong
| Mistake | Consequence | Test |
|---|---|---|
| Tenant from a header or body | Cross-tenant data access by editing a request | design rule; `test_each_key_only_sees_its_own_tenant` |
| Storing plaintext keys | DB leak = every client compromised | `test_only_the_hash_is_stored` |
| Different errors for unknown vs revoked keys | Key enumeration | `test_missing_malformed_or_unknown_keys_get_the_same_401` |
| No revocation | A leaked key works forever | `test_revoked_key_is_rejected` |
| Logging the header | Keys in log storage | real-server check: 0 occurrences |

A test-infrastructure lesson: adding a foreign key to `tenants` broke the test cleanup (`TRUNCATE tenants` is refused while another table references it). Cleanup now truncates every model table in one statement.

### Exercises
1. Create a tenant and key with the CLI, call `/v1/me` with `curl`, revoke the key, and call it again.
2. In `/docs`, click **Authorize**, paste `ApiKey <your key>`, and try `/v1/me`.

### Interview questions
- **"How do you store API keys?"** Hash them (a fast hash is fine for high-entropy keys), show the plaintext once, keep a non-secret prefix for display, support revocation and rotation.
- **"How do you enforce multi-tenancy in an API?"** Derive the tenant from the credential, pass a tenant context explicitly into every data access, and enforce it again in the database (composite foreign keys, possibly row-level security).
