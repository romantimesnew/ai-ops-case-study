# AI Ops Case Study: running two client websites through a team of AI agents

> I'm a former data analyst. Today I run website administration, tracking and paid search for two small-business clients, and most of the hands-on work is done by AI agents I designed, briefed and govern. This repo is an anonymised write-up of that system: how it is wired, the rules that keep it safe, and what it has produced so far.

**Clients (anonymised):** Client A, a wellness centre (WordPress landing site plus Google Ads), and Client B, a multi-specialty medical clinic (WordPress site with about 200 URLs in two languages).
**Period covered:** first 17 days of the system in production (2026-10-01 to 2026-10-17). Last updated 2026-10-17; see [Changelog / recent work](#changelog--recent-work).
**Author:** Roman Timoshenko · [GitHub](https://github.com/romantimesnew) · [LinkedIn](https://www.linkedin.com/in/timoshenkor/)
**Status:** live and in daily use. Numbers come from the private working repo and read-only exports from the ad accounts. Missing numbers are marked `[TODO]`; nothing here is estimated.

---

## Why I built this

At first I used AI only as an information assistant. I ran the ads and made site edits by hand. Then a client site's hosting was hacked and the site was lost. I rebuilt it from old backups with AI help, and it came out cleaner and better than before. After that I moved all the work to AI agents and onboarded other sites in parallel. That history explains three things you'll see throughout this repo: strict security and access rules per agent, a **site passport** as the single source of truth, and backup-before-every-change as a default.

## TL;DR: key takeaways for reviewers

Every claim below links to the evidence for it in this repo. Numbers come from the private working repo (git history, card and report files, ads audit and changelog). Where a number isn't known yet, it's marked `[TODO]` instead of estimated.

1. **I design multi-agent systems, not just prompts.** I set up four roles with written boundaries: a decision agent (project chat), a proposal agent (design chat), an executor agent and a per-site ads & analytics agent, coordinated through task cards in Git. → [docs/architecture.md](docs/architecture.md), [templates/bot-rules.md](templates/bot-rules.md)
2. **It runs in production on live client sites.** In the first 17 days (2026-10-01 to 2026-10-17) it produced 391 commits, 87 task cards and 79 committed execution reports across 2 client websites; 142 commits, 25 cards and 25 reports of that came in the last five days (2026-10-13 to 10-17). → [docs/evidence.md](docs/evidence.md#1-activity-from-git-history)
3. **I set up connectors directly and for free.** I built Google Ads API and GA4 Data/Admin API access on my own Google Cloud OAuth client (no billing, Explorer access tier), with secrets kept only on the agent machine. The OAuth app has since passed Google's brand verification and is published, so its tokens no longer expire the way testing-mode tokens do. No paid connector service and no browser automation for routine work. → [docs/connectors.md](docs/connectors.md)
4. **I bring analyst rigour to marketing, including my own work.** I ran the client's Google Ads account myself from 04/2023: ≈172k (account currency) lifetime spend, 53,114 clicks, 1.02M impressions, CTR 5.20%. It ran **without working conversion tracking** (0 primary conversions ever). The API audit made that visible, traced it to measurement setup, and quantified the waste. In the 14 days before the fixes, Display took 27.5% of spend and 88% of impressions; over 90 days, ≈10% of spend went to irrelevant queries. → [docs/measurement-case.md](docs/measurement-case.md)
5. **Changes are governed and auditable.** Every ads write goes proposal → owner approval → `validate_only` (dry run) → apply → re-read → changelog entry. From 2026-10-12 to 10-17 that process carried 9 logged change sets: Display off, presence-only geo, negatives grown from 51 to 101 terms, conversions restructured, GA4 key events and custom dimensions, ads rewritten, ad schedule. A reviewed keyword-list mistake was caught and corrected the same minute. → [docs/evidence.md](docs/evidence.md#2-excerpt-from-the-ads-changelog), [docs/measurement-case.md](docs/measurement-case.md#what-was-changed-2026-10-12-all-approved-by-me)
6. **Agents deliver working code from task cards, verified with evidence.** The executor shipped WordPress mu-plugins for tracking, lead events, legacy-URL 301s, a preview-copy guard and spam-URL blocking, each with before/after checks in its report. Lead tracking went live on 2026-10-16. On 2026-10-17 one test lead and one test call showed up in both GA4 and Google Ads. → [examples/wordpress-mu-plugins/](examples/wordpress-mu-plugins/), [docs/workflow.md](docs/workflow.md)
7. **Onboarding a second site reuses the same system.** For Client B the agents moved from a read-only audit to delivery on 2026-10-17: a preview copy with indexing closed, a child-theme mirror in Git, client edit requests turned into cards, and a two-phase production release over REST. That one day produced 15 cards and 15 reports. → [Changelog](#changelog--recent-work)
8. **The pattern carries over to other domains.** The parts that make it work (source-of-truth files, task cards, role-scoped rules, approval gates, direct API connectors) are domain-neutral and come as templates. → [templates/](templates/)

What this repo does **not** claim: post-change performance (the ads changes landed 2026-10-12 to 10-17, budgets and bidding are frozen until about 2026-10-30, and the first before/after comparison comes then, so these stay `[TODO]`), real recorded leads (tracking is verified with test events only; real lead counts are `[TODO]`), Meta Marketing API use in production (documented, not yet run), and production use of the tools I only trialled (see [Tools I use and why](#tools-i-use-and-why)).

## Capabilities matrix

| Capability | What I did | Evidence |
|---|---|---|
| Multi-agent architecture | 4 agent roles with an access matrix; one executor shared by all sites, ads agents per site | [architecture.md](docs/architecture.md#components) |
| Agent workspaces & memory | Private Git repo as shared memory; site passport as the single source of truth; rules written to files in the same turn they're decided | [architecture.md](docs/architecture.md#repository-layout-per-site), [site-passport.md](templates/site-passport.md) |
| Agent rules & guardrails | Profile texts with can / needs-approval / never sections; one card, one risk; stop conditions; ads agent may brief the executor only on cards already in progress; build-vs-buy rule: when nothing ready fits, estimate the cost of an own solution first | [bot-rules.md](templates/bot-rules.md), [task-card.md](templates/task-card.md) |
| Task orchestration | Backlog → card → report lifecycle with statuses; one-line dispatch | [workflow.md](docs/workflow.md) |
| Connectors (direct, free) | Google Ads API + GA4 Data/Admin API via own OAuth desktop client; WordPress REST via application password; GitHub | [connectors.md](docs/connectors.md) |
| Paid search (Google Ads) | Ran the account since 04/2023 (≈172k account currency lifetime, 53k clicks); API audit; Display off; geo set to presence only; shared negative list 51 → 101 terms; 9 phrase-match keywords; ads rewritten to full RSA sets and policy disapprovals fixed; ad schedule 07:00–24:00 daily with call assets in business hours only | [measurement-case.md](docs/measurement-case.md), [evidence.md](docs/evidence.md#2-excerpt-from-the-ads-changelog) |
| Tracking & analytics | GA4 in a single gtag loader; form lead made a primary Ads conversion, phone click added as secondary, page views demoted; GA4 `generate_lead` / `phone_click` as key events with 3 custom dimensions; deployed 2026-10-16, verified end to end 2026-10-17; preview-copy pitfall found by reading the plugin source | [measurement-case.md](docs/measurement-case.md#lead-measurement-shipped-vs-pending), [lead-events.php](examples/wordpress-mu-plugins/lead-events.php) |
| Technical SEO / site audit | 196-URL audit of a medical clinic site, with a staged fix plan; Search Console cleanup after the hack (spam sitemaps removed, domain property, new sitemap); 301s for old URLs that still had search clicks | [evidence.md](docs/evidence.md#3-site-audit-client-b), [legacy-301-redirects.php](examples/wordpress-mu-plugins/legacy-301-redirects.php) |
| Web via code | mu-plugins, file mirror in Git, preview → production release path, one-file rollback; own REST plugin for theme files when the host's file channel was unreliable | [examples/](examples/wordpress-mu-plugins/), [architecture.md](docs/architecture.md#release-path), [theme-file-rest.php](examples/wordpress-mu-plugins/theme-file-rest.php) |
| Site onboarding | Second site taken from audit to preview copy to a two-phase production release in one day, with the same executor and card format | [Changelog](#changelog--recent-work), [evidence.md](docs/evidence.md#1b-activity-2026-10-13-to-2026-10-17) |
| Data analysis background | ~3.5 years as a data and product analyst at mobile game companies: analytics set up from scratch per game, ETL, forecasts, A/B test analysis, decision support for marketers and producers | CV (separate document) |
| Tool selection | Main system on one agent platform with role-based bots; other agent tools trialled and compared per task | [Tools I use and why](#tools-i-use-and-why) |

Machine-readable summary: [profile.yaml](profile.yaml) · Index for LLM readers: [llms.txt](llms.txt)

## Changelog / recent work

Dates are when the change was committed or applied (Europe/Prague). Source: the private working repo (git log, task cards, execution reports, ads changelog) plus status notes from the ads & analytics agent. Counts are in [docs/evidence.md](docs/evidence.md#1b-activity-2026-10-13-to-2026-10-17).

### 2026-10-13 to 2026-10-17: 142 commits, 25 task cards, 25 reports

**Client A (wellness and rehabilitation centre): ads and measurement**
- **2026-10-12:** Display Network off in one Search campaign; an outdated phone number replaced in the ads.
- **2026-10-15:** two specialist ad groups were disapproved because their landing page no longer existed. Their final URLs were moved to the new staff page once it reached production, then sent for re-review.
- **2026-10-16:** conversions restructured. The website form lead became a primary conversion with data-driven attribution, the page-view actions were demoted or removed from bidding goals, and a new phone-click action was added as secondary. In GA4, `generate_lead` and `phone_click` were marked as key events, with 3 event-scoped custom dimensions (form location, link location, messenger).
- **2026-10-16:** sitelinks rewritten and 2 added; callouts and a structured snippet attached to the 3 active campaigns; a new call asset approved and the old one unlinked. Two ads expanded from 3 headlines and 2 descriptions to 15 and 4. One ad group's landing page moved to a better-matched service page.
- **2026-10-16:** lead tracking deployed on the live site (form lead, phone click and messenger click events, plus Ads lead and phone conversions).
- **2026-10-17:** ad schedule set to 07:00–24:00 every day, because the form takes leads around the clock. Call assets stay limited to business hours.
- **2026-10-17:** policy-disapproved headline and sitelink text fixed. The shared negative list grew from 51 to 67 terms on 10-16 and to 101 on 10-17 (competitors, other cities, training, equipment, home visits). 9 phrase-match keywords added.
- **2026-10-17, verified end to end:** one test lead and one test phone click on production. GA4 received both events and Google Ads recorded one test conversion for each. The test also showed that an earlier automated check (2026-10-16) could not have proven GA4 receipt on its own, which is why the re-test was done with a real browser session.
- **Search Console:** spam sitemaps left over from the hack were removed, a domain property was added and a new sitemap submitted.
- **Connector:** the OAuth app passed brand verification and was published (2026-10-16), so its tokens no longer expire.
- **Not yet measured:** budgets and bidding are frozen until about 2026-10-30 so the changes can be read cleanly. `[TODO: first before/after comparison, due ~2026-10-30]`

**Client A: site**
- **2026-10-15:** full production rollout from the preview copy: staff pages, a lead specialist's biography with grouped certificates, and full privacy policy and terms naming the operating business. Header section links also fixed for inner pages.
- **2026-10-16:** 301 redirects for 7 old URLs (14 address variants) that still had search clicks in Search Console, via a single mu-plugin on production and the preview copy. Query strings are preserved. → [legacy-301-redirects.php](examples/wordpress-mu-plugins/legacy-301-redirects.php)

**Client B (multi-specialty medical clinic): from audit to delivery, 2026-10-17**
- Preview copy set up in its own folder, search indexing closed, HTTPS verified.
- The hosting's file channel proved unreliable, so a small REST plugin was written to read and write child-theme files (admin-only, path-guarded). This followed a new rule: when nothing ready-made fits, estimate the cost of building your own first. → [theme-file-rest.php](examples/wordpress-mu-plugins/theme-file-rest.php)
- The child theme was mirrored into Git, so the decision chat reads the real code before writing a card.
- The client's edit requests arrived as messenger text and photos. They were saved to the repo as a file plus images and turned into cards: booking-form option removed, header button hidden, typos fixed, two new service pages, doctor profiles and order, banner photo position, menu items.
- Two-phase production release over the standard REST API: phase 1 covered pages, photos and menus (menu JSON backed up before the change), phase 2 the theme files and banner. Each step was checked with HTTP status and page HTML.
- 15 task cards and 15 reports for this site on that one day.

**Process and agents**
- The ads agent may now message the executor only about a card already in progress, never with a new task (owner decision, 2026-10-17).
- The project-chat "tempo" rules were folded into the ordinary work rules, and chats re-read the full rule set only on their first turn or after a long pause.
- Build-vs-buy rule added to the global rules (2026-10-17).

### 2026-10-01 to 2026-10-12: 249 commits, 62 task cards, 54 reports
Initial system build, the Client A ads and measurement audit and first governed fixes, and the Client B read-only audit. Details are in the sections below and in [docs/](docs/).

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

- **Google Ads API + GA4 Data/Admin API:** I created a Google Cloud project (no billing), an OAuth consent screen with the account as a test user, and a Desktop OAuth client. The app later passed brand verification and was published (2026-10-16), so tokens no longer expire. Python scripts run in a venv on the agent's own machine. Tokens are stored there with `chmod 600` and never in the repo or chat. Explorer access was granted within minutes.
- **WordPress:** a dedicated executor user (never the owner's account) with an application password. REST and file transfer come before any UI clicking. Where the host's file channel was unreliable, a small path-guarded REST plugin handles theme files.
- **GitHub:** the private repo is the shared memory every agent reads.
- **Meta Marketing API:** setup steps are documented against the official docs but not yet run in production.

Why this route: no subscription, fewer tokens than browser automation, and access I can audit and revoke.
How-to without secrets: [docs/connectors.md](docs/connectors.md)

## 5. Results so far

**Operations (2026-10-01 to 2026-10-17):** 391 commits, 87 task cards, 79 committed reports across 2 sites (to 2026-10-12: 249 / 62 / 54).

**Client A (wellness centre): measurement & paid search** ([docs/measurement-case.md](docs/measurement-case.md))
- **Account history:** I ran the account myself from 04/2023 to 10/2026. Lifetime it had ≈172k (account currency) spend, 53,114 clicks, 1,021,269 impressions, CTR 5.20% and average CPC 3.24. Primary conversions recorded over that whole period: **0**. The campaigns ran without working conversion tracking, and I'm stating that plainly because the diagnosis is the point of this case.
- **Root cause:** 7 enabled *primary* conversion actions, 3 of them page-view types. The form-submit action never recorded a primary conversion. GA4 (live since 2026-10-01) shows 284 sessions, 51% of them paid search, and **0 key events**, with no `generate_lead` event at all.
- **Waste found:** in the 14 days before the fixes (account CTR 1.47%, CPC 21.63, 194 clicks), Display inside a Search campaign took 27.5% of spend, 51% of clicks and 88% of impressions. Over that campaign's lifetime, Display CTR was 1.36% against 6.08% on Search. Over 90 days, ≈10% of spend went to competitors, other cities, training courses and job seekers (broad match, no negatives). Targeting was "presence or interest", so clicks came from outside the service area.
- **Applied after approval (2026-10-12, via API):** Display off, presence-only geo on 3 campaigns, and a shared negative list (52 terms, then corrected to 51 when a review caught the client's own specialist's surname).
- **Follow-up changes (2026-10-15 to 10-17, all approved, dry-run validated, re-read and logged):** conversions restructured (form lead primary, phone click secondary, page views demoted); GA4 key events and 3 custom dimensions; dead landing URLs replaced; ads rewritten to full RSA sets and policy disapprovals fixed; sitelinks, callouts and the call asset updated; schedule 07:00–24:00 daily with calls in business hours; negatives 51 → 101; 9 phrase-match keywords.
- **Lead tracking deployed (2026-10-16) and verified (2026-10-17):** one test lead and one test call reached GA4 as events and Google Ads as one conversion each.
- **Already shipped:** GA4 added to the existing tag block without a second loader, verified in production HTML. Meta Pixel `PageView` + `Lead` runs on the preview copy only, behind a host guard. The existing Ads form-success tag has recorded just 1 submission, in October 2026, counted under "all conversions" and not as a primary conversion.
- **A non-obvious finding:** on the preview copy, mail is suppressed but the form plugin still reports success, so test submissions *would* send real `Lead` conversions. That's now a documented rule.
- **After:** budgets and bidding are frozen until about 2026-10-30, when the first comparison is due. `[TODO: CTR / CPC / Display share / irrelevant-query share after the changes]` · `[TODO: real primary conversions (form leads) after the 2026-10-16 deploy]`

**Client A: site**
- A preview environment with a guard plugin (noindex, robots disallow, all outgoing mail and notifications blocked).
- Privacy policy published, then terms of use and an English legal version added on the preview copy.
- Junk spam URLs that returned the full homepage with 200 now return 403, while UTM and click-ID links are verified to still return 200.
- 2026-10-15: preview changes released to production (staff pages, biography, full legal texts). 2026-10-16: 301s for 7 old URLs that still had search clicks.
- Search Console: leftover spam sitemaps from the hack removed, domain property added, new sitemap submitted.

**Client B (medical clinic): audit before touching anything**
- Public crawl of 196 sitemap URLs (all 200), then a read-only admin inventory.
- Findings: homepage without H1 or meta description, titles in the wrong language on the primary-language pages, 6 of 11 homepage images without alt text, no SEO plugin, three overlapping content layers (old pages, taxonomy and landing pages), two competing doctor directories, a public user sitemap and author archive, no recent backup, and no legal entity or licence shown on the site.
- The output is a staged fix plan with explicit "don't touch without owner sign-off" boundaries (prices, packages, third-party booking integration).
- **2026-10-17, delivery started:** preview copy with indexing closed, child-theme mirror in Git, own REST plugin for theme files, client edits turned into cards, and a two-phase production release over REST (15 cards, 15 reports that day).
- `[TODO: indexed pages / Search Console clicks before and after fixes]`

## 6. What I'd do next

1. **Read the first before/after comparison (~2026-10-30), then decide on bidding.** Lead tracking is live and verified. Next: exclude internal traffic, decide with the owner on consent mode (not configured yet), and only move to conversion-based bidding once real leads accumulate. Until then the audit's proposal stands: "Maximise clicks" with a CPC cap.
2. **An ad-copy variant agent:** generate RSA headline and description variants within compliance rules (for health services: no diagnosis or outcome promises), create them *paused*, and run structured A/B reads with a pre-registered decision rule.
3. **A weekly insight digest:** Ads + GA4 (+ CRM when available) pulled by API into a short "here's what changed and what to do next" note, committed to the repo.
4. **Make onboarding a template:** a new site becomes a new folder with a passport, rules and inbox/outbox. The executor stays the same agent; only the ads agent is per site.

## Tools I use and why

- **Main working system:** Grok Bot, running several role-based bots (project chats, the executor, a per-site ads & analytics bot, a personal assistant). Each one has its own profile rules and reads the same Git repo.
- **Trialled and compared, used per task:** Conductor (agent orchestrator), Claude Code, Codex and Gemini. I evaluated them against the same kind of tasks and picked the tool per task. None of them is a dependency of the system described here, and I don't claim sustained production use of them.
- **Everyday tools:** git/GitHub, Python (API scripts in venvs), Docker, Warp (terminal), Zed (editor).
- **Selection rule:** use the cheapest tool that reliably reaches the goal (API over browser, file over click), and keep the repo, not the tool, as the system of record, so tools can be swapped without losing memory.

## Other projects

- **[Tesla Fleet: self-hosted data and voice-control server for my own car](projects/tesla-fleet/)** (2026-10-17). Built in one day with an AI agent on Tesla's official Fleet API, signed-command proxy and Fleet Telemetry: the car pushes data over mTLS through Kafka into TimescaleDB, with no API polling, and Siri, Shortcuts and Apple Watch commands go through a small Python service with a bearer token and an 8 m geofence for the trunk, frunk and charge port. Includes a wake-up log, the security setup, who did what, and the sanitised code.

## Repo map

```
README.md                    you are here
docs/architecture.md         roles, access matrix, boundaries
docs/workflow.md             backlog → card → report lifecycle, anonymised sample card + report
docs/connectors.md           direct API setup in general terms, pitfalls, no secrets
docs/measurement-case.md     the ads & tracking audit, anonymised
docs/evidence.md             activity numbers and how they were counted, changelog excerpt, site audit
profile.yaml                 machine-readable summary: role fit, skills, evidence paths
llms.txt                     index of key files for LLM readers
templates/                   agent rules, task card, report, site passport, backlog
examples/wordpress-mu-plugins/  generic, client-free code the executor shipped
projects/tesla-fleet/         side project: self-hosted Tesla telemetry + voice control, sanitised code
```

*Anonymisation: client names, domains, account and tag IDs, hosts, contacts and security settings are removed or replaced with placeholders such as `{ADS_TAG_ID}`.*
