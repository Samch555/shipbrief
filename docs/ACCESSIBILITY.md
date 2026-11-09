# Accessibility check (2026-11-09)

Method: manual review plus computed WCAG contrast ratios and headless-Chrome renders at 1280px and 390px, in light and dark. No automated axe run was possible offline. Re-check with Lighthouse or axe DevTools after deploying.

| Check | Result |
|---|---|
| Colour contrast (all text/background token pairs, both themes) | Lowest 5.5:1 (muted text on secondary surface, light theme). All pairs ≥ 4.5:1 (WCAG AA). |
| Landmarks | `header`, `nav`, `main`, `footer`. Each section has `aria-labelledby` pointing at its heading. |
| Skip link | "Skip to content" appears on focus and jumps to `#main`. |
| Keyboard | Every control is a native `button`, `a`, or `details/summary`. `:focus-visible` gets a 3px outline. |
| Toggles | Filter chips and the theme toggle expose state with `aria-pressed`. |
| Live feedback | Copy result is announced through `role=status aria-live=polite`. |
| Headings | h1 (product) → h2 (day and sections) → h3 (cards), with no skipped levels. |
| Touch targets | Buttons ≥ 36px, chips ≥ 32px, the filter summary ≥ 44px. |
| Motion | No animations. `prefers-reduced-motion` is respected anyway. |
| Zoom / reflow | Single column at 390px with no horizontal scroll. Text uses relative units. |
| Language / colour scheme | `lang="en"`, `color-scheme: light dark`. The theme follows the OS, with a manual override. |
| Links | Open in a new tab with `rel="noopener noreferrer"`. Link text is descriptive (title, "Source", "Discussion"). |

Known gaps:
- External links opening in a new tab aren't announced as such.
- The relative times ("3h ago") rely on the `datetime` attribute for exact values.
