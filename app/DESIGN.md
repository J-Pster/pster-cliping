# Design System, BidChex MMCC

**MMCC: Minimalist, Modern, Compact, Clean.**

This document describes the design as it actually exists in `bidchex-frontend`. The source of truth is the SCSS in `src/styles/` (`_variables.scss`, `_themes.scss`, `_mixins.scss`, `_buttons.scss`, `_dashboard-form-fields.scss`, `_modal-shell.scss`) and the real components (dashboard header/sidebar, dashboard tabs, project-detail tables, the shared dropdown). When in doubt, read those files, not this summary.

The UI is theme-agnostic, driven entirely by CSS custom properties. Never hardcode chrome colors, always use the tokens. The system supports dark (default) and light themes via `data-theme` on `:root` (also `.dark-theme` / `.light-theme` classes, and a `prefers-color-scheme` fallback when no attribute is set).

Two honest exceptions to "no hardcoded colors":
1. **Functional status colors** (green success, red error, amber warning, blue info) are hardcoded hex by design, see section 11.
2. **Interactive blue** (`#2563eb`, sometimes `#2196F3`) appears via fallbacks like `var(--accent, #2563eb)` / `var(--primary, #2563eb)` in dropdowns, badges and selection states. The neutral accent token is the chrome default; this blue is the functional "selected / actionable" hue.

---

## 1. Theme Tokens (CSS Custom Properties)

Defined in `_themes.scss` for `dark` and `light`. Values below are dark / light.

### Core surfaces and text
| Token | Dark | Light | Role |
|-------|------|-------|------|
| `--bg` | `#111111` | `#fafafa` | Page background, also the standard hover fill for chrome buttons |
| `--panel` | `#1a1a1a` | `#ffffff` | Sidebar, header, cards, inputs, dropdown panels |
| `--surface` | `#1a1a1a` | `#ffffff` | Table rows, elevated surfaces (identical value to `--panel` today) |
| `--bg-muted` | `#151515` | `#f7f7f7` | Subtly recessed areas, checklist rows, elevator card |
| `--surface-muted` | `#222222` | `#f1f5f9` | Code chips, muted panels |
| `--panel-muted` | `#222222` | `#f1f5f9` | Muted panel alias |
| `--color-surface-secondary` | `#2a2a2a` | `#f5f5f5` | Second-level surfaces |
| `--color-surface-secondary-hover` | `#333333` | `#ebebeb` | Hover for second-level surfaces |
| `--border` | `#2a2a2a` | `#b8b8b8` | All borders and dividers (light darkened to ~1.95:1 on white for visibility on low-contrast monitors; does not formally meet WCAG 1.4.11 3:1, kept lighter to preserve MMCC) |
| `--control-border` | `#3d3d3d` | `#b8b8b8` | Input/select/control borders (light kept equal to `--border`) |
| `--border-subtle` | `rgba(255,255,255,0.09)` | `rgba(0,0,0,0.22)` | Ultra-subtle inner separators (light darkened for visibility on washed-out displays) |
| `--text` | `#f4f4f4` | `#1a1a1a` | Primary text, also the primary-button fill |
| `--text-muted` | `#b3b3b3` | `#666666` | Secondary, placeholder, labels |
| `--text-fine` | `#8a8a8a` | `#999999` | Timestamps, chevrons, fine print |
| `--color-text-secondary` | `var(--text-muted)` | `#6b7280` | Secondary text alias |

### Accent and interaction
| Token | Dark | Light | Role |
|-------|------|-------|------|
| `--accent` | `#e6e6e6` | `#333333` | Neutral interactive accent (near-white / near-black), borders on focus/hover, active states |
| `--accent-hover` | `#ffffff` | `#000000` | Accent on hover |
| `--accent-rgb` | `230,230,230` | `51,51,51` | For `rgba()` focus rings, `rgba(var(--accent-rgb), 0.35)` |
| `--text-on-accent` | `#111111` | `#ffffff` | Text placed on an accent-filled surface |
| `--hover-bg` | `rgba(255,255,255,0.08)` | `rgba(0,0,0,0.06)` | The standard focus-ring fill and many hover backgrounds |

