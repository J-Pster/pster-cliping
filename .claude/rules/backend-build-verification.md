---
paths:
  - "backend/**"
---
# Backend, Build Verification

After any change under `backend/`, run the build before marking the task complete:

```bash
cd backend && npm run build
```

This runs `nest build` and compiles the whole TypeScript project.

**NEVER** declare the task done if the build returns compilation errors. Fix every type and syntax error and re-run until the build passes with exit code 0.
