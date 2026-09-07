# backend

NestJS 11 API. Orchestrates the Python engine (`../engine/`), persists jobs/users/clips, serves the Angular frontend and mobile clients (future).

## Stack

- NestJS 11, TypeScript strict
- TypeORM + PostgreSQL
- Jest for tests

## Layout (target)

```
src/
  <feature>/          # module per domain (jobs, clips, users, billing...)
  database/
    entities/          # TypeORM entities (see database/CLAUDE.md for migration rules)
    migrations/         # generated via CLI, NEVER by hand
    seeds/
  common/              # shared guards, interceptors, decorators
```

## Commands

```bash
docker compose up -d                     # from repo root: Postgres + backend, hot-reload
docker logs cortepolitico-backend -f     # backend logs
npm run start:dev                        # local dev without Docker, watch mode
npm run build                            # nest build
npm run test                             # Jest
npm run typeorm:generate -- src/database/migrations/Name   # after TypeORM is wired in
npm run typeorm:run
npm run typeorm:revert
```

Local dev runs via the root `docker-compose.yml` (Postgres on host port `5433`, backend on `3000`). The backend container mounts `~/.aws` read-only and uses `AWS_PROFILE=CortePoliticoAdmin`, so it hits real Cognito/Secrets Manager in dev, never a local `.env` fallback. Requires `aws sso login --profile CortePoliticoAdmin` active on the host.

`typeorm:*` scripts are not wired yet, add them to `package.json` once TypeORM and the DB connection are set up. Until then, follow `.claude/rules/typeorm-migrations.md` and `src/database/CLAUDE.md` the moment migrations exist.

## Invariants

- **Controllers thin:** zero business logic, orchestration only.
- **Domain logic** exclusively in services.
- **DTO-driven** at every request/response boundary, `class-validator` + `class-transformer`.
- **Engine calls are I/O at a boundary:** treat the Python engine as an external system (subprocess, queue, or HTTP, decide and document once chosen), never inline its logic in TypeScript.

## Secrets & Config

- `@nestjs/config`, typed configuration, no hardcoded secrets in code or logs.
- Encryption keys and credentials from AWS Secrets Manager once AWS is wired in, no local fallback for source-of-truth secrets.

## Sub-CLAUDE.md

- `src/database/CLAUDE.md` — TypeORM rules: migration workflow, entities, forbidden actions.

## Don't

- Don't use `cdk deploy`, infra via AWS CLI or scripts.
- Don't hardcode secrets or encryption keys in code or logs.
- Don't commit without the user explicitly asking.