> **Key rule.** The accent is **neutral**. There is no brand-colored accent in the UI chrome. The high-contrast blue you see in dropdown selection, sidebar badges and "compare" buttons is a functional hue applied via `#2563eb` fallbacks, not the chrome accent.

### Elevation
| Token | Dark | Light |
|-------|------|-------|
| `--shadow-sm` | `0 4px 12px rgba(0,0,0,0.3)` | `0 4px 12px rgba(0,0,0,0.1)` |
| `--shadow-md` | `0 6px 16px rgba(0,0,0,0.35)` | `0 6px 16px rgba(0,0,0,0.15)` |
| `--shadow-lg` | `0 8px 24px rgba(0,0,0,0.4)` | `0 8px 24px rgba(0,0,0,0.1)` |

Dropdown panels use `var(--shadow-md)`. Small cards/asides often use a literal `0 1px 2px rgba(0,0,0,0.04)`.

### Functional and feature tokens
| Token | Dark | Light | Role |
|-------|------|-------|------|
| `--warning-bg` | `#352306` | `#fef3c7` | Warning banners |
| `--warning-border` | `#5c3d0a` | `#f59e0b` | Warning banner border / icon |
| `--info-bg` | `#0d1f38` | `#eff6ff` | Informational notice banners |
| `--info-border` | `#1e3a5f` | `#bfdbfe` | Informational notice border / icon |
| `--info-text` | `#93c5fd` | `#1d4ed8` | Informational notice copy |
| `--skeleton-from/via/to` | `#2a2a2a/#333/#2a2a2a` | `#f0f0f0/#e0e0e0/#f0f0f0` | Skeleton shimmer stops |
| `--calendar-event-bg` | `#2563eb` | `#2563eb` | Calendar event chip |
| `--calendar-event-color` | `#ffffff` | `#ffffff` | Calendar event text |
| `--calendar-picker-filter` | `invert(1) brightness(1.5)` | `none` | Native date-picker icon tint |
| `--mail-folder-track-bg` | `#252525` | `#e8eaed` | Mail folder rail |
| `--mail-folder-active-bg` | `#333333` | `#e3e3e3` | Mail folder active |
| `--ideas-*` | warm notepad set | warm notepad set | Ideas tab notepad chrome (see `_themes.scss`) |

Do not invent new global tokens for one component. Reuse the set above or a documented feature token.

---

## 2. Typography

**Font: Poppins.** `$font-family-primary: 'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`.

Always inherit from body (`font-family: inherit`), never redeclare `font-family` in components. Interactive elements (buttons, inputs, triggers) must set `font-family: inherit` so they do not fall back to the UA font.

### Size scale (`$font-sizes`)
| Token | Value | Use |
|-------|-------|-----|
| `xs` | 12px | Labels, micro text, status badges, hints |
| `sm` | 13px | Table cells, dropdown rows, tile titles, compact body |
| `base` | 16px | Default body, header HOA name |
| `lg` | 20px | Card titles, modal headings |
| `xl` | 22px | Sub-page headings |
| `2xl` | 44px | Display |
| `3xl` | 54px | Display |
| `4xl` | 56px | Display |

### rem usage in real components (important)
Form chrome and tab content frequently set sizes directly in rem rather than via the map. The recurring ladder is:

| rem | px | Typical use |
|-----|----|-------------|
| `0.75rem` | 12px | overline labels, chips, hints, detail dl |
| `0.8125rem` | 13px | form labels, dropdown rows, menu items, detail values |
| `0.875rem` | 14px | form controls, body in tabs, list text |
| `0.9375rem` | 15px | aside titles, lead paragraphs |
| `1.0625rem` | 17px | form section titles |
| `1.125rem` | 18px | section titles |
| `1.25rem` | 20px | create-shell titles, success titles |

Match this when editing existing components; do not "upgrade" 13px labels to 16px.

### Weights (`$font-weights`)
| Token | Value | Use |
|-------|-------|-----|
| `normal` | 400 | Reading text, sub-titles |
| `medium` | 500 | Labels, tile titles, nav, controls |
| `semibold` | 600 | Section headings, table headers, card headers |
| `bold` | 700 | Display numbers, strong emphasis, PIN values |

