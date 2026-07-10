# DESIGN.md — Control-Plane Design System

The editor is a tool a non-technical marketer uses for hours. Optimize for
legibility, low visual noise, and obvious affordances. The live preview is the
star; the chrome recedes. Every screen is assembled from the tokens and
components below — no ad-hoc colors, sizes, or spacing.

Tokens live in `static/css/tokens.css`; components in `static/css/app.css`.

## Hard rules (non-negotiable)

- **No purple, violet, or indigo. Anywhere.**
- **Light UI only.** No dark theme, no dark-mode-by-default.
- No gradient heroes, glassmorphism/blur-behind, rainbow gradients,
  drop-shadow overload, everything-rounded-3xl, or emoji as UI icons.
- App screens are **left-aligned and content-first** — no centered-template
  look. (Exception: the auth card and empty-state copy may center.)
- Hairline borders over shadows. Shadows only on true overlays (menus, dialogs).
- Every interactive element has hover / focus / active / disabled states, with
  a **visible keyboard focus ring** (2px accent outline).
- Accessibility is part of done: semantic HTML, WCAG AA contrast, full
  keyboard nav, real `<label>`s.
- Motion is subtle and functional (120ms ease on state changes), never
  decorative.

## Palette — "Neutral gray + forest green" (client-approved 2026-07-11)

True-gray neutral base, one accent, clear semantics. Quiet and trustworthy.

| Token | Hex | Use |
|---|---|---|
| `--color-bg` | `#FAFAFA` | Page background |
| `--color-surface` | `#FFFFFF` | Panels, cards, inputs |
| `--color-subtle` | `#F4F4F5` | Wells, hovers, table stripes |
| `--color-border` | `#E4E4E7` | Hairlines |
| `--color-border-strong` | `#D4D4D8` | Input borders |
| `--color-text` | `#18181B` | Primary text |
| `--color-text-secondary` | `#52525B` | Secondary text |
| `--color-text-muted` | `#71717A` | Metadata only (AA at 14px+) |
| `--color-accent` | `#166534` | Buttons, links, focus, active nav |
| `--color-accent-hover` | `#14532D` | Hover |
| `--color-accent-tint` | `#F0FDF4` | Selected/active backgrounds |
| `--color-success` | `#15803D` | Published, webhook OK |
| `--color-warning` | `#B45309` | Drafts, pending TLS |
| `--color-error` | `#B91C1C` | Failures, destructive actions |

The accent is the **only** brand color. If a screen needs a second hue,
the answer is a neutral or a semantic color, not a new brand color.

## Type

**IBM Plex Sans** (vendored woff2: 400 / 500 / 600) with system-ui fallback;
**IBM Plex Mono** for code, subdomains, and HTML snippets.

| Token | Size | Use |
|---|---|---|
| `--text-xs` | 12px | Badges, table headers |
| `--text-sm` | 13px | Labels, help text |
| `--text-base` | 14px | UI default |
| `--text-md` | 16px | Emphasized body |
| `--text-lg` | 18px | Panel titles |
| `--text-xl` | 21px | Page titles |
| `--text-2xl` | 26px | Rare display |

Line-height 1.5 body / 1.25 headings. Weights: 400 body, 500 labels/buttons,
600 headings. One weight jump at a time; hierarchy comes from size + weight +
color, not decoration.

## Space, shape, motion

- Spacing scale (4px base): `--space-1..8` = 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.
- Content max-width `64rem`, left-aligned; generous vertical rhythm
  (`--space-6` above page headers).
- Radius: 4px (small controls, badges), 6px (buttons, inputs, panels). Nothing larger.
- Motion: `--transition-fast` (120ms ease) on background/border color only.

## Icons

Lucide (lucide.dev) line icons only, via the sprite `static/icons.svg`,
rendered at 16px (`.icon`) or 20px (`.icon-lg`), `stroke-width: 2`,
`currentColor`. Add icons by appending `<symbol>`s to the sprite — never
inline one-off SVGs or emoji.

## Components (app.css)

`.btn` (`-primary` / `-secondary` / `-quiet` / `-danger`) · `.input` /
`.select` / `.textarea` + `.label` / `.help` / `.error-text` in a `.field` ·
`.panel` (+ `.panel-body`) · `.alert` (`-error` / `-success`) · `.badge`
(`-success` / `-warning` / `-error`) · `.table` · `.topnav` · `.page-header` ·
`.empty-state` · `.auth-layout` / `.auth-card` · `.container` / `.stack`.

Extend the system here first, then use it — screens never define their own
one-off variants.

## UX map (screens to design against, per architecture.md)

1. **Sites/funnels list** → site detail (pages within the funnel).
2. **Import**: paste/upload HTML → progress → annotation review
   (confirm/rename/add/remove fields).
3. **Editor**: live preview iframe (the star) + side panel of grouped, labeled
   fields; click-to-locate both ways.
4. **Countdown wiring**: date+time picker, timezone, plain-English
   "when it hits zero…" select.
5. **Form wiring**: webhook URL, success page dropdown (+ "new thank-you page"
   shortcut), resilience toggle.
6. **Publish**: draft/published status, history, one-click rollback.

Design for the non-technical marketer: plain-language labels ("When the timer
hits zero…", not "on_expiry"), obvious primary action per screen, no jargon.
