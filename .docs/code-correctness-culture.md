# Code Correctness Culture (Correctness by Construction)

When tempted to add a guard, fallback, default, redundant validation, or "just in case" branch, stop. Ask whether the design itself can make the bad state impossible. Scattered runtime checks signal a weak data model. Fix the structure; the guards disappear.

## Lineage

- Make illegal states unrepresentable, Yaron Minsky (Jane Street), Scott Wlaschin (Domain Modeling Made Functional).
- Parse, don't validate, Alexis King.
- Design by Contract, Bertrand Meyer (preconditions, postconditions, class invariants).
- Tell, don't ask, Andy Hunt, Martin Fowler.
- Fail fast, Jim Shore.
- Encapsulation as invariant protection, Bjarne Stroustrup, Barbara Liskov.
- YAGNI, Ron Jeffries.
- Errors should never pass silently, Tim Peters (PEP 20).
- Cyclomatic complexity is a smell, Thomas McCabe.

## Core principles

1. **Make illegal states unrepresentable**, use discriminated unions, not records with many optionals.
   ```ts
   // Wrong: { status: 'idle'|'done'|'error'; data?: T; error?: string }
   // Right:  {status:'idle'} | {status:'done'; data:T} | {status:'error'; error:string}
   ```
2. **Parse, don't validate**, validate ONCE at the system boundary into a strong type; never re-check downstream.
3. **Encapsulation protects invariants**, `order.markShipped()`, not `order.status='shipped'; order.shippedAt=new Date()`.
4. **Tell, don't ask**, `project.deleteAs(user)`, not `if (user.isAdmin && ...) project.delete()`.
5. **Fail fast, fail loud**, never swallow errors or return `[]`, `null`, `0`, `{name:'Guest'}` to mask failure.
6. **No fallbacks for source-of-truth**, auth claim, DB row, remote config: no local fallback. Silently weakens security.
7. **YAGNI**, no guards, params, or branches for cases not real today.
8. **Complexity is a data-flow signal**, nested `if` ladders mean the data model is too loose; reshape before adding another `if`.

## Decision algorithm (run BEFORE any guard/check/fallback/try-catch)

1. Is the bad state possible given the type/call site/schema? **NO** → remove guard or strengthen the type.
2. Is it only possible because the data model is too loose? **YES** → fix with sum types, branded types, smart constructors.
3. Is the input crossing an uncontrolled system boundary? **YES** → validate ONCE at the boundary; downstream trusts the type.
4. Is it a real, designed failure scenario (timeout, concurrent modification)? **YES** → handle explicitly with typed Result; never silent default.
5. Did you reach this because "what if it changes someday"? → **YAGNI. Stop.**

## Code smells

- Null checks for values the type system proves can't be null
- `try/catch` returning `[]`, `null`, `0`, default DTOs, or `{name:'Guest'}`
- Nested `if` ladders for states the data model should forbid
- Duplicated validation at many call sites instead of one boundary
- Frontend hardcoded role/permission lists "while the API loads"
- `catch (e) { console.log(e); }` with no rethrow
- Speculative params, unused option bags, flags to nowhere

## When defensive code IS justified

1. **System boundaries**, HTTP payloads, file uploads, webhooks, plugin input: validate aggressively, map to internal types.
2. **External I/O**, network, flaky APIs: retry, timeout, circuit breaker at clear edges.
3. **Concurrency**, locks, CAS, cancellation: invariants spanning threads.
4. **Serialization versioning**, tolerate unknown fields explicitly as a stated compatibility policy.
5. **Fault isolation**, with observable signals (metrics, logs, alarms); never silent success on corruption.