Line height: `1.5` body, `1.2`–`1.4` headings and compact UI, `1.45`–`1.55` paragraphs inside asides.

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
| 15 | 60px | Large layout spacing |
| 20 | 80px | Extra-large layout spacing |

Compact dashboard defaults: table cell padding `8px`, dropdown row padding `8px 12px`, control padding `12px 12px` (or `8px 10px` for trigger rows).

---

## 4. Border Radius

| Token | Value | Use |
|-------|-------|-----|
| `$border-radius-sm` | 8px | Buttons, text inputs, table wrappers, search bars, status-filter triggers |
| `$border-radius-md` | 12px | Cards, modals (token-driven), asides, kind tiles, table containers, drop zones |
| `$border-radius-full` | 999px | Pills, chips, status badges, avatar status dots |
| literal `6px` | 6px | Compact controls: dropdown panels, datetime/select trigger rows, menu items, icon buttons, inline inputs, sidebar buttons |
| literal `4px` | 4px | Small inline chips, tiny clear buttons, inline title edit |
| literal `50%` | round | Avatars, status dots, action-icon circles |

`6px` is a first-class radius for interactive chrome, not an exception. Use `sm` (8px) for full-size inputs and buttons, `6px` for compact triggers/menus/dropdown panels, `md` (12px) for cards/panels/tables.

---

## 5. Buttons (global system, `_buttons.scss`)

There is one global button system. Reuse `.btn` plus a variant class; do not hand-roll button styles in component SCSS.

### Base `.btn`
```scss
display: inline-flex; align-items: center; justify-content: center;
gap: 8px;                       // spacing 2
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

Sizes: `.btn-sm` (8px 16px, 13px), `.btn-xs` (6px 12px, 12px), `.btn-lg` (16px 32px, 20px), `.btn-icon` (square 10px padding, 8px when `.btn-sm`), `.btn-block` (full width). On mobile, non-small buttons compress to `10px 20px / 13px`.

### Variants
| Class | Fill | Text | Border | Hover |
|-------|------|------|--------|-------|
| `.btn-primary` | `var(--text)` | `var(--panel)` | `var(--text)` | fill `var(--accent)`, lift `translateY(-2px)`, shadow |
| `.btn-secondary` | `var(--panel)` | `var(--text)` | `var(--border)` | fill `var(--bg)`, border `var(--text)`, lift `-1px` |
| `.btn-outline` | transparent | `var(--text)` | `var(--border)` | fill `var(--bg)`, border+text `var(--accent)`, lift `-1px` |
| `.btn-outline-primary` | transparent | `var(--accent)` | `var(--accent)` | fill `var(--accent)`, text `var(--panel)` |
| `.btn-ghost` | transparent | `var(--text)` | none (8px 12px) | fill `var(--bg-subtle)`, text `var(--accent)` |
| `.btn-link` | transparent | `var(--accent)` | none, underlined | text `var(--accent-hover)` |
| `.btn-danger` | `var(--panel)` | `#ef4444` | `#ef4444` | fill `#ef4444`, white text, red shadow |
| `.btn-success` | `#10b981` | `#fff` | `#10b981` | darken to `#059669` |
| `.btn-warning` | `#f59e0b` | `#fff` | `#f59e0b` | darken to `#d97706` |

`.cta-button` extends `.btn-primary` with semibold weight. `.btn-group` lays buttons in a row with `gap: 8px`; `.btn-group-justified` makes each `flex: 1`.

> The **primary button is a high-contrast neutral fill** (`var(--text)`), not a colored accent. This is the correct MMCC primary. A small hover lift (`translateY(-1px/-2px)`) plus a soft shadow is the standard affordance across variants.

---

## 6. Form Fields (canonical, `_dashboard-form-fields.scss`)

This is the shared form chrome used by every dashboard tab form (request/schedule tab, reports tab, vendor modals, future HOA forms). Prefer the `bc-dash-form__*` global classes in templates; use the `df` mixins when keeping legacy BEM prefixes (`@use '.../dashboard-form-fields' as df`).

### Field wrapper and label
```scss
.bc-dash-form__field { margin-bottom: 1rem; }          // df.field-spacing

.bc-dash-form__label {                                 // df.label
  display: block;
  font-size: 0.8125rem;        // 13px
  font-weight: 500;
  margin-bottom: 0.35rem;
  color: var(--text-muted);
}
```

