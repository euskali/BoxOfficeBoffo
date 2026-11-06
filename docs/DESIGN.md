# Design Direction — "Web 1.0, built with Tailwind"

**The vibe:** a late-90s / early-2000s movie fan site. Think old GameFAQs, eeggs.com, Movie Mistakes, the original Box Office Mojo, and the forums of that era. It should be **dense, text-first, table-heavy and a little nerdy**, made by someone who loves the data.

**The rule:** it *looks* like 1999 but *works* like 2026. It's fast, responsive, accessible and keyboard-friendly, with instant search. The nostalgia is in the styling, never in the usability.

Inspiration only: don't copy any real site's logo, name, or exact layout.

---

## Stack
- **Tailwind CSS v4** with a custom theme (tokens below). No component library that brings a modern look (no shadcn defaults, no rounded-2xl cards).
- System fonts only (no webfont loading).
- Small hand-made pixel icons/GIF-style badges as SVG or PNG in `site/public/img/`.

## Design tokens (Tailwind theme)
| Token | Value | Use |
|---|---|---|
| `--color-page` | `#FFFFFF` (light) / `#000033` (dark) | page background |
| `--color-ink` | `#000000` / `#E6E6E6` | body text |
| `--color-link` | `#0000CC` | links, always underlined |
| `--color-visited` | `#551A8B` | visited links (yes, really) |
| `--color-bar` | `#003366` | section header bars (white bold text) |
| `--color-bar-alt` | `#336699` | sub-headers |
| `--color-row` | `#FFFFFF` / `#EEEEEE` | zebra rows |
| `--color-hl` | `#FFFFCC` | highlighted row ("you are here" film in a leaderboard) |
| `--color-new` | `#CC0000` | "NEW!" / "UP" badges |
| `--color-down` | `#006600` | — (pick a clear up/down pair; never rely on color alone, use ▲▼ arrows too) |
| font body | `Verdana, Tahoma, Geneva, sans-serif` at 13px | everything |
| font small | 11px | table meta, footers |
| font mono | `"Courier New", Courier, monospace` | FAQ-style text blocks, "data notes" |
| radius | `0` everywhere | no rounded corners |
| borders | 1px solid `#999`, or `outset`/`inset` 2px bevels for buttons | |

Dark mode is optional but fun: navy background, light text, cyan links, like a late-90s "dark theme" fan page.

## Layout patterns
- **Fixed-width feel, fluid in reality.** Center a container with a max width of about 980px. On mobile, collapse the sidebar under the content. Never horizontal-scroll the page, only wide tables inside their own scroll box.
- **Top banner:** the "BoxOfficeBozo" wordmark in bold Verdana or Georgia, a tagline ("Box office history, as it happened"), and a thin nav bar of text links separated by `|`.
- **Left sidebar boxes** (desktop): each box has a navy header bar ("SEARCH", "THIS WEEKEND IN 1993", "TOP DIRECTORS", "SITE NEWS"), with bulleted text links inside.
- **Section header bars:** full-width navy bar, white bold small-caps text, with an optional `»` prefix.
- **Tables are the star:** dense zebra rows, a sticky header, right-aligned numbers in tabular-nums, sortable headers with ▲▼, and the current film highlighted in pale yellow.
- **"Data notes" blocks:** monospace text in a bordered box, like a GameFAQs FAQ excerpt, explaining methodology and caveats.
- **Footer:** "Last updated: Mon Nov 9 2026", a static joke hit counter, a "Best viewed in any browser" badge, a source credits line, and a link to the GitHub repo.

## Signature details (use sparingly; charm, not clutter)
- 88×31 badge buttons in the footer, all made for this site ("Powered by DuckDB", "Made w/ Notepad", "Data: Wikidata").
- `NEW!` badge on newly released films in weekend charts.
- Beveled `[ Go ]` buttons with outset borders that turn inset on press.
- A `<hr>` styled as a 3D groove.
- A "What's New" changelog box in the sidebar, dated entries.
- Breadcrumbs like `Home > Films > T > Titanic (1997)`.
- An A–Z letter bar for browsing films and people.
- Optional "webring" footer link to other movie data hobby sites.

## Things NOT to do
- No blinking/marquee text (accessibility). A static "marquee-looking" ticker strip is fine if it doesn't move or respects `prefers-reduced-motion`.
- No auto-playing audio, no splash page, no frames.
- No low-contrast "retro" color combos. All text must meet WCAG AA.
- No fake popups.

## Charts
- Line charts (rank over time, cumulative gross) in a deliberately plain style: white background, gray 1px grid, a single strong line color, square markers, and an axis in Verdana 11px. They should look like a 2002 Excel chart exported as a GIF, but stay interactive (hover tooltips styled as a yellow `title`-style box).
- Use uPlot or Observable Plot for a small bundle; style the chart, not the library chrome.

## Key screens (MVP)
1. **Home:** search box, "This weekend in history" (same weekend N years ago), the current all-time top 10, and site news.
2. **Film page:** header table (title, year, distributor, release date, lifetime totals), a **date picker + measure toggle**, a leaderboard slice around the film at that date (±10 ranks, film highlighted), a rank-over-time chart, and the film's weekend-by-weekend table.
3. **All-time leaderboard as of a date:** date picker, measure toggle (Nominal / CPI-adjusted / Admissions), filters (release year range), and top 100 with "rank change vs 1 year earlier".
4. **Person page:** career totals as of a date, rank among directors/actors as of that date, and filmography table.
5. **Weekend chart:** any weekend 1982→present, laid out like an old Mojo weekend chart.
6. **About / Data notes:** sources, methodology, caveats, and credits in monospace FAQ style.
