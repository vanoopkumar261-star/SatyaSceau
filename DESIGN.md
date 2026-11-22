# SatyaSceau design system (locked)

Source: the team's Stitch design system (`refernces/stitch_satyasceau_upi_verification_app/satyasceau_design_system.md`) and reference image, made concrete in `backend/static/css/theme.css`. Every page links that one stylesheet; page `<style>` blocks only lay out their own screen.

## Direction
A payment witness at an Indian shop counter. The people using it are a shopkeeper or rider mid-handover, reading the screen from a metre away; a customer in a hurry, one thumb; a judge opening a certificate. It should feel calm, plain and trustworthy, like a clean ledger next to a lemon highlighter.

- **Signature, "the witness slip":**
  - a lemon slip carries the figure that matters: today's witnessed total, the customer's payment, the home hero
  - UTRs are passbook entries (grouped `4318 7650 9123`, Source Code Pro)
  - a seal mark (ring + check) stamps every verified card and certificate
- **Colour has jobs:**
  - sage canvas, paper cards and ink actions are structure
  - lemon is the one highlight
  - green, amber and red mean only VERIFIED, WAITING and NOT VERIFIED, always with an icon and a word

## Tokens (`:root` in theme.css; dark values under `prefers-color-scheme: dark`)
| Token | Light | Dark | Job |
|---|---|---|---|
| `--sage` | #E2F3E9 | #0B1410 | page canvas |
| `--sage-2` | #F2FAF5 | #172820 | inset fields, quiet fills |
| `--paper` | #FFFFFF | #122019 | cards |
| `--ink` | #0F172A | #ECFDF5 | text, primary pill |
| `--ink-2` | #3F5549 | #9BB5A6 | supporting text |
| `--ink-3` | #647A6E | #7E9A8B | meta |
| `--rule` | #CBE2D5 | #263E32 | hairlines |
| `--highlight` | #F7FA66 | #E8EC4F | the lemon slip |
| `--teal` | #0F766E | #5EEAD4 | links, focus |
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