### Control (input / select / textarea), `df.control($max-width: 420px)`
```scss
width: 100%;
max-width: 420px;                         // none under .bc-dash-form--wide / *--shell
padding: 12px 12px;                       // spacing 3 / 3
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
  box-shadow: 0 0 0 3px var(--hover-bg);  // the standard focus ring
}
&::placeholder { color: var(--text-muted); opacity: 0.6; }
&:disabled { opacity: 0.6; background: var(--bg); color: var(--text-muted); }
```
Textareas add `max-width: 560px; resize: vertical`.

### Field rows and halves
`.bc-dash-form__field-row` (`df.field-row`): flex, wrap, `gap: 16px`, `margin-bottom: 1rem`, stacks to column on mobile. Each `.bc-dash-form__field--half` (`df.field-half`) is `flex: 1 1 220px`.

### Trigger rows (datetime / inline-select pickers), `df.trigger-row`
```scss
display: flex; align-items: center; gap: 10px;
padding: 8px 10px;
border-radius: 6px;
border: 1px solid var(--border);
background: var(--panel);
transition: background-color .15s ease, border-color .15s ease;
// clickable: hover -> background var(--hover-bg), border var(--accent)
// open:      border var(--accent)
// focus:     box-shadow 0 0 0 3px var(--hover-bg)
```
Inside a trigger: `.bc-dash-form__trigger-placeholder` is 13px/500/muted; selected values render as `.bc-dash-form__pill` (radius 999px, `0.75rem`, `var(--hover-bg)` fill, `var(--border)`); a chevron (`.bc-dash-form__trigger-chevron`) rotates 180deg when open.

### Hints and errors
`.bc-dash-form__hint` (`df.hint`): 13px, muted, `margin-top: 0.35rem`, line-height 1.45. `.bc-dash-form__error`: `rgba(239,68,68,0.1)` fill, `#ef4444` text, radius sm, 13px.

### Radio/choice pills
Yes/No and option choices use selectable pills, not toggles: bordered (`var(--border)`), radius md, `var(--panel)` fill; hover gives accent border + `var(--hover-bg)`; `:has(input:checked)` gives accent border, `var(--surface)` fill and `box-shadow: 0 0 0 1px var(--accent)`. `accent-color: var(--accent)` on the input.

---

## 7. Dropdowns and Submenus (canonical, `user-selection-dropdown`)

This is the preferred dropdown pattern: a CDK connected overlay panel, optional search, grouped sections, rows with avatar + name + badge, an optional **second-level submenu** anchored to a row, and inline create forms that replace the list. Reuse this structure for any rich picker.

### Panel
```scss
background: var(--panel);
border: 1px solid var(--border);
border-radius: 6px;
box-shadow: var(--shadow-md);
width: 280px;                      // submenu panel: 300px
max-height: min(480px, 68dvh);
overflow: hidden;                  // inner list scrolls
animation: menuFadeIn 0.15s ease;  // opacity + translateY(-4px) -> 0
```
Opened via `cdkConnectedOverlay` (`hasBackdrop: false`, `push: true`, `flexibleDimensions: true`, `growAfterOpen: true`, `viewportMargin: 8`). Scrollbars are hidden (`scrollbar-width: none` + `::-webkit-scrollbar { display: none }`).

### Search row
`.menu-search`: flex, `gap: 8px`, `padding: 8px 12px`, `border-bottom: 1px solid var(--border)`. Icon 14px, muted, `opacity: 0.6`. Input is transparent and borderless, 13px, placeholder muted at 0.6 opacity.

### Section header
```scss
font-size: 10px; font-weight: 600;
text-transform: uppercase; letter-spacing: 0.5px;
color: var(--text-muted);
padding: 8px 12px 4px;
```

### Rows
```scss
.item {                                  // .mention-autocomplete-item
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; cursor: pointer;
  transition: background 0.1s ease;
  &:hover { background: var(--bg); }
  &.selected { background: color-mix(in srgb, var(--accent) 10%, transparent); }
}
```
Avatar: 20px circle (img or color placeholder via `avatar-color.util.ts`). Name: 13px/500, ellipsis. Badges next to the name (`.mention-user-badge`, `.mention-scope-badge`, `.mention-link-badge`): 10px/600, uppercase, `var(--bg)` or `color-mix` fill, radius 4px. Subtitle: 11px muted.

