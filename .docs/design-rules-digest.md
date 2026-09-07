# Design & Correctness Rules (digest)

Condensed from `.docs/code-correctness-culture.md` and `.docs/ai-software-design-handbook.md`. Every rule below is binding; read the full docs only when a rule needs nuance or examples.

## Correctness by Construction

**Decision algorithm (run BEFORE any guard/check/fallback/try-catch):**
1. Bad state impossible given the type/call site/schema? NO possibility: remove the guard or strengthen the type.
2. Possible only because the data model is too loose? Fix with sum types, branded types, smart constructors.
3. Input crossing an uncontrolled system boundary? Validate ONCE at the boundary; downstream trusts the type.
4. Real, designed failure scenario (timeout, concurrent modification)? Handle explicitly with typed Result; never silent default.
5. Reached this because "what if it changes someday"? YAGNI. Stop.

**Core principles:**
1. Make illegal states unrepresentable: discriminated unions, not records with many optionals.
2. Parse, don't validate: validate ONCE at the boundary into a strong type; never re-check downstream.
3. Encapsulation protects invariants: `order.markShipped()`, not `order.status='shipped'; order.shippedAt=...`.
4. Tell, don't ask: `project.deleteAs(user)`, not `if (user.isAdmin && ...) project.delete()`.
5. Fail fast, fail loud: never swallow errors or return `[]`, `null`, `0`, `{name:'Guest'}` to mask failure.
6. No fallbacks for source-of-truth (auth claim, DB row, remote config): silently weakens security.
7. YAGNI: no guards, params, or branches for cases not real today.
8. Complexity is a data-flow signal: nested `if` ladders mean the data model is too loose; reshape before adding another `if`.

**Code smells:** null checks the type system already proves impossible; `try/catch` returning `[]`/`null`/`0`/default DTOs; nested `if` ladders for states the model should forbid; duplicated validation at many call sites; frontend hardcoded role lists "while the API loads"; `catch (e) { console.log(e); }` without rethrow; speculative params, unused option bags, flags to nowhere.

**Defensive code IS justified at:** system boundaries (HTTP payloads, uploads, webhooks, plugin input); external I/O (retry, timeout, circuit breaker); concurrency (locks, CAS, cancellation); serialization versioning (explicit compatibility policy); fault isolation with observable signals (never silent success on corruption).

## Design Handbook

**Pre-merge checklist:**
1. Nesting: guard clauses, main path at one indent level.
2. Names: domain intent (`resolvePostAuthRoute`), not mechanics (`doStuff`).
3. Duplication: repeated parse → validate → act sequences live in ONE place.
4. Side effects: don't mix HTTP + storage + navigation + domain rules in one branch; split orchestration from logic.
5. Complexity: if a function can't be described in one sentence, split by outcome or layer.
6. Patterns only when they remove coupling or clarify extension points; no cargo-cult CQRS/sagas in simple CRUD.
7. Boundaries (APIs/queues/multi-module): idempotency, EIP, DDD where scope demands.
8. Run the 5-question algorithm above before any guard/fallback/default/try-catch.

**Control flow:** multi-axis rules (role × plan × flags): one function per outcome or per axis resolver; table-driven map for finite cases; explicit state machine when transitions/invariants matter. Cyclomatic complexity 10-15 = justify or refactor; higher = split soon.

**SOLID:** SRP (name the responsibility in 5 words without "and"); OCP (new variants must not edit a `switch` in N places: registry or polymorphic family); LSP (every caller of the base type can use the subtype without special cases); ISP (consumer ignoring half the methods: split or inject a narrower port); DIP (domain depends on abstractions; inject ports, not concrete infra).

**CUPID:** Composable, Unix (one thing well), Predictable, Idiomatic, Domain-based.

**Design constraints:** tell-don't-ask + Law of Demeter (no `a.b().c().d()` chains); CQS (a routine is command XOR query; CQRS only for complex domains); error modeling railway-oriented (Result/Either) at boundaries, domain core free of transport exceptions; SQS/EventBridge/webhook handlers idempotent with explicit retry + idempotency keys; hexagonal ports/adapters (domain calls ports, adapters implement I/O); DRY = factor repeated MEANING, not tokens (wrong abstraction is worse than duplication); composition over inheritance; immutability (`readonly`/new objects) for small value shapes; GRASP (Information Expert, Controller orchestrates); Twelve-Factor for ECS containers and Lambdas.

**Schema vs business rules (where DB constraints stop):** The database enforces STRUCTURAL integrity only: column types, `NOT NULL`, `DEFAULT`, foreign keys, `UNIQUE`, and native enums (a closed value domain is structural). Business limits and mutable policy stay in CODE: numeric ranges, cross-field coherence, and any rule that can change without a schema change live in DTO validation at the boundary + service invariants, NOT as DB `CHECK` constraints. Why: a value limit is policy, not a schema invariant; baking it into the DB forces a migration for every business tweak and splits one rule across two layers. Keep native enums in the DB (they are a domain, not a limit); a `CHECK` that merely simulates an enum is acceptable only as a fallback when a native enum is impractical. This is the project house rule, prefer typed columns + native enums + FK/UNIQUE in the schema, and put the "how big / how many / which combinations are valid" logic in the application layer.

**Anti-patterns to flag:** god class/component (UI + HTTP + routing + storage in one unit); shotgun surgery (one concept change forces edits across many unrelated files); primitive obsession (loose `string`/`Record` instead of typed value objects); boolean blindness (`doThing(true, false, true)`: use small types or enums).

**GoF (use when / avoid when):** Factory (non-trivial or env-varying creation / one-liner construction); Builder (many optional fields / flat DTOs); Singleton (truly single coordinated resource, rare / global mutable state by convenience); Adapter (incompatible third-party interfaces / you control both sides); Decorator (layered behavior without subclass explosion / one small tweak); Facade (hide messy subsystem / already a thin wrapper); Proxy (lazy load, access control, remote boundary / direct call is clearer); Strategy (swappable algorithms / only one algorithm); Command (undo, queueing, macros / simple function call); Observer (many listeners, UI reactivity / local synchronous flow); State (explicit transitions and invariants / two booleans suffice); Template Method (fixed skeleton with varying steps / hooks obscure flow in small services).

**DDD tactical blocks:** value object (immutable, validated by construction); entity (identity + lifecycle invariants); aggregate root (consistency boundary, external refs to root only); domain service (rule belongs to no single entity); ACL (translate foreign models at the boundary); ubiquitous language (code names match stakeholder vocabulary).

**EIP (NestJS + SQS/EventBridge):** idempotent receiver, competing consumers, message expiration/DLQ, process manager (orchestrated saga); always paired with observability and explicit retry + idempotency keys under at-least-once delivery.
