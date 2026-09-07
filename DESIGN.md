# Design System, Clipador MMCC

**MMCC: Minimalist, Modern, Compact, Clean.**

Same structural discipline as any BidChex-grade MMCC system (black/white base, one neutral chrome, functional color only where it carries meaning), tuned to Clipador's brand: Brazil flag green, yellow and blue as the accent family, black and white as the base. This document is the target system to build the Angular app against, there is no shipped SCSS yet. Once `frontend/src/styles/` exists, that SCSS becomes the source of truth and this file gets updated to match it, not the other way around.

The UI is theme-agnostic, driven entirely by CSS custom properties. Never hardcode chrome colors, always use the tokens. Support dark (default) and light themes via `data-theme` on `:root`, plus a `prefers-color-scheme` fallback when no attribute is set.

Two honest exceptions to "no hardcoded colors":
1. **Functional status colors** (green success, red error, amber warning, blue info) are hardcoded hex by design, see section 11. Note the success green is a different, more saturated hex than the brand green, they read as distinct semantics.
2. **Brand accent** (`--brand-green`, `--brand-yellow`, `--brand-blue`) is the one place a fixed brand hex is allowed outside chrome tokens, see section 1.

---

## 1. Theme Tokens (CSS Custom Properties)

Values below are dark / light.

### Core surfaces and text
| Token | Dark | Light | Role |
|-------|------|-------|------|
| `--bg` | `#0d0d0d` | `#fafafa` | Page background, standard hover fill for chrome buttons |
| `--panel` | `#161616` | `#ffffff` | Sidebar, header, cards, inputs, dropdown panels |
| `--surface` | `#161616` | `#ffffff` | Table rows, elevated surfaces |
| `--bg-muted` | `#121212` | `#f7f7f7` | Subtly recessed areas |
| `--surface-muted` | `#222222` | `#f1f5f9` | Code chips, muted panels |
| `--border` | `#2a2a2a` | `#b8b8b8` | All borders and dividers |
| `--control-border` | `#3d3d3d` | `#b8b8b8` | Input/select/control borders |
| `--border-subtle` | `rgba(255,255,255,0.09)` | `rgba(0,0,0,0.22)` | Ultra-subtle inner separators |
| `--text` | `#f4f4f4` | `#1a1a1a` | Primary text |
| `--text-muted` | `#b3b3b3` | `#666666` | Secondary, placeholder, labels |
| `--text-fine` | `#8a8a8a` | `#999999` | Timestamps, chevrons, fine print |

### Brand accent (Brazil flag family)
| Token | Value | Role |
|-------|-------|------|
| `--brand-green` | `#009c3b` | Primary brand accent, primary CTA, active nav, links |
| `--brand-green-hover` | `#00b042` | Brand green on hover |
| `--brand-yellow` | `#ffcc29` | Secondary accent, highlights, badges that need to pop, warning-adjacent brand moments |
| `--brand-blue` | `#002776` | Tertiary accent, used sparingly: info tags, selected map/timeline markers |
| `--brand-green-rgb` | `0,156,59` | For `rgba()` focus rings, `rgba(var(--brand-green-rgb), 0.35)` |
| `--text-on-brand` | `#ffffff` | Text placed on a brand-green or brand-blue filled surface |
| `--text-on-yellow` | `#111111` | Text placed on a brand-yellow filled surface (contrast) |

### Neutral chrome accent (non-brand interactive states)
| Token | Dark | Light | Role |
|-------|------|-------|------|
| `--accent` | `#009c3b` | `#00812f` | Interactive accent used across chrome (focus rings, hover borders, active states) — this IS the brand green, unlike a neutral-only MMCC system. Light mode uses a darkened green for AA contrast on white. |
| `--accent-hover` | `#00b042` | `#006b27` | Accent on hover |
| `--hover-bg` | `rgba(0,156,59,0.10)` | `rgba(0,129,47,0.08)` | Standard focus-ring fill and most hover backgrounds, tinted brand green, not gray |

> **Key rule.** Unlike a purely neutral MMCC system, Clipador's chrome accent IS the brand green. Keep it disciplined: one accent color for interactive chrome (`--accent`), yellow and blue stay reserved for the specific roles in section 1, never used interchangeably with `--accent`.

### Elevation
| Token | Dark | Light |
|-------|------|-------|
| `--shadow-sm` | `0 4px 12px rgba(0,0,0,0.3)` | `0 4px 12px rgba(0,0,0,0.1)` |
| `--shadow-md` | `0 6px 16px rgba(0,0,0,0.35)` | `0 6px 16px rgba(0,0,0,0.15)` |
| `--shadow-lg` | `0 8px 24px rgba(0,0,0,0.4)` | `0 8px 24px rgba(0,0,0,0.1)` |

