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

---

## Step 2.2: Ingestion schema and the job state machine

### The tables
| Table | One row is… | Key rule enforced **by the database** |
|---|---|---|
| `ingestion_batches` | an upload session ("Q3 contracts") | belongs to one tenant |
| `documents` | the logical document ("Travel Policy") | `external_id` unique per tenant among live docs (partial unique index) |
| `document_versions` | one immutable upload of its bytes | same checksum can't be live twice in a tenant (dedupe) |
| `ingestion_jobs` | one processing run of a version | at most **one active job per version** (partial unique index) |
| `ingestion_job_events` | one state transition | append-only audit trail |

**Composite foreign keys** (`(tenant_id, document_id) → documents(tenant_id, id)`) make a cross-tenant link *impossible to store*: four tests try and the database refuses every one.

**Circular reference:** `documents.current_version_id → document_versions` and `document_versions.document_id → documents`. Neither table can be created first with both keys, so the migration creates both tables, then adds one key with `ALTER TABLE`. Alembic's autogenerate got this wrong (it put the key inside `CREATE TABLE`), which is why **generated migrations are always reviewed**.

**Gotcha:** `ON DELETE SET NULL` on a composite key would null `tenant_id` too, so the job→batch key has no delete action.

### The state machine (`app/ingestion/state.py`)
A pure dictionary `ALLOWED[current] → {next states}`, checked before any SQL. Unit tests verify properties of the whole graph (BFS reachability), not just a few examples:
- every state is reachable from `PENDING`;
- every state can reach a terminal state, so a job can never get stuck forever;
- no self-loops; terminal states have no exits (except a manual retry of `DEAD_LETTER`).

### Compare-and-set in one statement (`app/ingestion/jobs.py`)
```sql
WITH prev  AS (SELECT id, status FROM ingestion_jobs WHERE id = :id FOR UPDATE),
     moved AS (UPDATE ingestion_jobs j SET status = :target, …
               FROM prev WHERE j.id = prev.id
                 AND prev.status = ANY(:expected)      -- compare
                 AND j.attempt = :fence_attempt        -- fence (worker writes)
               RETURNING …, prev.status AS from_status)
INSERT INTO ingestion_job_events (…) SELECT … FROM moved   -- audit, same statement
RETURNING …;
```
| Part | Why |
|---|---|
| `FOR UPDATE` in `prev` | Concurrent callers queue up on the row; the loser re-reads the *new* status and matches nothing |
| `status = ANY(:expected)` | The compare in compare-and-set. Zero rows means someone else already moved the job. |
| `attempt = :fence_attempt` | Fencing token: a worker that lost its lease can't write anymore |
| Event insert in the same statement | The audit row exists if and only if the transition happened |
| Commit right after each transition | Row locks last milliseconds, never a whole task |

### Proving it, not claiming it
| Mutation (deliberately broken code) | Tests that failed |
|---|---|
| Removed the status check from the CAS | 7/9, including "10 concurrent claims → exactly one winner" |
| Removed the fencing check | exactly the stale-worker test |

Both mutations were reverted. This is mutation testing done by hand: if breaking the code doesn't break a test, the test isn't protecting anything.

### Security lint note
ruff's bandit rule S608 flags SQL built with f-strings. Here only fixed fragments from the same module are interpolated, and every *value* is a bound parameter, so the finding is suppressed with a reason. Never suppress it for anything derived from user input.

### Exercises
1. In `test_concurrent_claims_have_exactly_one_winner`, remove `FOR UPDATE` from the CTE and run it 20 times. Does it still pass? Why does the `UPDATE`'s own row lock still protect you, and what would break in the event log?
2. Draw the state graph from `ALLOWED` on paper. Find the path a job takes when the embedding provider is down for 10 minutes.

### Interview questions
- **"Two workers receive the same message. How do you make sure only one processes it?"** An atomic compare-and-set on the job's state in the database. The broker isn't trusted for exactly-once.
- **"What's a fencing token?"** A monotonically increasing number handed out with a lease. Every write must present it, so a worker whose lease expired (GC pause, network partition) can't clobber the new owner's work.
- **"Why enforce invariants with partial unique indexes instead of application checks?"** Under concurrency, check-then-insert races. The index makes the rule atomic and also protects against other writers (scripts, workers).

---

## Walking skeleton W1: text extraction and cleaning

### Why it matters
Every later stage (chunks, embeddings, retrieval, the LLM's answer) sees only this text. **Garbage in, garbage out.** A PDF stores *positioned glyphs*, not paragraphs, so extraction has to rebuild text and gets predictable things wrong.

| Raw artifact | Damage to RAG | Our fix |
|---|---|---|
| Repeated header/footer | Every chunk looks alike → retrieval can't discriminate | Owner's detector: normalized lines at page edges on ≥ 60% of pages |
| `informa-` ⏎ `tion` | Keyword search misses "information" | Re-join when the next line starts lowercase |
| `ﬁ` ligature, non-breaking spaces | Text doesn't match queries | Unicode NFKC normalization |
| Scanned page (no text) | Silent empty answers | Guard: `NO_TEXT_LAYER` (permanent error; OCR in H3) |
| One page in a PDF fails to parse | Losing the whole document | Log it and continue; the guard decides |

### Pure stages
`extract_pdf` / `extract_txt` → `clean_pages` → `guard_has_text`, composed in `extract_document`. File in, text out, no DB or network: 25 unit tests run in 0.2 s. Try it: `uv run python -m app.cli extract your.pdf`.

### Bugs the tests caught (the review lesson)
| Bug | Root cause | Lesson |
|---|---|---|
| Password-protected PDF reported as "corrupt" | Assumed `decrypt()` *raises* on a wrong password. It *returns* `NOT_DECRYPTED`. | Read the library's contract; don't assume |
| Real content deleted as boilerplate on short pages | "First 3 + last 3 lines" covered the whole page | Cap edges at half the page; ignore long lines |
| Tests failing on correct code | Test data varied only by numbers, which *is* a footer after normalization | Test data must look like real documents |

### Exercises
1. Run `extract` on a real PDF of yours. Which headers were removed? Anything wrongly removed?
2. Find a word that the hyphenation rule joins incorrectly. *(Hint: compound words.)*

### Interview questions
- **"How do you handle PDFs in a RAG pipeline?"** Per-page extraction (for citations), cleaning (boilerplate, hyphenation, Unicode), guards for scanned documents, OCR as a separate slow path, and evaluation-driven choice of extractor.
- **"Build or buy document parsing?"** Start simple and permissive-licensed behind an interface; evaluate heavier tools (Docling, Textract) against your own eval set; watch AGPL/GPL licenses for hosted services.
