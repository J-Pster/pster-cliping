# backend/src/database

TypeORM migrations and entities for the Clipador PostgreSQL database.

## ABSOLUTE RULE: never create migration files by hand

**Always** use the TypeORM CLI. Entity definitions → CLI → migration file. Never skip the middle step.

Do not invent a timestamp. Do not hand-write the `.ts`. Do not copy an old migration and edit it. Every migration must come from the `entities × DB` diff the CLI computes. Fabricated zero-padded timestamps (`1780900000000`, `1780900000001`, etc.) are a clear sign of an AI improvising and are forbidden.

## ABSOLUTE RULE: migrations are for SCHEMA, never for DATA

Row manipulation (`INSERT`, `UPDATE`, `DELETE`) **never** goes inside a migration. Migrations version structure (tables, columns, indexes, FKs, enums). Data is state, it does not belong in versioned files.

When you need to touch data:
- Connect to the DB directly (psql or an admin script) and run the SQL there.
- Document what ran in ai-memory (`memory_write_page`) if it is a significant action, but the migration file is **not** the place.

Exceptions that look like data but are schema-adjacent (reference-table seeds, immutable lookups/catalogs): **still** via a direct DB connection or a dedicated seeds script, not via a migration.

## Atomic chain, NEVER break it

```
1. npm run typeorm:generate -- src/database/migrations/MigrationName
2. Review: only the expected changes should be present
3. npm run typeorm:run   ← IMMEDIATELY after generating
4. If it fails: STOP. Fix before anything else.
```

Second migration in the same session? The first one MUST have run before generating the second.

## Commands

```bash
npm run typeorm:generate -- src/database/migrations/Name
npm run typeorm:run
npm run typeorm:revert
npm run typeorm:show
```

## NEVER

- Create a migration by hand (copy a template, write raw SQL directly).
- Edit a migration that already ran in production, create a corrective migration instead.
- Delete migration files that already ran in production.
- Move to the next task without running the migration you just generated.

## Entities (`src/database/entities/`)

Use TypeORM decorators correctly: `@Entity`, `@Column`, `@Index`, `@ManyToOne`, `@OneToMany`, `@JoinColumn`. After changing an entity, always regenerate the migration via the CLI.

## NEVER NEVER NEVER (anti-drift hardcore)

- Edit the `typeorm_migrations` table directly via psql/a DB client (`SELECT` is fine; `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/DDL on it is blocked).
  → If the ledger needs a fix, create a "repair migration" instead.
- Rename a migration file already committed in any environment (even if it has not run in production yet).
- Edit the content of an already-committed migration, create a new migration that corrects it.
- Regenerate a migration that already ran in any DB (local, staging, production).
- Apply raw DDL directly against production outside the TypeORM flow.
- Run `typeorm:run` against production manually, use the CI/CD pipeline with a concurrency lock once one exists.

## If tempted to do any of this: STOP

Ask for explicit human approval before executing.

## Drift detected between local and production?

Do NOT fix it silently.
1. Show a diff table (migration files vs local DB vs production DB).
2. List the likely root cause.
3. Propose a plan with a mandatory backup (external `pg_dump`).
4. Wait for human approval before any `DELETE`/`INSERT` touching `typeorm_migrations`.