### Functional and feature tokens
| Token | Dark | Light | Role |
|-------|------|-------|------|
| `--warning-bg` | `#352306` | `#fef3c7` | Warning banners |
| `--warning-border` | `#5c3d0a` | `#f59e0b` | Warning banner border / icon |
| `--info-bg` | `#0d1f38` | `#eff6ff` | Informational notice banners |
| `--info-border` | `#1e3a5f` | `#bfdbfe` | Informational notice border / icon |
| `--info-text` | `#93c5fd` | `#1d4ed8` | Informational notice copy |
| `--skeleton-from/via/to` | `#2a2a2a/#333/#2a2a2a` | `#f0f0f0/#e0e0e0/#f0f0f0` | Skeleton shimmer stops |

Do not invent new global tokens for one component. Reuse the set above or add a documented feature token here first.

---

## 2. Typography

**Font: Poppins.** `$font-family-primary: 'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`.

Always inherit from body (`font-family: inherit`), never redeclare `font-family` in components. Interactive elements (buttons, inputs, triggers) must set `font-family: inherit`.

### Size scale (`$font-sizes`)
| Token | Value | Use |
|-------|-------|-----|
| `xs` | 12px | Labels, micro text, status badges, hints |
| `sm` | 13px | Table cells, dropdown rows, tile titles, compact body |
| `base` | 16px | Default body |
| `lg` | 20px | Card titles, modal headings |
| `xl` | 22px | Sub-page headings |
| `2xl` | 44px | Display |
| `3xl` | 54px | Display |

### Weights (`$font-weights`)
| Token | Value | Use |
|-------|-------|-----|
| `normal` | 400 | Reading text, sub-titles |
| `medium` | 500 | Labels, tile titles, nav, controls |
| `semibold` | 600 | Section headings, table headers, card headers |
| `bold` | 700 | Display numbers, strong emphasis |

Line height: `1.5` body, `1.2`-`1.4` headings and compact UI, `1.45`-`1.55` paragraphs inside asides.

---

## 3. Spacing Scale

Base unit **4px**. Always `map.get(vars.$spacing-scale, N)`.

| Key | Value | Use |
|-----|-------|-----|
| 1 | 4px | Micro gaps, icon-to-label, badge padding-y |
| 2 | 8px | Row gaps, inline item gaps, table cell padding |
| 3 | 12px | Compact padding, control padding, strip padding |
| 4 | 16px | Standard padding, section gutter, card padding |
| 5 | 20px | Header horizontal padding, between sections |
| 6 | 24px | Generous section spacing, tab content gaps |
| 8 | 32px | Large vertical rhythm, empty states |
| 10 | 40px | Empty states, search input inset |

Compact dashboard defaults: table cell padding `8px`, dropdown row padding `8px 12px`, control padding `12px 12px`.

---

## 4. Border Radius

| Token | Value | Use |
|-------|-------|-----|
| `$border-radius-sm` | 8px | Buttons, text inputs, search bars |
| `$border-radius-md` | 12px | Cards, modals, asides, tiles, table containers |
| `$border-radius-full` | 999px | Pills, chips, status badges, avatar status dots |
| literal `6px` | 6px | Compact controls: dropdown panels, trigger rows, menu items, icon buttons |
| literal `50%` | round | Avatars, status dots |

`6px` is first-class for interactive chrome, not an exception. Use `sm` (8px) for full-size inputs/buttons, `6px` for compact triggers/menus, `md` (12px) for cards/panels/tables.

---

## 5. Buttons

One global button system. Reuse `.btn` plus a variant class; do not hand-roll button styles in component SCSS.

### Base `.btn`
```scss
display: inline-flex; align-items: center; justify-content: center;
gap: 8px;
padding: 12px 24px;
border-radius: vars.$border-radius-sm;   // 8px
font-size: map.get(vars.$font-sizes, base);
font-weight: map.get(vars.$font-weights, medium);
font-family: inherit;
border: 1px solid transparent;
line-height: 1.5;
transition: all vars.$transition-base;   // 0.3s ease

&:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
&:disabled { opacity: 0.5; cursor: not-allowed; pointer-events: none; }
```

Sizes: `.btn-sm` (8px 16px, 13px), `.btn-xs` (6px 12px, 12px), `.btn-lg` (16px 32px, 20px), `.btn-icon` (square), `.btn-block` (full width).

