# AI Ops Case Study: running two client websites through a team of AI agents

> I'm a former data analyst. Today I run website administration, tracking and paid search for two small-business clients, and most of the hands-on work is done by AI agents I designed, briefed and govern. This repo is an anonymised write-up of that system: how it is wired, the rules that keep it safe, and what it has produced so far.

**Clients (anonymised):** Client A, a wellness centre (WordPress landing site plus Google Ads), and Client B, a multi-specialty medical clinic (WordPress site with about 200 URLs in two languages).
**Period covered:** first 12 days of the system in production (2026-10-01 to 2026-10-12).
**Status:** live and in daily use. Numbers below come from the private working repo. Missing numbers are marked `[TODO]`; nothing here is estimated.

---

## TL;DR

| | |
|---|---|
| **What I built** | A multi-agent operating model for web marketing. A *decision* chat, an *executor* agent that only acts on written task cards, a dedicated *ads & analytics* agent on direct Google APIs, and a private Git repo as the single source of truth |
| **Why it works** | Every change is a file: idea → backlog row → task card → committed report. Agents can't "remember" things wrongly because the facts live in a *site passport*, not in chat history |
| **Throughput (12 days)** | 249 commits · 62 task cards · 54 committed execution reports · 2 sites |
| **Ads audit, Client A** | 90 days: 849 clicks, **0 recorded conversions**. Root cause was measurement, not bidding. About 28% of spend went to the Display Network inside a Search campaign, and about 10% to irrelevant queries |
| **Fixes applied** | Display off, geo set to presence-only, 51-term shared negative list. Each one validated (`validate_only`), applied, re-read and logged. Impact: `[TODO: CTR / CPC / wasted-spend share, 14 and 30 days after 2026-10-12]` |
| **Connectors** | Direct, free API access (own Google Cloud OAuth client, Explorer API tier) instead of paid connector services or browser automation |

---

## 1. What I built

```mermaid
flowchart LR
    Owner(["Me: owner / approver"])
    subgraph Repo["Private Git repo = source of truth"]
        PASS["Site passport<br/>facts only"]
        RULES["Rules<br/>global + per site + per agent"]
        BL["backlog.md<br/>the only to-do list"]
        IN["inbox/<br/>task cards"]
        OUT["outbox/<br/>execution reports"]
        MIRROR["file mirror<br/>custom code + CSS"]
        CL["ads changelog"]
    end
    PC["Project chat<br/>decides, writes cards"]
    DC["Design chat<br/>proposes, never dispatches"]
    EX["Executor agent<br/>builds only from a card"]
    ADS["Ads & analytics agent<br/>Google Ads API, GA4 API"]
    PA["Personal assistant agent<br/>outside the site loop"]
    PREV["Preview copy<br/>noindex, mail blocked"]
    PROD["Production site"]
    GOOG[("Google Ads / GA4")]

    Owner -- "yes / no" --> PC
    Owner -- "personal yes for every ads write" --> ADS
    DC -- "reviews, design backlog" --> BL
    PC -- "decided item" --> IN
    IN --> EX
    EX -- "report + mirror update, same commit" --> OUT
    EX --> PREV -- "separate card after owner review" --> PROD
    ADS -- "read freely, write after approval" --> GOOG
    ADS -- "site change needed? backlog row" --> BL
    ADS --> CL
    PASS -. "read first" .-> PC
    PASS -.-> EX
    PASS -.-> ADS
    PA -.- Owner
```

Roles and boundaries:

- **Project chat (one per site), the decision maker.** Reads the passport, rules and backlog, then decides. It writes the task card and dispatches it to the executor, but only after my confirmation. It never logs in to a server itself.
- **Design chat, the proposer.** Writes dated design reviews (findings `F1…Fn`) and a design backlog (`D1…Dn`). It never writes cards and never talks to the executor.
- **Executor agent, one for all sites.** Its name carries no client name, so adding a site doesn't mean renaming it. It works *only* from a card path in the repo, reads only that site's passport, and must commit a report to `outbox/`. No report means the task isn't done.
- **Ads & analytics agent, one per site.** Talks to Google Ads and GA4 through its own API scripts. It reads and audits freely. Every write needs my personal approval and runs through `validate_only` first. It never edits the website; when a campaign needs a page or tag change, it adds a backlog row.
- **Personal assistant agent.** Separate from the site loop, with no access to site rules or cards.

Full detail: [docs/architecture.md](docs/architecture.md)

## 2. How the work flows

```
idea / finding ──► backlog.md row (open)
                   │ project chat + owner decide
                   ▼
                decided ──► task card in inbox/ (in-card)
                               │ one-line dispatch: "Execute card <path>"
                               ▼
                       executor works on the preview copy
                               │
                               ▼
                 report in outbox/ + mirrored files, same commit
                               │ owner reviews
                               ▼
                 done  (prod release = separate card)
```

Rules that made this reliable:

1. **One card, one risk.** Small edits to the same file go into one card. A new card is needed whenever a *boundary* changes: publishing, price, tracking tag, access, or someone else's file.
2. **The goal beats the step.** A card states a measurable goal (for example "header height 105 px at 1440 px"). If the named step doesn't reach it, the executor may adjust within the same file and must say what actually moved the result.
3. **Read the mirror, not memory.** Before a visual card, the decision chat reads the mirrored CSS and plugin files. It learned this the hard way: a later rule in the same file was silently overriding an earlier one.
4. **Cheapest path first.** File, REST API or mirror before any browser clicking, because browser sessions burn the weekly agent quota. A click needs a stated reason and my yes. Failed attempts are never blindly repeated.
5. **Unknown means unknown.** Agents write `unknown` and never fill gaps with guesses.
6. **Rules live in files.** Any new rule decided in any chat is written into the repo in the same turn. Chats can't see each other's history, so a rule kept only in one chat doesn't exist for the others.

