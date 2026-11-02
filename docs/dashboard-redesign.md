# Dashboard redesign — decisions

Status: **design and visual direction agreed, not implemented.**
Mock: [`docs/mock/index.html`](mock/index.html) — open it from disk, no server needed.

Chosen direction: **"Ledger + rail"** (variant `e` in the mock). The existing paper
ground, teal-black ink and IBM Plex Serif figures are kept; the filters move into a
persistent left rail rather than dropdowns, so no filter value is hidden behind a
menu. Rejected: a dark treatment, a monospaced high-density table, and a card list.

The brief: the page explains too much. Scores, meters and percentages that the owner
cannot read at a glance are worse than useless, because an unreadable number still
looks authoritative. Everything below follows from replacing indices with rupees.

## What the page becomes

One table, five columns:

| Product | Specification | Price here | Est. Apple landed | Difference |
|---|---|---|---|---|

The difference is a plain subtraction in rupees, set as the largest element on the
row. Sorted by it, the best buy is simply the top row. Nothing else ranks anything.

### Decisions

- **No status pill.** 147 of the 154 listings with an Apple estimate are cheaper than
  it; the median gap is 25%. Any pill driven by that gap is green on almost every
  row, which communicates nothing. Rejected in favour of the raw number.
- **No composite deal score, no meters, no confidence count.** Removed from the page.
- **No hero cards.** The table sorted by difference is the ranking. A second ranking
  above it would only need reconciling with the first.
- **Three comparisons survive, as rupee facts rather than 0–100 scores**, and move
  into the row drawer:
  - price against the Apple estimate (also the `Difference` column),
  - price against listings of the identical specification,
  - the shop's markdown from its own earlier price.
- **Dropped signals:** `vs_history` as a score (the chart replaces it) and
  `spec_value` (see *Price per GB*, below).

### Filters

Family tabs — Everything / MacBook Pro / MacBook Air / iPhone — then a left rail of
multi-select checkboxes grouped by Model, Chip, Memory, Storage and Colour. Each
group lists only values present in the current tab, with live counts computed with
that group's own selection lifted, so ticking one value does not zero the rest of
its group. Applied filters also appear above the table as dismissible chips.

Multi-select was chosen over single-select so two chips or two capacities can be
compared side by side in one view.

### Price chart

In the row drawer. **Plotted against real time, not run number** — six checks three
hours apart must not draw the same picture as six checks six months apart. The
current sparkline plots by index and would.

The chart answers "has this been steady, or did it move" and nothing else. No
percentage claims, no median.

**There is no history yet.** All six runs in `history.json` fall on 16 Sep 2026
between 00:22 and 03:19. Until the daily job has built a real span, the drawer says
so in words rather than drawing a trend across three hours. The mock also shows a
clearly-labelled invented series so the chart could be judged as a design.

## Data problems this surfaced

These are in the scraped data, not the dashboard, and need fixing in `normalize.py`.

1. **iPhone chip labels are inconsistent.** `A19` and `Apple A19` are the same chip,
   as are `A19 Pro` and `Apple A19 Pro`. Ten distinct chip values collapse to eight
   once the `Apple ` prefix is stripped. Without this the Chip filter shows a value
   twice.
2. **iPhone `color` is often a list of every colour the model comes in**, e.g.
   `"Silver, Cosmic Orange, Deep Blue"` — not this listing's colour. Treated as
   unknown rather than filtered on.
3. **7 of 160 single-colour listings contradict their own title** — the name ends
   "Space Black" while `data-color` says `Silver`. Proposed rule: when the attribute
   colour does not appear in the name, record no colour. Seven rows lose a colour;
   no row gets a wrong one.
4. **Identical specifications frequently share an identical price.** Three listings
   at PKR 772,000 for the same MacBook Pro 14 config. "This is the cheapest" is a
   distinction the prices do not support, so ties are stated as ties.

## Deferred, deliberately

- **Upgrade ladders.** What each RAM and storage step costs here versus Apple's
  estimated step — `+120,000 for +24 GB, Apple charges about +111,000`. Agreed as a
  good idea, held back so the simplified page ships first.
- **Price per GB was considered and rejected.** It is the `spec_value` signal under
  another name: dividing a whole machine's price by its RAM plus storage charges the
  chip, screen and build to nothing, so a big machine always looks like good value.
  The upgrade ladder above answers the real question — "am I paying a fair price for
  this upgrade" — without inventing a ratio.
- **Product names carry specifications that now have their own column**, e.g.
  "Apple MacBook Pro 16 M5 Max 18 Core CPU 40 Core GPU 128GB 8TB Silver". The filter
  rail costs about 210px of width, so these names wrap to two lines on most rows.
  Trimming the trailing capacity and colour would help scanning, but the untrimmed
  name is what the shop shows and is the row's only unique identifier. Open
  question, not decided.

## Out of scope

`score.py`, `excel.py` and the workbook are untouched by this. The dashboard stops
displaying the scores; the pipeline keeps computing them. Nothing is deleted, so the
change is reversible and the test suite stays meaningful.