### Second-level submenu (the sub-dropdown)
A nested `cdkConnectedOverlay` anchored to the hovered/clicked row origin (`cdkOverlayOrigin` per row), 300px wide, same panel chrome. Used for vendor contacts: it lists contacts with medium chips (`.mention-medium-chip`, radius 10px, 11px) or inline SMS/Email/WhatsApp action buttons (`.mention-contact-action-btn`, 22px tall, 10px label). Below the list an "OR" divider (`.mention-or-divider`, 10px/600 uppercase with rule lines) plus a subtle "Add new contact" action.

### Action rows and inline create
Accent action rows (`.mention-action-row`, e.g. "Create new vendor"): 13px/500, `color: var(--accent)`, with a 20px "+" avatar; hover `var(--bg)`. Inline create forms render in-panel and replace the list: label `.mention-vendor-create-label` (11px/600), input `.mention-vendor-create-input` (radius 6px, 13px, `8px 10px`), and a pinned action bar (`Back` secondary + primary submit).

### Other dropdown styles in the app
The header HOA selector and several table menus use a lighter inline dropdown (`.organization-selector-dropdown` / `.dropdown-item`): `var(--panel)` panel, radius sm, `slideDown` animation, items padded `16px 20px`, active item tinted with accent text. For new rich pickers prefer the `user-selection-dropdown` structure above.

---

## 8. Header and Sidebar

### Dashboard header (`dashboard-header`)
Fixed, full width, height **64px**, `var(--panel)` background, `border-bottom: 1px solid var(--border)`, horizontal padding `20px` (spacing 5, `16px` on mobile), `z-index: 100`. Shifts down when the impersonation banner (48px) or developer toolbar (52px) is present.

- HOA label: `xs` (12px), 500, uppercase, muted.
- HOA name: `base` (16px), semibold, `var(--text)`.
- Theme toggle and icon buttons: 40x40, radius 8px, transparent, muted icon; hover `var(--bg)` + `var(--text)`; focus `2px solid var(--accent)`.
- Logo height 24px (desktop/mobile variants).

### Dashboard sidebar (`dashboard-sidebar`)
Fixed, below the header, `var(--panel)` background, `border-right: 1px solid var(--border)`, collapsed **56px** / expanded **180px** (width transitions `0.2s ease`), `z-index: 50`. Scrollbars hidden.

- Nav button (`.dashboard-sidebar-btn`): 36x32, radius 8px, transparent, muted; hover `var(--bg)` + `var(--text)`; **active = `var(--bg)` fill + `var(--text)`**; focus-visible = inset `0 0 0 2px var(--accent)`. Expanded: full width, left-aligned, icon 22px.
- Label (`.dashboard-sidebar-label`): 13px/500, ellipsis.
- Subtab button: min-height 28px, radius 8px, 12px/500, muted; active = `var(--bg)` + `var(--text)`.
- Badge (`.sidebar-badge`): accent fill (`var(--accent, #2563eb)`), `var(--panel)`/`var(--text-on-accent)` text, 11px/600, radius 9px.
- Separators: 1px `var(--border)` with `8px` vertical margin. Footer section pinned to bottom with a top border.

---

## 9. Tables (project-detail bids table, schedule table)

```scss
// Wrapper
border: 1px solid var(--border);
border-radius: vars.$border-radius-md;   // 12px
background: var(--surface);
overflow-x: auto;                        // scroll on narrow viewports

// Header row
thead { background: var(--panel) (or var(--bg)); }
th {
  padding: 8px; text-align: left; white-space: nowrap;
  font-size: 13px–14px; font-weight: 600;     // semibold
  color: var(--text);
  border-bottom: 2px solid var(--border);
}

// Body
tr {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  transition: ...;
  &:hover { background: var(--hover-bg); }     // bids table uses var(--bg)
  &:last-child { border-bottom: none; }
}
td { padding: 8px; color: var(--text); vertical-align: middle; }
```

