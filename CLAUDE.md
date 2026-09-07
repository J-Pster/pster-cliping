<!-- OMC orchestration block intentionally omitted: it already loads from ~/.claude/CLAUDE.md every session. -->

**Memory-first:** Before ANY task (implementation, analysis, security, architecture, infra), call `memory_query` (ai-memory MCP) with relevant keywords to check for established patterns and decisions. ai-memory is the single source of project knowledge and wiki; its findings take precedence over any new proposal.

---

# Clipador

SaaS that turns a raw YouTube video into short and long clips: automatic editing, thumbnail generation, title, description and hashtags. Three parts in this monorepo:

```
engine/     # Python engine: the clip-generation pipeline (yt-dlp, transcription, cuts, thumbnails)
backend/    # NestJS 11 API: orchestrates the engine, persists jobs/users/clips, serves the frontend
frontend/   # Angular SPA: upload, job status, clip review/export, account/billing
```

Each part has its own `CLAUDE.md` with stack, layout and commands:

- `engine/CLAUDE.md` — Python pipeline. **Read it before touching transcription or
  subtitles**: both carry binding decisions backed by measurement. It also holds the
  **pending work** the user asked future sessions to remember.
- `backend/CLAUDE.md` — NestJS 11, TypeORM, PostgreSQL.
- `frontend/CLAUDE.md` — Angular, standalone components.

Decision records with the evidence behind non-obvious choices live in `.docs/decisions/`.

Path-scoped rules in `.claude/rules/` load automatically when opening matching files.

---

# Quality Rules (mandatory every session)

@.docs/design-rules-digest.md

Full versions (read when a rule needs nuance or examples): `.docs/code-correctness-culture.md` and `.docs/ai-software-design-handbook.md`.

---

# Paths and `@`-mentions are hints, not boundaries

When the user marks a file/directory or mentions a path while describing a task, treat it as a **starting point to locate the problem**, not as the mandatory place the fix happens.

- The marker points you **near the problem** ("it's about clip rendering", "look around here"), it does not fence the scope of the change.
- The root cause and the fix can live in **any layer**: frontend, backend (NestJS), the Python engine, a migration, AWS config, wherever the investigation leads.
- Always trace the problem to its real root cause following the data flow between `frontend` → `backend` → `engine`, instead of assuming the fix belongs in the marked path.

---

# AWS

- **Always AWS CLI**, never CDK, never manual console changes for anything reproducible.
- Profile: `CortePoliticoAdmin` (`aws sso login --profile CortePoliticoAdmin`), account `229446391137`, default region `us-east-2`. IAM Identity Center admin, never root.
- Before any AWS operation, verify the login (`aws sts get-caller-identity --profile <profile>`). If it errors, run `aws sso login --profile <profile>` and wait for the user to finish browser auth before resuming.
- Encryption keys and secrets exclusively from Secrets Manager, no local fallback.

---

# Cross-Cutting Invariants (apply to every part)

- **Controllers thin:** business logic lives in services (backend).
- **Engine as a black box from the backend's point of view:** the backend orchestrates and persists; it does not reimplement engine logic (transcription, cuts, thumbnails) in TypeScript.
- **Commits:** only when the user explicitly asks.
- **No em dash** anywhere (code, docs, commit messages, UI copy).
