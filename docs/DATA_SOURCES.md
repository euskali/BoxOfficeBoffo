# Data Sources

Status key: ✅ use in MVP · 🔜 later phase · 📚 reference/manual · ⚠️ terms restrict use

BoxOfficeBoffo is a **non-commercial hobby project**. Several sources below are free *only* for non-commercial use. If that ever changes, revisit this file first.

## Core (MVP)

| Source | What | Coverage | Terms | Status |
|---|---|---|---|---|
| **Purdue `stat695data` (`mojo.rda`)**, github.com/schloerke/stat695data | Box Office Mojo weekend charts scraped Mar 2017: rank, weekend gross, theaters, **cumulative total gross**, release date, genre, MPAA, legacy Mojo id | 1982–2016, 116,663 rows, 13,499 releases | MIT (package); underlying facts from Mojo | ✅ |
| **Wayback Machine** (CDX API) | Archived Box Office Mojo weekend chart pages (new-style URLs `/weekend/YYYYWnn/`) | 2019 redesign → present, plus old-style pages before that | Archive.org terms; be polite | ✅ |
| **Box Office Mojo** (live) | Weekend charts, release pages with IMDb `tt` links | 1982 → present | IMDb terms prohibit scraping. Opt-in fallback only: cached, rate-limited | ⚠️ |
| **IMDb non-commercial datasets**, datasets.imdbws.com | `title.basics`, `title.crew`, `title.principals`, `name.basics` | All titles and people | Personal / non-commercial use | ✅ |
| **FRED `CPIAUCSL`** (BLS CPI-U) | Monthly CPI | 1947 → present (BLS annual back to 1913) | Public domain | ✅ |
| **Average ticket price history** | Annual US avg ticket price | 1910 → present | Facts; cite NATO / Mojo table used | ✅ (manual CSV) |

## Helpful extras

| Source | What | Notes | Status |
|---|---|---|---|
| **heike/classdata `mojo`** (R pkg, GitHub) | Mojo weekend charts scraped Sep 2018 | 2013–2018, about 31.7k rows. Use to cross-check or fill 2017–2018 | 🔜 |
| **Common Crawl** (index.commoncrawl.org) | Raw HTML of crawled pages, including boxofficemojo.com | Good coverage ~2013→present. Includes **pre-Oct-2019 Mojo pages** (people charts, inflation-adjusted charts) that are gone from the live site. Free, no key | 🔜 |
| **Wayback Machine, old Mojo** | `boxofficemojo.com/people/…`, `/alltime/adjusted.htm`, `/movies/?id=…` | Validate person rollups and adjusted rankings against what Mojo showed | 🔜 |
| **R `boxoffice` package** (CRAN) | Daily scraper for Mojo / The Numbers | A daily-granularity reference implementation for Phase 4 | 🔜 |
| **TMDB API** | Lifetime worldwide revenue, budget, posters | Free non-commercial with attribution; 6-month cache limit | 🔜 |
| **Wikidata** (P2142 box office) | Lifetime grosses with qualifiers | CC0, inconsistent coverage | 🔜 |
| **Wikipedia "box office number-one films in the US" lists** | Weekly #1 film, 1948→present (pre-1982 = Variety National Boxoffice Survey) | CC BY-SA text; facts free. Great for pre-1982 #1 history | 🔜 |

## Pre-1982 / deep history (Phase 3)

| Source | What | Notes |
|---|---|---|
| **Media History Digital Library / Lantern**, lantern.mediahist.org | Scanned Variety, Film Daily, Boxoffice, Motion Picture Herald, etc. | Public domain, mostly pre-1964. OCR text; full volumes downloadable via Internet Archive |
| **Boxoffice magazine back issues** (Internet Archive, Online Books Page) | Weekly trade issues and the annual *Boxoffice Barometer* | Free scans |
| **Variety anniversary editions**, worldradiohistory.com | Annual issues with the all-time rental champs list | Free scans |
| **Books** 📚 | Finler, *The Hollywood Story* (2003) and *All-Time Box-Office Hits* (1985); Steinberg, *Reel Facts* (1982); Sackett, *Hollywood Reporter Book of Box Office Hits* (1996); *Art Murphy's Box Office Register* (annual from 1984) | Library / Internet Archive lending. Extract figures manually with page citations |

**Big caveat for old data:** until the 1970s–80s, trades reported **distributor rentals**, not box office grosses. Store them with `is_rental=true` and never mix them silently with grosses.

## Commercial (not used; for reference)
- **OpusData / The Numbers**: licensed API. The site's terms reserve scraping and redistribution, "commercial or otherwise", to licensees.
- **IMDb + Box Office Mojo on AWS Data Exchange**: enterprise contract.
- **Rentrak** (formerly Comscore Movies; sold to Advaya Capital in May 2026): industry source of truth, studio-only.

## Etiquette for anything fetched
- Cache everything in `data/raw/` and never re-fetch what's cached.
- At least 5 s between live requests, and a User-Agent that names the project and repo URL.
- Prefer archives (Wayback, Common Crawl) over hitting live sites.
- Credit sources on the About page and in the footer.
