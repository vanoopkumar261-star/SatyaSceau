# SatyaSceau design system (locked)

Source: the team's Stitch design system (`refernces/stitch_satyasceau_upi_verification_app/satyasceau_design_system.md`) and reference image, made concrete in `backend/static/css/theme.css`. Every page links that one stylesheet; page `<style>` blocks only lay out their own screen.

## Direction
A payment witness at an Indian shop counter. The people using it are a shopkeeper or rider mid-handover, reading the screen from a metre away; a customer in a hurry, one thumb; a judge opening a certificate. It should feel calm, plain and trustworthy, like a clean ledger next to a cream highlighter.

- **Signature, "the witness slip":**
  - a cream slip carries the figure that matters: today's witnessed total, the customer's payment, the home hero
  - UTRs are passbook entries (grouped `4318 7650 9123`, Source Code Pro)
  - a seal mark (ring + check) stamps every verified card and certificate
- **Colour has jobs:**
  - sky-blue canvas, paper cards and navy actions are structure
  - cream (#FDF5AA) is the one highlight; the palette is two colours, navy blue and cream
  - green, amber and red mean only VERIFIED, WAITING and NOT VERIFIED, always with an icon and a word

## Tokens (`:root` in theme.css; dark values under `prefers-color-scheme: dark`)
| Token | Light | Dark | Job |
|---|---|---|---|
| `--sage` | #EAF2F8 | #0A1C2E | page canvas (sky-blue wash / deep navy) |
| `--sage-2` | #F5F9FC | #12283F | inset fields, quiet fills |
| `--paper` | #FFFFFF | #0F2438 | cards |
| `--ink` | #113F67 | #F3F8FC | text, primary pill (navy) |
| `--ink-2` | #34699A | #A9C6DD | supporting text (blue) |
| `--ink-3` | #4A6F90 | #87A8C3 | meta |
| `--rule` | #C9DCEB | #1F3C5A | hairlines |
| `--highlight` | #FDF5AA | #FDF5AA | the cream slip |
| `--teal` | #34699A | #58A0C8 | links, focus, accents (blue) |
| `--ok / --ok-tint` | #15803D / #DCFCE7 | #4ADE80 / #052E16 | verified |
| `--wait / --wait-tint` | #B45309 / #FEF3C7 | #FBBF24 / #451A03 | waiting |
| `--no / --no-tint` | #B91C1C / #FEE2E2 | #F87171 / #450A0A | not verified |

- **Type:**
  - Faces: Noto Sans (UI) and Noto Sans Devanagari (Hindi) share one stack; Source Code Pro is for UTRs and hashes.
  - Scale, ratio 1.25: 12 · 14 · 16 · 18 · 22 · 28 · 36 · 44.
  - Amounts are 800 weight with `tabular-nums`.
  - Hierarchy comes from weight and colour before size.
- **Space:** a 4px base; card padding is 20–24px; page gutter is 16px on phones.
- **Radius:** 12 for controls, 16 for inner tiles, 24 for cards, 28 for the hero slip, 9999 for pills and chips (concentric when nested).
- **Depth:** whisper-quiet layered shadows in light mode; a single 1px ring in dark mode. No glass, no gradients for decoration.
- **Icons:** Material Symbols Outlined, `aria-hidden`, next to a word. Never emoji.
- **Motion:** 150ms ease-out on `transform` and `opacity` only; `prefers-reduced-motion` drops movement.
- **Touch:** every control is at least 44px, and primary pills are 48px.

## Rules
- Every colour and font goes through a token.
- No eyebrow labels and no tracked capitals.
- One primary action per view.
- Every interactive element gets `:focus-visible`, hover, active and disabled states.
- Pages keep every id, `data-*` attribute and class hook their scripts use (see each page's script).
