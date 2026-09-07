# frontend

Angular SPA for Clipador: upload a video, watch job progress, review/export generated clips, manage account and billing.

## Stack

| Lib | Version |
|-----|---------|
| Angular | ^21.2.0 |
| TypeScript | ~5.9.2 |
| RxJS | ~7.8.0 |

## Architecture

Standalone components + lazy loading throughout. No feature NgModules. `app.config.ts` provides the router, HTTP client and global providers.

```
src/
  app/
    app.config.ts        # global providers (router, http, error handler)
    app.routes.ts         # root routes, lazy loadComponent/loadChildren
    core/                # singleton services, guards, interceptors, models
    features/            # lazy-loaded feature slices (upload, jobs, clips, billing...)
    shared/              # reusable components and services
  environments/
    environment.ts        # dev
    environment.prod.ts   # prod
```

## Commands

```bash
npm start                    # ng serve, dev
npm run build                # ng build, production configuration
npm test                     # unit tests
```

**After any code change: run `npm run build` before marking it done.**

## Design System

**Read `DESIGN.md` at the workspace root before any visual change.**

- Font: Poppins (`$font-family-primary`), weights 400/500/600/700 only. Always `font-family: inherit` in components.
- Colors, spacing, radius: exclusively the tokens from `DESIGN.md` (CSS custom properties).
- Borders: `1px solid var(--border)`.
- Component styles: inline SCSS (`inlineStyleLanguage: "scss"`).

## Invariants

- Every production API call goes through `environment.apiUrl`, centralize the HTTP base URL, never hardcode it in a component.
- HTTP errors: centralize handling in one interceptor/service, do not scatter `catch` blocks per component.
- Never hardcode role/permission lists in the frontend once auth exists, permissions come from the backend.

## Don't

- `cdk deploy`, never.
- Add NgModules, the app uses standalone components.
- Commit without the user explicitly asking.