Sample card, report and lifecycle: [docs/workflow.md](docs/workflow.md)

## 3. Source of truth: the site passport

Every site has one `site-passport.md` holding facts only: domain and renewal dates, hosting, CMS and theme, every custom file and why it exists, forms and where leads go, the measurement setup, what's unfinished, and **where each fact came from** (confirmed by the owner, live-checked on a date, or unknown). Secrets are never stored, only *where* they live.

Blank template: [templates/site-passport.md](templates/site-passport.md)

## 4. Connectors: direct and free

- **Google Ads API + GA4 Data/Admin API:** I created a Google Cloud project (no billing), an OAuth consent screen in testing mode with the account as a test user, and a Desktop OAuth client. Python scripts run in a venv on the agent's own machine. Tokens are stored there with `chmod 600` and never in the repo or chat. Explorer access was granted within minutes.
- **WordPress:** a dedicated non-admin editor user with an application password. REST and file transfer come before any UI clicking.
- **GitHub:** the private repo is the shared memory every agent reads.
- **Meta Marketing API:** setup steps are documented against the official docs but not yet run in production.

Why this route: no subscription, fewer tokens than browser automation, and access I can audit and revoke.
How-to without secrets: [docs/connectors.md](docs/connectors.md)

## 5. Results so far

**Operations (2026-10-01 to 2026-10-12):** 249 commits, 62 task cards, 54 committed reports across 2 sites.

**Client A (wellness centre): measurement & paid search** ([docs/measurement-case.md](docs/measurement-case.md))
- Read-only audit of 90 days of Google Ads: 849 clicks and 0 conversions. Three campaigns ran on *Maximise conversions* with no conversion signal to learn from.
- Root cause: some primary conversions were *page views*. Form submissions and calls weren't counted, and GA4 had no lead or phone-click key events.
- Waste found: about 28% of 90-day spend went to the Display Network inside a Search campaign, and about 10% to competitors, other cities, training courses and job seekers (broad match, no negatives). Targeting was "presence or interest", so clicks came from outside the service area.
- Applied after approval: Display off, presence-only geo on 3 campaigns, and a shared negative list (52 terms, then corrected to 51 when a review caught the client's own specialist's surname).
- Agent-delivered tracking work: GA4 added to the existing tag block without a second loader, verified in production HTML; Meta Pixel plus a `Lead` event on the form-success event in the preview copy only, behind a host guard.
- A non-obvious finding: on the preview copy, mail is suppressed but the form plugin still reports success, so test submissions *would* send real `Lead` conversions. That's now a documented rule.
- `[TODO: conversions recorded after the lead-tracking fix ships]` · `[TODO: CTR before/after]` · `[TODO: CPC before/after]` · `[TODO: share of spend on irrelevant queries after negatives]`

**Client A: site**
- A preview environment with a guard plugin (noindex, robots disallow, all outgoing mail and notifications blocked).
- Privacy policy published, then terms of use and an English legal version added on the preview copy.
- Junk spam URLs that returned the full homepage with 200 now return 403, while UTM and click-ID links are verified to still return 200.

**Client B (medical clinic): audit before touching anything**
- Public crawl of 196 sitemap URLs (all 200), then a read-only admin inventory.
- Findings: homepage without H1 or meta description, titles in the wrong language on the primary-language pages, 6 of 11 homepage images without alt text, no SEO plugin, three overlapping content layers (old pages, taxonomy and landing pages), two competing doctor directories, a public user sitemap and author archive, no recent backup, and no legal entity or licence shown on the site.
- The output is a staged fix plan with explicit "don't touch without owner sign-off" boundaries (prices, packages, third-party booking integration).
- `[TODO: indexed pages / Search Console clicks before and after fixes]`

## 6. What I'd do next

1. **Close the lead-tracking gap end to end:** form, `tel:` and messenger clicks as primary conversions, page views demoted to secondary, internal traffic excluded. Until conversions flow, the audit proposes "Maximise clicks" with a CPC cap. Once the data supports it, go back to conversion-based bidding.
2. **An ad-copy variant agent:** generate RSA headline and description variants within compliance rules (for health services: no diagnosis or outcome promises), create them *paused*, and run structured A/B reads with a pre-registered decision rule.
3. **A weekly insight digest:** Ads + GA4 (+ CRM when available) pulled by API into a short "here's what changed and what to do next" note, committed to the repo.
4. **Make onboarding a template:** a new site becomes a new folder with a passport, rules and inbox/outbox. The executor stays the same agent; only the ads agent is per site.

## Repo map

```
README.md                    you are here
docs/architecture.md         roles, access matrix, boundaries
docs/workflow.md             backlog → card → report lifecycle, anonymised sample card + report
docs/connectors.md           direct API setup in general terms, pitfalls, no secrets
docs/measurement-case.md     the ads & tracking audit, anonymised
templates/                   agent rules, task card, report, site passport, backlog
examples/wordpress-mu-plugins/  generic, client-free code the executor shipped
```

*Anonymisation: client names, domains, account and tag IDs, hosts, contacts and security settings are removed or replaced with placeholders such as `{ADS_TAG_ID}`.*
