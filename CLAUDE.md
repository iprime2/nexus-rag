# NexusRAG — Working Agreement for AI Coding Assistants

This file is read by Claude Code (and is the reference for Cursor / Codex sessions). It defines how to work on this repository.

## Purpose of the project
NexusRAG is a **learning project** and a portfolio piece for **AI engineering and Forward Deployed Engineer (FDE)** roles. The owner (TypeScript/NestJS background, intermediate Python) must be able to explain every design decision and important code path in an interview. **Understanding matters more than speed.**

## Teaching mode (always on)
Whenever you design, write or change code:
1. **Before coding:** explain the concept and why it is needed here. Mention alternatives and the trade-off. Where it helps, compare to the TypeScript/Node/NestJS equivalent.
2. **Keep changes small:** one focused component per step. Never several unrelated modules at once.
3. **After coding:** walk through the changed files and the important code paths (the "how it works" story, not a line-by-line recap).
4. **Failure thinking:** state what breaks if it is done wrong, and which test proves it isn't.
5. **Exercise:** give 1–2 small things the owner can try or modify to check understanding.
6. **Interview angle:** 1–3 questions an interviewer could ask about this piece, with short answer sketches.
7. Record durable notes in `docs/learning/` (one file per phase) so the learning outlives the chat.

**Communication style (owner preference):** keep answers brief. Prefer tables and short bullets over long prose. Put the depth in `docs/learning/`, not in chat.

When the owner asks a question, teach the underlying engineering concept, don't just hand over code. If the owner proposes a flawed design, challenge it and explain the consequences.

## Development workflow
1. Understand the requirement → 2. explain the design → 3. alternatives and trade-offs → 4. implementation plan → **5. wait for approval** → 6. implement a small piece → 7. explain changes → 8. write **and run** tests → 9. review edge and failure cases → 10. document → 11. update `docs/PROJECT_STATUS.md`.

## Hard rules
- Do not change the approved architecture silently. Propose an ADR in `docs/adr/` instead.
- Explain why before adding any new dependency.
- Never report tests as passing without running them. Show the command and the result.
- Never claim scalability or high availability without benchmark or failure-test evidence.
- Authorization and tenant isolation are enforced in backend code, never by LLM prompts.
- No secrets in code, logs or commits. Configuration comes from environment variables.
- Don't overwrite the owner's changes. Don't create empty modules or abstractions before they are needed.

## Key documents
- `docs/system-design.md`: the entry point to the design
- `docs/PROJECT_STATUS.md`: current phase and next steps (keep it updated)
- `docs/adr/`: decisions and their reasons
- `docs/learning/`: concept notes and interview prep per phase
