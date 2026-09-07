---
paths:
  - "frontend/src/**/*.ts"
  - "frontend/src/**/*.html"
  - "frontend/src/**/*.scss"
---
# Design System, Rules

**MANDATORY:** Read `DESIGN.md` at the workspace root before any visual change.

- Font: Poppins (`$font-family-primary`), weights 400/500/600/700 only. Always `font-family: inherit` in components.
- Colors and spacing: only the tokens defined in DESIGN.md (CSS custom properties).
- Borders: `1px solid var(--border)`.
- Radius: scale defined in DESIGN.md (8px sm, 12px md, 6px compact controls, 999px pills).

Do not invent values outside the scale. Do not use chrome hex codes that are not in DESIGN.md (functional status colors and the documented brand accents are the only exceptions).
