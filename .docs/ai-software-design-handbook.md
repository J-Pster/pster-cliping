# AI Software Design Handbook

Keep control flow readable, complexity bounded, and design choices deliberate, not accidental.

## Pre-merge checklist

1. **Nesting**, guard clauses (early `return`/`continue`); main path stays at one indent level.
2. **Names**, extracted units named after domain intent (`resolvePostAuthRoute`), not mechanics (`doStuff`).
3. **Duplication**, repeated sequences (parse → validate → act) exist in one place.
4. **Side effects**, don't mix HTTP + storage + navigation + domain rules in one branch; split orchestration from logic.
5. **Complexity**, if a function can't be described in one sentence, split by outcome or layer (logic vs I/O).
6. **Patterns**, GoF/architectural patterns only when they remove coupling or clarify extension points. No cargo-culting CQRS/sagas into simple CRUD.
7. **Boundaries**, for APIs/queues/multi-module: apply idempotency, EIP patterns, DDD where scope demands.
8. **Cultural prerequisite**, before any guard/fallback/default/try-catch: run the 5-question algorithm in `code-correctness-culture.md`.

## Control flow

Multi-axis rules (role × plan × flags × storage): prefer **one function per outcome** or **one function per axis resolver** (e.g. `resolveClipRenderPlan()`, `shouldDeferToQueue()`). Table-driven map for finite cases; explicit state machine when transitions and invariants matter.

## Cyclomatic complexity (McCabe)

Count of linearly independent paths through a function. Treat 10-15 as "justify or refactor", higher as "split soon". Rule: if you cannot describe a function in one short sentence, it does too much, split by decision outcomes or layer.

## SOLID (AI checks)

- **SRP:** Name the responsibility in 5 words without "and". If you can't, split.
- **OCP:** New variants shouldn't require editing a `switch` in N places, prefer registry or polymorphic family.
- **LSP:** Can every caller of the base type use the subtype without special cases?
- **ISP:** If a consumer ignores half the methods, split the type or inject a narrower port.
- **DIP:** Domain logic depends on abstractions; inject ports (repositories, clocks, config), not concrete infra.

## CUPID (modern complement to SOLID)

Properties of maintainable units (Dan North, 2021): **Composable**, **Unix** (does one thing well), **Predictable**, **Idiomatic** (fits the stack), **Domain-based** (structure tracks problem language). Less "letter law" than SOLID; pairs well with small TS modules.

## Design constraints

- **Tell, don't ask**, let objects act on their own state; don't pull fields and branch outside. Avoids leaky abstractions and long `a.b().c().d()` chains (Law of Demeter).
- **CQS**, a routine is either a command (mutation) or a query (no mutation); avoids surprising side effects in "getters". **CQRS** (split write/read models) is powerful for complex domains but overkill for simple CRUD.
- **Error modeling**, railway-oriented (Result/Either) at boundaries; keep domain core free of transport exceptions.
- **Idempotency**, SQS/EventBridge/webhook handlers must be idempotent with explicit retry + idempotency keys.
- **Hexagonal/ports**, domain core calls ports; adapters implement IO (HTTP, DB, queue).
- **DRY**, factor repeated *meaning*, not repeated tokens, wrong abstraction is worse than duplication.
- **Composition over inheritance**, favor has-a + small interfaces over deep class hierarchies (TS/Angular/NestJS).
- **Immutability**, prefer `readonly`/new objects for small value shapes to reduce accidental mutation.
- **GRASP**, Information Expert (put behavior with the data it needs); Controller (orchestrate, don't do all work).
- **Twelve-Factor**, config via env, logs as streams, stateless processes, disposability, baseline for ECS containers and Lambdas.
- **Schema vs business rules, where DB constraints stop (project house rule)**, the database enforces *structural* integrity only; *value limits and mutable policy* live in code.
  - **Belongs in the schema (structural invariants):** column types, `NOT NULL`, `DEFAULT`, foreign keys, `UNIQUE`, and **native enums** (a closed set of valid values is a domain, which is structural).
  - **Belongs in code (the application layer):** numeric ranges, cross-field coherence, counts, and any "how big / how many / which combinations are valid" rule. Enforce these once at the boundary (class-validator DTO) plus service invariants, never as DB `CHECK` constraints.
  - **Why:** a value limit is *policy that changes*, not a schema invariant. A DB `CHECK` forces a migration for every business tweak and splits one rule across two layers (DTO *and* DB), so they drift. Native enums are different, they are the value domain itself, so they stay in the schema; a `CHECK` that merely simulates an enum is acceptable only as a fallback when a native enum is impractical.

## Anti-patterns to flag

- **God class/component**, UI + HTTP + routing + storage in one unit.
- **Shotgun surgery**, one concept change forces edits across many unrelated files (cohesion/coupling smell).
- **Primitive obsession**, loose `string`/`Record` instead of typed value objects that encode invariants.
- **Boolean blindness**, `doThing(true, false, true)` → use small types or enums.

## GoF patterns (use when / avoid when)

**Creational**
- **Factory/Abstract Factory**, use when creation is non-trivial or varies by environment; avoid when construction is a one-liner.
- **Builder**, use when many optional fields or staged construction; avoid for flat DTOs.
- **Singleton**, use for truly single coordinated resources (rare); avoid for global mutable state by convenience.

**Structural**
- **Adapter**, use to bridge incompatible interfaces (legacy, third-party); avoid when you control both sides.
- **Decorator**, use to add behavior in layers without subclass explosion; avoid for one small tweak.
- **Facade**, use to hide a messy subsystem behind one port; avoid when already a thin wrapper.
- **Proxy**, use for lazy load, access control, remote boundary; avoid when direct call is clearer.

**Behavioral**
- **Strategy**, use for swappable algorithms or policies; avoid when there's only one algorithm.
- **Command**, use for undo, queueing, macro transactions; avoid for simple function calls.
- **Observer/Pub-Sub**, use for many listeners, UI reactivity; avoid for local synchronous flow.
- **State**, use for explicit transitions and invariants; avoid when two booleans suffice.
- **Template Method**, use for fixed skeleton with varying steps; avoid when hooks obscure flow in small TS/NestJS services.

## DDD tactical building blocks

- **Value object**, immutable, validated by construction (money, email, date range).
- **Entity**, identity matters; lifecycle and invariants span mutations.
- **Aggregate root**, consistency boundary; external refs to root only.
- **Domain service**, rule doesn't naturally belong on one entity/VO.
- **ACL**, translate foreign models (legacy API, vendor DTO) at boundary.
- **Ubiquitous language**, names in code match stakeholder vocabulary.

## EIP high-signal patterns (NestJS + SQS/EventBridge)

**Idempotent receiver**, **competing consumers**, **message expiration/DLQ**, **process manager** (orchestrated saga), always pair with observability and explicit retry + idempotency keys where at-least-once delivery applies.
