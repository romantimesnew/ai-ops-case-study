# Evidence

This page backs the numbers used in the README. The source is the private working repo, which can't be published because it holds client data. Counts for 2026-10-01 to 10-12 were taken on 2026-10-13, and the update for 10-13 to 10-17 on 2026-10-17, with the commands shown, so they can be reproduced on the original repo.

## 1. Activity from git history

Period: 2026-10-01 (initial commit) to 2026-10-12.

| Metric | Value | How counted |
|---|---|---|
| Commits | 249 | `git log --oneline \| wc -l` |
| Task cards, Client A | 59 | files in `site-a/09-ops/inbox/` excluding README |
| Execution reports, Client A | 51 | files in `site-a/09-ops/outbox/` excluding README |
| Task cards, Client B | 3 | `site-b/09-ops/inbox/` |
| Execution reports, Client B | 3 | `site-b/09-ops/outbox/` |
| **Total cards / reports** | **62 / 54** | |
| Client sites | 2 | top-level site folders |

Commits per day:

| Date | Commits |
|---|---|
| 2026-10-01 | 59 |
| 2026-10-02 | 7 |
| 2026-10-04 | 15 |
| 2026-10-06 | 12 |
| 2026-10-07 | 2 |
| 2026-10-09 | 25 |
| 2026-10-10 | 96 |
| 2026-10-11 | 21 |
| 2026-10-12 | 12 |

## 1b. Activity, 2026-10-13 to 2026-10-17

Counted on 2026-10-17 at the private repo's head commit (last commit 2026-10-17 17:45 Europe/Prague), with the same commands. Only `.md` files count as cards; a raw client message saved next to the cards is excluded.

| Metric | Cumulative to 2026-10-17 | Added 2026-10-13 to 10-17 | How counted |
|---|---|---|---|
| Commits | 391 | 142 | `git log --oneline \| wc -l`; `git log --since` |
| Task cards, Client A | 69 | 10 | `.md` files in `site-a/09-ops/inbox/` excluding README |
| Execution reports, Client A | 61 | 10 | `.md` files in `site-a/09-ops/outbox/` excluding README |
| Task cards, Client B | 18 | 15 | `site-b/09-ops/inbox/*.md` excluding README |
| Execution reports, Client B | 18 | 15 | `site-b/09-ops/outbox/*.md` excluding README |
| **Total cards / reports** | **87 / 79** | **25 / 25** | |
| Client sites | 2 | 0 new | top-level site folders |
| Ads changelog entries (change sets) | 9 from 2026-10-12 | 8 | dated sections in `07-ads/changelog.md` |

Commits per day: 2026-10-15: 36 · 2026-10-16: 20 · 2026-10-17: 86. There were no commits on 10-13 and 10-14.

Why cards and reports differ: some cards were superseded by a follow-up card before they ran, and some were still in progress at the cut-off. Finished cards are never rewritten; a follow-up change always gets a new card.

## 2. Excerpt from the ads changelog

Anonymised copy of the real `07-ads/changelog.md` entry. Campaign and object IDs are removed. Times are Europe/Prague.

> **2026-10-12.** Approved by the owner. All changes run with `validate_only` first, then applied and re-read.
> - 13:21:02, Search campaign "Rehabilitation centre": Display Network `true → false`. Search and search partners unchanged.
> - 13:21:02, three campaigns: geo targeting type `PRESENCE_OR_INTEREST → PRESENCE`. Locations unchanged.
> - 13:21:03, shared negative keyword list created (52 terms) and attached to the three campaigns: competitors, other cities, training, vacancies, equipment.
> - 13:21:46, one term removed from the list. It was the client's own specialist's surname, added by mistake. Total: 51.
>
> Verification: Display off on all three, PRESENCE on all three, list attached to all three.

Source figures for the 90-day shares (to 2026-10-11, account currency): total spend 13,688; Display Network inside Search 3,869 (≈28%); irrelevant queries ≈1,316 (≈10%); 849 clicks; 0 conversions.

The API's change history independently shows the 2026-10-12 geo and network updates with source `GOOGLE_ADS_API`. It shows no event for the third campaign's geo change or for the shared list, probably a limitation of the change-history feed. A re-read on 2026-10-13 confirmed all three campaigns are on PRESENCE with Display off, and the shared list is enabled on 3 campaigns with 51 members.

## 2a. Ads changelog, 2026-10-15 to 10-17 (summary, anonymised)