### Variants
| Class | Fill | Text | Border | Hover |
|-------|------|------|--------|-------|
| `.btn-primary` | `var(--brand-green)` | `var(--text-on-brand)` | `var(--brand-green)` | fill `var(--brand-green-hover)`, lift `translateY(-2px)`, shadow |
| `.btn-secondary` | `var(--panel)` | `var(--text)` | `var(--border)` | fill `var(--bg)`, border `var(--text)`, lift `-1px` |
| `.btn-outline` | transparent | `var(--text)` | `var(--border)` | fill `var(--bg)`, border+text `var(--accent)`, lift `-1px` |
| `.btn-outline-primary` | transparent | `var(--brand-green)` | `var(--brand-green)` | fill `var(--brand-green)`, text `var(--text-on-brand)` |
| `.btn-ghost` | transparent | `var(--text)` | none | fill `var(--hover-bg)`, text `var(--accent)` |
| `.btn-link` | transparent | `var(--accent)` | none, underlined | text `var(--brand-green-hover)` |
| `.btn-danger` | `var(--panel)` | `#ef4444` | `#ef4444` | fill `#ef4444`, white text |
| `.btn-accent-yellow` | `var(--brand-yellow)` | `var(--text-on-yellow)` | `var(--brand-yellow)` | darken 8% |

> The **primary button is the brand green fill**. This is Clipador's one deliberate departure from a fully neutral MMCC chrome: the accent color and the primary-button color are the same brand green, used consistently everywhere so it reads as identity, not decoration.

---

## 6. Form Fields

### Field wrapper and label
```scss
.field { margin-bottom: 1rem; }

.label {
  display: block;
  font-size: 0.8125rem;        // 13px
  font-weight: 500;
  margin-bottom: 0.35rem;
  color: var(--text-muted);
}
```

### Control (input / select / textarea)
```scss
width: 100%;
max-width: 420px;
padding: 12px 12px;
border-radius: vars.$border-radius-sm;    // 8px
border: 1px solid var(--border);
font-size: 0.875rem;                      // 14px
background: var(--panel);
color: var(--text);
font-family: inherit;
box-sizing: border-box;

&:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--hover-bg);
}
&::placeholder { color: var(--text-muted); opacity: 0.6; }
&:disabled { opacity: 0.6; background: var(--bg); color: var(--text-muted); }
```

### Hints and errors
`.hint`: 13px, muted, `margin-top: 0.35rem`. `.error`: `rgba(239,68,68,0.1)` fill, `#ef4444` text, radius sm, 13px.

---

## 7. Dropdowns and Menus

```scss
background: var(--panel);
border: 1px solid var(--border);
border-radius: 6px;
box-shadow: var(--shadow-md);
width: 280px;
max-height: min(480px, 68dvh);
overflow: hidden;
animation: menuFadeIn 0.15s ease;
```

Rows: `padding: 8px 12px`, hover `background: var(--hover-bg)`, selected `background: color-mix(in srgb, var(--accent) 10%, transparent)`. Section headers: 10px/600, uppercase, `letter-spacing: 0.5px`, muted.

---

## 8. Header and Sidebar

### Header
Fixed, full width, height **64px**, `var(--panel)` background, `border-bottom: 1px solid var(--border)`, horizontal padding `20px` (`16px` on mobile), `z-index: 100`. Product mark uses `--brand-green` on the icon/wordmark, never as a full-width color block, this stays a black/white/gray UI with a green accent, not a green UI.

### Sidebar
Fixed, below the header, `var(--panel)` background, `border-right: 1px solid var(--border)`, collapsed **56px** / expanded **200px**, `z-index: 50`.

- Nav button: 36x32, radius 8px, transparent, muted icon; hover `var(--hover-bg)` + `var(--text)`; **active = `var(--brand-green)` text + `rgba(var(--brand-green-rgb), 0.12)` fill + 2px left border in `--brand-green`**.
- Badge: `var(--brand-yellow)` fill, `var(--text-on-yellow)` text, 11px/600, radius 9px, reserved for counts that need attention (new clips ready, job done).

---

## 9. Tables

```scss
border: 1px solid var(--border);
border-radius: vars.$border-radius-md;   // 12px
background: var(--surface);
overflow-x: auto;

thead { background: var(--panel); }
th {
  padding: 8px; text-align: left; white-space: nowrap;
  font-size: 13px; font-weight: 600;
  color: var(--text);
  border-bottom: 2px solid var(--border);
}
tr {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  &:hover { background: var(--hover-bg); }
  &:last-child { border-bottom: none; }
}
td { padding: 8px; color: var(--text); vertical-align: middle; }
```

---

## 10. Other Component Patterns

