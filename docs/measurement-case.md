# Measurement case: 849 clicks, 0 conversions

**Client A:** a wellness and rehabilitation centre, one landing site on WordPress, local service area, three active Search campaigns.
**Agent:** the per-site ads & analytics agent on direct Google Ads API + GA4 API access (see [connectors.md](connectors.md)).
**Date of audit:** 2026-10-12, with a lifetime read-only export on 2026-10-13. Changes are logged separately.

## Context: my own account, run without conversion tracking

I ran this Google Ads account myself from April 2023, before any agents were involved. For most of that time it was one Search campaign on a clicks strategy, plus Performance Max briefly (it had no delivery). In mid-2026 three service-specific Search campaigns were added. Primary conversions were **never** tracked successfully, so in 3.5 years the account never told me which clicks became leads. This case shows what the audit found and what I changed once agents had API access.

### Lifetime (2023-04-12 to 2026-10-12, read-only export)

| Spend (account currency) | Clicks | Impressions | CTR | Avg CPC | Primary conversions |
|---|---|---|---|---|---|
| ≈172k | 53,114 | 1,021,269 | 5.20% | 3.24 | **0** |

- "All conversions" recorded exactly **1** form submission, in October 2026. It wasn't counted as a primary conversion.
- Trend: account CTR was about 6–7.6% per month in 2023, about 4–5% in 2025, and 1.47% in October 2026. Average CPC went from about 3 to 15–20 from July 2026, when the newer service-specific campaigns took over the traffic. On Search, those campaigns ran at 17–33 CPC, against 3.26 for the original campaign.

## The question

The account had been spending for years. Was it working, and could anyone tell?

## What the audit found

| Finding | Evidence | Why it matters |
|---|---|---|
| **0 primary conversions, lifetime** | Ads API, 2023–2026 | Three campaigns ran on *Maximise conversions* and were "learning" with no signal at all |
| **7 enabled primary conversion actions, 3 of them page views** | Conversion-action export | Bidding optimised for visits, not leads; duplicated, overlapping actions |
| **Form submits and calls not recorded** | Form-submit action: 0 primary, 1 under "all conversions" | The single real business outcome was invisible |
| **GA4: 0 key events** | GA4 Data API, 2026-10-01 to 10-12: 284 sessions, 243 users, `generate_lead` never fired, 2 `form_start` events | No lead signal in analytics either |
| **Paid search dominates traffic** | 146 of 284 GA4 sessions (51%) from google / cpc | Measurement gaps here cost the most |
| **Display Network inside a Search campaign** | That campaign's lifetime: Display CTR 1.36% vs Search 6.08%, 36% of the campaign's spend. 14 days before the fix: 27.5% of account spend, 51% of clicks, 88% of impressions | Budget leaking into low-intent placements, dragging account CTR down |
| **Broad match only, no negatives** | Search terms over 90 days: competitors, other cities, training courses, job seekers, equipment. ≈10% of spend | Paying for clicks that can never become customers |
| **Geo = "presence or interest"** | Clicks from outside the city and the country | A local service paying for out-of-area clicks |
| **Disapproved ads** | Two ad groups pointed at a staff-profile URL that no longer exists | Spend blocked; needs a site change, not an ads change |
| **Thin ads** | 3 headlines, 2 descriptions; assets not linked to active campaigns | Low ad strength, low CTR potential |

## What was changed (2026-10-12, all approved by me)

Each change ran `validate_only` → apply → re-read. Logged with timestamps in Europe/Prague time.

1. Display Network **off** in the Search campaign that had it on. Search and search partners unchanged.
2. Location targeting **"presence or interest" → "presence"** on all 3 campaigns. Locations themselves unchanged.
3. **Shared negative keyword list** created and attached to 3 campaigns: competitors, other cities, training, vacancies, equipment. 52 terms at first. Within a minute one term was removed because it was the client's own specialist's surname, added by mistake. **Final: 51.**

Verification by re-read: Display off on all three, PRESENCE on all three, list attached to three campaigns.

## Proposed, not yet decided (owner's call)

1. Make real leads (form, `tel:`, messengers) **primary** conversions and demote page views to secondary. The site-side part goes through an executor card.
2. Fix or replace the dead landing URL. The new staff page exists on the preview copy only, so ads are switched **after** it reaches production.
3. Move keywords to phrase and exact match.
4. Until conversions flow, use *Maximise clicks* with a CPC cap.
5. Expand ads to full RSA asset sets and attach assets.
6. GA4: `generate_lead` and `phone_click` as key events; exclude internal traffic.
7. Remove two old paused campaigns after review.

## Lead measurement: shipped vs pending

**Pending deploy (prepared, waiting on a production release card):** form, `tel:` and messenger events as primary conversions; page views demoted to secondary; GA4 `generate_lead` and `phone_click` as key events.

**Already shipped by the executor:**
- **GA4 in the existing tag block.** One added line, no second loader, verified in production HTML.
- **Ads conversion event** on the form plugin's client-side *mail sent* event. It fires only on a successful submit, not on validation errors or spam. So far it has recorded only 1 submission, under "all conversions".
- **Meta Pixel on the preview copy only.** `PageView` on every page, `Lead` on the same success event. The plugin refuses to run unless the site's host is the preview host, so an accidental copy to production outputs nothing. Verified headless with all Meta domains blocked: exactly one `init`, one `PageView`, and exactly one `Lead` per success event. Error, invalid and spam events send nothing.

### The finding I'm proudest of

On the preview copy, a guard plugin blocks all outgoing mail. You'd assume test submissions are harmless there. Reading the form plugin's source showed the opposite: when mail is skipped, the plugin still returns *mail sent*, the browser still fires the success event, and **a test lead on the preview copy would send a real `Lead` to Meta**. The same would apply to the Ads conversion if it were enabled there. This became a written rule: no test submissions on the preview copy, or use the platform's test-events mode.

## Results

Changes were applied mid-day on 2026-10-12, so that day is mixed and there are **no full days of "after" data yet**. Baseline = the 14 full days before the change (2026-09-28 to 2026-10-11). In those 14 days all traffic came from one campaign, and there were no impressions at all on 10–11 October (cause not yet established).

| Metric | Baseline (14 d before) | After |
|---|---|---|
| Clicks | 194 (13.9 / day) | `[TODO: 14 / 30 days after]` |
| Impressions | 13,195 | `[TODO]` |
| CTR | 1.47% | `[TODO: CTR after]` |
| Avg CPC (account currency) | 21.63 | `[TODO: CPC after]` |
| Display share of spend | 27.5% | 0% by setting, `[TODO: confirm in report]` |
| Display share of impressions | 88% | `[TODO]` |
| Share of spend on irrelevant queries | ≈10% (90-day audit) | `[TODO: after negatives]` |
| Out-of-area clicks | present | `[TODO: geo report after PRESENCE]` |
| Primary conversions | 0 | `[TODO: after lead-tracking deploy]` |
| GA4 key events | 0 (2026-10-01 to 10-12) | `[TODO: after deploy]` |

## Lessons

1. **Check measurement before optimisation, including your own.** I ran this account for years on clicks and page-view "conversions". No bid strategy can learn from zero real conversions, and neither can the person running it.
2. **Read the code, not the docs.** The preview-copy pitfall was only visible in the form plugin's source.
3. **Agents need a reviewer, even for a keyword list.** The surname mistake took one re-read to catch.
4. **Keep site changes and ads changes in separate lanes.** The ads agent found the dead URL but couldn't "just fix it". The fix waits for the page to reach production, so ads never point to a page that doesn't exist yet.