Every entry records the approval time, the `validate_only` result, apply time, before → after per object, and a re-read check. Object IDs, texts naming people or places, and phone numbers are removed here.

| Date | Change set | Verification recorded |
|---|---|---|
| 10-15 | Final URLs of 2 disapproved ads, 1 sitelink and the ad group's keywords moved to the new production page | all objects show the new URL; ads in re-review |
| 10-16 | Call asset tied to the calls conversion; callouts and snippet attached to 3 active campaigns (12 links); 5 sitelinks rewritten, 2 added; schedule aligned to opening hours | links, texts and schedules re-read |
| 10-16 | Form lead → primary (data-driven); page views → secondary or out of bidding goals; phone-click action created (secondary); 16 negatives added (51 → 67) | bidding goals = lead form + calls from ads |
| 10-16 | GA4: 3 custom dimensions, 2 key events (`generate_lead`, `phone_click`) | present on re-read, no duplicates |
| 10-16 | Old call asset unlinked after the new one was approved | only the new asset remains, eligible |
| 10-16 | Two RSAs expanded 3/2 → 15/4 headlines/descriptions; one landing page moved to a service page | ENABLED, 15/4, no pinning |
| 10-17 | Schedule → 07:00–24:00 daily; call asset stays in business hours | 7 days × 07–24 on 3 campaigns |
| 10-17 | Disapproved headline and sitelink text fixed; 34 negatives added (→ 101); 9 phrase-match keywords | 101 members, 9 keywords ENABLED |

## 2b. Read-only account export (2026-10-13)

Exported via Google Ads API and GA4 Data API. Nothing was changed.

| Scope | Spend (account currency) | Clicks | Impressions | CTR | Avg CPC | Primary conv. |
|---|---|---|---|---|---|---|
| Lifetime, 2023-04-12 to 2026-10-12 | ≈172k | 53,114 | 1,021,269 | 5.20% | 3.24 | 0 |
| 14 days before the fix, 2026-09-28 to 10-11 | ≈4.2k | 194 | 13,195 | 1.47% | 21.63 | 0 |
| of which Display (same 14 days) | 27.5% of spend | 99 (51%) | 11,664 (88%) | — | — | 0 |
| Fixed campaign lifetime, Search vs Display | 63% / 36% of spend | — | — | 6.08% / 1.36% | — | 0 |

Conversion actions: 7 enabled primary actions (3 page-view types, ad calls, contact, two lead-form submit types), plus hidden GA4-imported actions. Lifetime "all conversions": 1 (a form submit, October 2026). Primary conversions: 0.

GA4 (data from 2026-10-01 to 10-12): 284 sessions, 243 users, 0 key events; google / cpc 146 sessions (51%), direct 76, organic 31, Instagram ≈19 across sources. Events: page_view 342, scroll 73, click 13, form_start 2; `generate_lead` absent.

## 3. Site audit, Client B

A multi-specialty medical clinic on WordPress, two languages. Method: public crawl first, then a read-only admin inventory via REST with an application password. No changes were made to production.

- 196 unique sitemap URLs, all returned 200. Some sitemap requests returned 503 or 508 under a burst of requests (a hosting bottleneck worth noting in itself).
- Homepage: no H1 and no meta description; its title is in the secondary language on primary-language pages.
- 6 of 11 homepage images have no alt text. No structured data. No SEO plugin.
- Three overlapping content layers (old pages, department taxonomy, landing pages); two competing doctor directories, one of them stale with 11 broken links.
- Public user sitemap and author archive.
- 20 plugins, 16 active. No recent backup (latest archives from 2021 and 2022).
- No legal entity or licence shown in any public block (a trust and compliance gap for a clinic).
- Opening hours (to 17:00) contradict a "24/7 support" line in the footer.

Output: a staged fix plan with explicit boundaries. Prices, packages, publishing and the third-party booking integration are not to be touched without the owner's sign-off, and no visible production edit is made until a preview copy exists.

## 4. Rule excerpts (translated from the working repo)

> "The project chat decides. The executor executes from a card."
> "Unknown facts are written as `unknown`, never invented."
> "Clicking the site burns the limit. File, REST or mirror first. A click only after the owner's answer. Don't repeat an empty attempt."
> "Any change in Ads, GA4 or a click in the browser only after the owner's personal confirmation. Confirmation from the project chat or another bot doesn't count."
> "A new structure or a new rule is written down immediately, in the same turn as the decision."
> "If there is no ready-made solution, consider building your own. Estimate its cost and complexity before choosing." (added 2026-10-17)