### Cards
```scss
@mixin card { background: var(--panel); border: 1px solid var(--border);
              border-radius: vars.$border-radius-md; padding: 20px; }
```

### Job/clip progress
Progress bars use `--brand-green` as the fill on a `var(--border)` track, radius `999px`, height `6px`. Completed state adds a small `--brand-yellow` check accent, not a full color swap, keep it a green bar with a yellow "done" beat, not a yellow bar.

### File drop zone (video upload)
Dashed `2px var(--border)`, radius md, `var(--surface)`, centered column, `min-height: 10rem`. Active/dragover: `--brand-green` border + `color-mix(in srgb, var(--brand-green) 6%, var(--surface))` fill + `0 0 0 1px` accent ring.

---

## 11. Status Badges (functional color, the colored exception)

Pill shape, `border-radius: 999px`, `padding: 4px 12px`, `font-size: xs` (12px), `font-weight: medium`.

```scss
// success / clip ready
background: rgba(34,197,94,0.2);  color: #15803d;
// info / processing
background: rgba(56,189,248,0.2); color: #0284c7;
// warning / queued
background: rgba(234,179,8,0.22); color: #a16207;
// error / failed
background: rgba(239,68,68,0.2);  color: #dc2626;
// neutral / archived
background: rgba(100,116,139,0.2); color: #475569;
```

These are the ONLY colored badges beyond the brand accent. Never use a colored badge purely decoratively, and never use `--brand-yellow` as a warning-badge substitute, warning stays amber (`#a16207`), yellow stays brand.

---

## 12. Modal Shell

Layout invariant: **fixed header, scrollable body only, fixed footer.**

```scss
.modal-host   { position: fixed; inset: 0; display: flex; justify-content: center;
                align-items: flex-start; overflow-y: auto; }
.modal-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.5);
                   backdrop-filter: blur(4px); }
.modal-panel  { width: min(640px, calc(100vw - 1rem));
                max-height: 88vh;
                background: var(--panel);
                border-radius: vars.$border-radius-md;
                border: 1px solid var(--border);
                box-shadow: var(--shadow-lg);
                display: flex; flex-direction: column; overflow: hidden; }
.modal-body   { flex: 1; min-height: 0; overflow-y: auto; padding: 24px; }
.modal-footer { flex-shrink: 0; padding: 16px 24px;
                border-top: 1px solid var(--border); }
```

Footer actions render end-aligned, `gap: 0.75rem`. Build this as one shared `app-modal-shell` component the moment a second modal exists, never a bespoke overlay per feature.

---

## 13. Breakpoints and Responsive

| Name | Width |
|------|-------|
| Mobile | <=767px |
| Tablet | 768-1023px |
| Desktop | >=1024px |

---

## 14. Transitions

```scss
$transition-fast: 0.15s ease;   // hover states, border/background on triggers
$transition-base: 0.3s ease;    // buttons (all), theme transitions
```

---

## 15. Do and Don't

### Do
- Use CSS custom properties for all chrome color: `var(--text)`, `var(--border)`, `var(--panel)`, `var(--accent)`.
- Use `font-family: inherit` everywhere (Poppins cascades from body).
- Use the spacing scale in section 3, do not invent one-off pixel values.
- Use the global `.btn` + variant classes, primary action is `.btn-primary` (brand green fill).
- Use `--brand-green` as the single interactive accent; reserve `--brand-yellow` and `--brand-blue` for the specific roles in section 1.
- Use status-badge colors only for functional state, never for brand decoration.
- Use `app-modal-shell` for every modal once it exists.

### Don't
- Don't hardcode chrome colors. Functional status hex and the three brand tokens are the only allowed literals.
- Don't paint large surfaces (a whole header, a whole sidebar) in brand green or yellow, this is a black/white/gray UI with a green accent and a yellow highlight, not a Brazil-flag-colored UI.
- Don't mix `--brand-blue` into interactive chrome, it is reserved for the specific tags/markers in section 1 until a real second use case earns it a broader role.
- Don't import any font other than Poppins, or use weights outside 400/500/600/700.
- Don't restyle buttons in component SCSS, extend the global system.
- Don't enlarge compact type (13px labels, 14px controls) to 16px.
- Don't use the em dash character anywhere.

---

## 16. Open decision for the user

The Brazil-flag palette above (`--brand-green #009c3b`, `--brand-yellow #ffcc29`, `--brand-blue #002776`) is a first pass meant to be tuned, not a locked spec. Adjust the exact hexes and update this file (and the eventual SCSS) once you've picked the final shades, keep every other section (typography, spacing, radius, buttons, forms, tables, modals) as the stable structural contract.
