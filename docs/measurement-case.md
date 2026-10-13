# Measurement case: 849 clicks, 0 conversions

**Client A:** a wellness and rehabilitation centre, one landing site on WordPress, local service area, three active Search campaigns.
**Agent:** the per-site ads & analytics agent on direct Google Ads API + GA4 API access (see [connectors.md](connectors.md)).
**Date of audit:** 2026-10-12. Read-only snapshot; changes are logged separately.

## The question

The account had been spending for months. Was it working?

## What the audit found (90 days, mid-July to 11 October 2026)

| Finding | Evidence | Why it matters |
|---|---|---|
| **849 clicks, 0 conversions** | Ads API report, 90 days | Three campaigns ran on *Maximise conversions* and were "learning" with no signal at all |
| **Primary conversions partly = page views** | Conversion action settings | Bidding optimised for visits, not leads |
| **Form submit and calls not recorded** | No conversion for successful submits or `tel:` clicks; no `generate_lead` or phone-click key events in GA4, only default key events | The single real business outcome was invisible |
| **Display Network inside a Search campaign** | ≈ 28% of 90-day spend, weak engagement | Budget leaking into low-intent placements |
| **Broad match only, no negatives** | Search terms: competitors, other cities, training courses, job seekers, gym equipment. ≈ 10% of spend | Paying for clicks that can never become customers |
| **Geo = "presence or interest"** | Clicks from outside the city and the country | A local service paying for out-of-area clicks |
| **Disapproved ads** | Two ad groups pointed at a staff-profile URL that no longer exists | Spend blocked; needs a site change, not an ads change |
| **Thin ads** | 3 headlines, 2 descriptions; assets not linked to active campaigns | Low ad strength, low CTR potential |
| **GA4 is young** | Property created 2026-10-01, about 11 days of data | Not enough history for GA4-based conclusions yet |

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

## Site-side tracking the executor delivered

- **GA4 in the existing tag block.** One added line, no second loader, verified in production HTML.
- **Ads conversion event** on the form plugin's client-side *mail sent* event. It fires only on a successful submit, not on validation errors or spam.
- **Meta Pixel on the preview copy only.** `PageView` on every page, `Lead` on the same success event. The plugin refuses to run unless the site's host is the preview host, so an accidental copy to production outputs nothing. Verified headless with all Meta domains blocked: exactly one `init`, one `PageView`, and exactly one `Lead` per success event. Error, invalid and spam events send nothing.

### The finding I'm proudest of

On the preview copy, a guard plugin blocks all outgoing mail. You'd assume test submissions are harmless there. Reading the form plugin's source showed the opposite: when mail is skipped, the plugin still returns *mail sent*, the browser still fires the success event, and **a test lead on the preview copy would send a real `Lead` to Meta**. The same would apply to the Ads conversion if it were enabled there. This became a written rule: no test submissions on the preview copy, or use the platform's test-events mode.

## Results

| Metric | Before (90 d to 2026-10-11) | After |
|---|---|---|
| Recorded conversions | 0 | `[TODO: after lead-tracking card ships]` |
| CTR | `[TODO: CTR before]` | `[TODO: CTR after, 14 / 30 days]` |
| Avg CPC | `[TODO: CPC before]` | `[TODO: CPC after]` |
| Share of spend on Display inside Search | ≈ 28% | 0% by setting, `[TODO: confirm in report]` |
| Share of spend on irrelevant queries | ≈ 10% | `[TODO: after negatives]` |
| Out-of-area clicks | present | `[TODO: geo report after PRESENCE]` |

## Lessons

1. **Check measurement before optimisation.** No bid strategy can learn from zero conversions.
2. **Read the code, not the docs.** The preview-copy pitfall was only visible in the form plugin's source.
3. **Agents need a reviewer, even for a keyword list.** The surname mistake took one re-read to catch.
4. **Keep site changes and ads changes in separate lanes.** The ads agent found the dead URL but couldn't "just fix it". The fix waits for the page to reach production, so ads never point to a page that doesn't exist yet.
