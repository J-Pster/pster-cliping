---
paths:
  - "backend/src/database/migrations/**"
  - "backend/src/database/entities/**"
---
# TypeORM Migrations, Critical Rules

NEVER create migration files by hand. Always use the TypeORM CLI.

**Atomic chain, NEVER break this sequence:**
1. `npm run typeorm:generate -- src/database/migrations/MigrationName`
2. Review the generated file: only the expected changes should be there
3. `npm run typeorm:run`, IMMEDIATELY after generating
4. If it fails: STOP. Fix before doing anything else.

Need a second migration in the same session? The first one MUST have run before generating the second.

**NEVER:**
- Create a migration by hand (copy a template, write raw SQL directly)
- Put row `INSERT` / `UPDATE` / `DELETE` inside a migration. **Migrations are for schema.** For data, connect to the DB directly and run SQL there (psql or an admin script), never via a migration file.
- Invent a timestamp, zero-padded sequences (`1780900000000`, `1780900000001`, ...) are forbidden. Use only a real `Date.now()`, via the CLI.
- Edit a migration that already ran in production, create a corrective migration instead.
- Delete migration files that already ran in production.
- Move on to the next task without running the migration you just generated.

## Fallback ONLY when the CLI is unavailable

If, and only if, the environment blocks `typeorm:generate` (Docker down, no network for deps, etc.), write a skeleton migration by hand with a real `Date.now()` timestamp, matching the TypeORM CLI filename/class-name format exactly. Return to the CLI and regenerate via the real entity diff as soon as possible.

## Anti-drift checklist

Before declaring a feature with a migration "done":
1. Confirm the migration actually ran locally (`npm run typeorm:show`).
2. Confirm zero divergence between migration files and the `typeorm_migrations` table in every environment you can reach.

## Drift warning signs

- A row in `typeorm_migrations` with no matching file in `src/database/migrations/`
- A file in `src/database/migrations/` with no matching row in some DB
- A duplicate `(timestamp, name)` pair in the ledger
- A ledger timestamp newer than the latest file in git

Stop immediately. Do not try to "fix" it via ad-hoc SQL. Report to the user with the full diff and wait for a decision.
