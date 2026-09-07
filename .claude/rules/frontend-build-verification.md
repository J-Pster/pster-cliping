---
paths:
  - "frontend/**"
---
# Frontend, Build Verification

After any change under `frontend/`, run the build before marking the task complete:

```bash
cd frontend && npm run build
```

This runs `ng build` (production configuration) and compiles the Angular bundle.

**NEVER** declare the task done if the build returns errors. Fix every TypeScript, SCSS, and Angular module error, then re-run until the build passes with exit code 0 and produces output in `dist/frontend`.