Cell action icon buttons: ~37.5px square (or 2rem), `var(--panel)` fill, `1px solid var(--border)`, radius 6px, muted icon; hover `var(--bg)` + accent border. Row action menus and "more" (`…`) overflow buttons follow the same 2rem icon-button chrome. Inline cell editing (e.g. bid title) swaps a text-like trigger for a bordered input with the standard accent focus ring. Empty state: centered, muted, italic, generous padding.

---

## 10. Other Component Patterns

### Cards and asides
```scss
@mixin card { background: var(--panel); border: 1px solid var(--border);
              border-radius: vars.$border-radius-md; padding: 20px; }
```
"How it works" asides: padding 16px, radius md, border, `var(--panel)`, soft `0 1px 2px rgba(0,0,0,0.04)` shadow. Aside title 15px/600; lead/list text 14px muted, line-height 1.5.

### Selectable tiles (kind picker)
Left-aligned, not centered: `flex: 1 1 0`, padding `1.125rem 1.25rem`, radius md, border, `var(--panel)`; hover border `var(--accent)` + `var(--hover-bg)`; focus-visible ring `0 0 0 3px var(--hover-bg)`. Label 15px/600, hint 13px muted. Lay tiles out in a wrapping row (`gap: 0.75rem`).

### Two-column form layout
Form on the left, "How it works" aside on the right:
```scss
display: grid;
grid-template-columns: minmax(0, 1fr) minmax(15rem, 22rem);
gap: 1.25rem; align-items: start;
@media (max-width: 960px) { grid-template-columns: 1fr; }
```
The aside can be `position: sticky; top: 12px` on wide viewports.

### File drop zone
Dashed `2px var(--border)`, radius md, `var(--surface)`, centered column, `min-height: 7.5rem`. Active: accent border + `color-mix(in srgb, var(--accent) 6%, var(--surface))` fill + `0 0 0 1px` accent ring. `focus-within`: `2px solid var(--accent)` outline. Thumbnail grids: `repeat(6,1fr)` desktop, 4 on tablet, 2 on small; remove button is a red circle revealed on hover.

### Section labels (overline)
12px (or 0.75rem), 600, uppercase, `letter-spacing: 0.04em–0.5px`, muted.

### Detail lists
`dl` grid: `grid-template-columns: minmax(10rem, 14rem) 1fr`, 13px; `dt` muted/500, `dd` `var(--text)` with `word-break`.

---

## 11. Status Badges (functional color, the colored exception)

Pill shape, `border-radius: 999px`, `padding: 4px 12px` (spacing 1/3), `font-size: xs` (12px), `font-weight: medium`, `white-space: nowrap`. Color is hardcoded hex by design (functional meaning, not chrome).

Real families in use:
```scss
// success / approved
background: rgba(34,197,94,0.2);  color: #15803d;   // or #16a34a
// info / processing
background: rgba(56,189,248,0.2); color: #0284c7;
// warning / draft
background: rgba(234,179,8,0.22); color: #a16207;
// error / denied
background: rgba(239,68,68,0.2);  color: #dc2626;
// neutral / completed
background: rgba(100,116,139,0.2); color: #475569;  // slate
// muted / default
background: rgba(148,163,184,0.2); color: #64748b;
```
Use these only for functional state (green = success, blue = in-progress/info, amber = pending/warning, red = error/denied, slate = closed/neutral). Never use a colored badge purely decoratively.

---

## 12. Modal Shell (obligatory, `_modal-shell.scss` + `app-modal-shell`)

All modals use the structural shell, never a bespoke overlay. Layout invariant: **fixed header, scrollable body only, fixed footer.**

