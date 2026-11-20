# ADR-0008: Tenant isolation strategy

- **Status:** Accepted (2026-11-20)
- **Date:** 2026-11-20

## Context
Cross-tenant data exposure is the most serious possible failure. The spec asks for "tenant-specific document collections" and backend-enforced authorization. Assumption A-6: tens of tenants.

## Decision
Defense in depth, with no reliance on the LLM:
1. **Credential → tenant.** The tenant is never taken from request input.
2. **Postgres:** `tenant_id` on every tenant-owned table; **composite foreign keys** (`(tenant_id, parent_id)`) so cross-tenant references can't be stored; repositories require a `TenantContext`. Row-Level Security to be decided in Phase 5.
3. **Qdrant:** a **shared collection** per embedding model with a `tenant_id` keyword payload index marked as the tenant key. `VectorStore.search` requires a `TenantContext` and adds the filter itself.
4. **Hydration:** every retrieved chunk is re-checked in Postgres (tenant, `ACTIVE`, current version) before it can reach the prompt.
5. **API:** other tenants' resources return `404`, indistinguishable from non-existent ones.

"Tenant-specific collections" is interpreted as **logical** collections (filter-isolated), not physical ones.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| **Shared collection + mandatory tenant filter** | Scales to many tenants; one schema; Qdrant's recommended multitenancy pattern | Isolation depends on the filter always being applied (mitigated by layers 2–4) |
| Collection per tenant | Physical separation; easy per-tenant deletion | Per-collection memory overhead; operational overhead grows with tenant count; schema changes multiply |
| Hybrid (dedicated collections for large or regulated tenants) | Best of both | More complexity than needed now |
| Database per tenant (Postgres) | Strongest isolation | Migrations × N; connection pools × N |

## Consequences
- Security tests S1–S4 and S9 are mandatory before Phase 5 is complete.
- A tenant that contractually requires physical isolation could later get a dedicated collection behind the same `VectorStore` interface.
