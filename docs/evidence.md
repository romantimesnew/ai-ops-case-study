# Evidence

This page backs the numbers used in the README. The source is the private working repo, which can't be published because it holds client data. Counts were taken on 2026-10-13 with the commands shown, so they can be reproduced on the original repo.

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

Why cards and reports differ: some cards were superseded by a follow-up card before they ran, and some were still in progress at the cut-off. Finished cards are never rewritten; a follow-up change always gets a new card.

## 2. Ads change log excerpt

Anonymised copy of the real `07-ads/changelog.md` entry. Campaign and object IDs are removed. Times are Europe/Prague.

> **2026-10-12.** Approved by the owner. All changes run with `validate_only` first, then applied and re-read.
> - 13:21:02, Search campaign "Rehabilitation centre": Display Network `true → false`. Search and search partners unchanged.
> - 13:21:02, three campaigns: geo targeting type `PRESENCE_OR_INTEREST → PRESENCE`. Locations unchanged.
> - 13:21:03, shared negative keyword list created (52 terms) and attached to the three campaigns: competitors, other cities, training, vacancies, equipment.
> - 13:21:46, one term removed from the list. It was the client's own specialist's surname, added by mistake. Total: 51.
>
> Verification: Display off on all three, PRESENCE on all three, list attached to all three.

Source figures for the shares quoted in the README (90 days to 2026-10-11, account currency): total spend 13,688; Display Network inside Search 3,869 (≈28%); irrelevant queries ≈1,316 (≈10%); 849 clicks; 0 conversions.

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