```scss
.bc-modal-host   { position: fixed; inset: 0; display: flex; justify-content: center;
                   align-items: flex-start; overflow-y: auto; pointer-events: none; }
.bc-modal-backdrop { position: absolute; inset: 0; background: var(--bc-modal-backdrop-color);
                     backdrop-filter: blur(var(--bc-modal-backdrop-blur)); }
.bc-modal-panel  { width: min(768px, calc(100vw - 1rem));   // --lg: 920px; fullscreen variant
                   max-height: var(--bc-modal-panel-max-height);
                   background: var(--bc-modal-panel-bg);
                   border-radius: var(--bc-modal-panel-radius);
                   border: 1px solid var(--bc-modal-border);
                   box-shadow: var(--bc-modal-panel-shadow);
                   display: flex; flex-direction: column; overflow: hidden; }
.bc-modal-body   { flex: 1; min-height: 0; overflow-y: auto; padding: var(--bc-modal-body-padding); }
.bc-modal-footer { flex-shrink: 0; padding: var(--bc-modal-footer-padding);
                   border-top: 1px solid var(--bc-modal-border); }
```
Footer actions render in a wrapped, end-aligned row with `gap: 0.75rem`. An empty footer (no projected content) collapses to nothing. Use `bodyPadding="none"` (`--body-flush`) for full-bleed layouts. Modal sizing/blur/radius come from `_modal-tokens.scss`; stacking z-index from `_modal-layers.scss`. The CDK overlay teleports to `document.body` to avoid `transform`/`filter` stacking bugs. See `src/app/shared/CLAUDE.md` for the `app-modal-shell` contract.

---

## 13. Breakpoints and Responsive

| Name | Mixin | Width |
|------|-------|-------|
| Mobile | `@include mix.mobile` | <=767px |
| Tablet | `@include mix.tablet` | 768–1023px |
| Desktop | `@include mix.desktop` | >=1024px |
| Tablet-up | `@include mix.tablet-up` | >=768px |

Components also use ad-hoc `@media (max-width: 960px)` (two-column form collapse) and `640px` (thumbnail grids). Dashboard form rows stack to a single column on mobile.

---

## 14. Transitions

```scss
$transition-fast: 0.15s ease;   // hover states, border/background on triggers, chevron rotation
$transition-base: 0.3s ease;    // buttons (all), background/color theme transitions
```
Use `@include mix.transition($property, $duration)` for the standard helper. Dropdown row hovers use a quicker `0.1s ease`. Menu fade-in is `0.15s`.

---

## 15. Do and Don't

### Do
- Use CSS custom properties for all chrome color: `var(--text)`, `var(--border)`, `var(--panel)`, `var(--hover-bg)`.
- Use `font-family: inherit` everywhere (Poppins cascades from body).
- Use `map.get(vars.$spacing-scale, N)` for spacing; reuse the rem ladder in section 2 when matching existing form chrome.
- Use the global `.btn` + variant classes; the primary action is `.btn-primary` (`var(--text)` fill).
- Use the `bc-dash-form__*` classes / `df` mixins for any dashboard form.
- Reuse the `user-selection-dropdown` structure for rich pickers, including the second-level submenu.
- Use `var(--hover-bg)` for hover fills and as the `0 0 0 3px` focus ring.
- Use status-badge colors only for functional state.
- Use `app-modal-shell` for every modal.

### Don't
- Don't hardcode chrome colors (`#111`, `#fff`, raw `rgba(255,255,255,...)`). Functional status hex and the `#2563eb` interactive-blue fallbacks are the only allowed literals.
- Don't paint the chrome accent a brand color; the accent token is neutral.
- Don't import Inter, Berkeley Mono, or any font other than Poppins. Do not set `font-feature-settings: "cv01","ss03"` or weights like 510/590; Poppins supports 400/500/600/700 only. (Note: the legacy "Inter Variable / weight 510 / semi-transparent white borders" wording in some older CLAUDE.md and rule files is stale and contradicts the shipped UI; this document is authoritative.)
- Don't restyle buttons in component SCSS; extend the global system.
- Don't build bespoke modal overlays; use the shell.
- Don't enlarge compact type (13px labels, 14px controls) to 16px.
- Don't use the em dash character anywhere.

---

## 16. Imports in Component SCSS

```scss
@use 'sass:map';
@use '../../../../../../styles/variables' as vars;            // adjust depth
@use '../../../../../../styles/mixins' as mix;                // when using mixins
@use '../../../../../../styles/dashboard-form-fields' as df;  // when building forms
```
Reference: `vars.$spacing-scale`, `vars.$border-radius-sm/md/full`, `vars.$font-sizes`, `vars.$font-weights`, `vars.$transition-fast/base`; `mix.mobile/tablet/desktop/transition/card/flex-center/flex-between`; `df.label/control/field-row/field-half/trigger-row/hint`.
