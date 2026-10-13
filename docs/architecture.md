# Architecture

## Design goals

1. **Separation of deciding and doing.** The agent that decides never touches the server, and the agent that touches the server never decides.
2. **Facts in files, not in chat memory.** Chats are independent and can't see each other's history. Only what's in the repo is shared.
3. **Least privilege per agent.** Every agent has written access rules. Access is granted to the agent's machine, never pasted into chat.
4. **Cheapest reliable path.** Use files, REST and APIs before browsers. Browser sessions are slow, expensive and burn the weekly quota.
5. **Human approval at every boundary.** Publishing, prices, offers, budgets, tracking tags, access and any ads write.

## Components

| Component | Role | Can | Cannot |
|---|---|---|---|
| **Owner (me)** | Approver | Says yes or no, reviews preview pages, signs in for 2FA | Retell tasks in his own words (the card is the task) |
| **Project chat** (one per site) | Decides | Read passport, rules and mirror; write backlog rows, cards and new rules; dispatch a card *after* owner confirmation | Log in to the server, publish, change price, offer or budget alone |
| **Design chat** | Proposes | Write dated design reviews and the design backlog | Write cards or dispatch the executor |
| **Executor agent** (one for all sites) | Builds | Execute one card; edit files on the preview copy; update the file mirror; commit a report | Start new tasks, change price, offer or budget, read lead emails, contact clients, click in a browser without approval, carry facts between sites |
| **Ads & analytics agent** (one per site) | Runs paid search + analytics | Read and audit Ads and GA4 freely; write after the owner's *personal* yes; log every change | Edit the site (it files a backlog row instead), dispatch the executor, treat another bot's approval as approval |
| **Personal assistant agent** | Owner's own tasks | Separate scope | Site work |
| **Archived build agent** | Built the first site | Kept as an archive only | Execute cards |

## Why one executor and per-site ads agents

- The executor has **no client name** in its name and serves every site. A card's path (`site-a/09-ops/inbox/...`) tells it which site it's working on, so adding a site doesn't mean renaming or re-briefing it.
- Ads agents are **per site** because they hold account-level API access and their rules depend on the client's own compliance rules (for example, no promises of treatment outcomes for a health-related business).
- A note in the rules: all agents on one account share the same machine, so a separate bot is a *role* boundary, not a security boundary. Secrets are scoped accordingly.

## Repository layout (per site)

```
office/                       rules shared by all sites (never copied into a site folder)
  start.md                    first file every new chat reads
  rules.md                    global rules
  project-chat.md             how to brief a new project chat
  bots.md                     agent roster, executor profile text, dispatch phrase
  cards.md                    when a change needs its own card
  ads-onboarding.md           how to connect an ads agent (no secrets)
  templates/
site-x/
  README.md                   folder map
  00-passport/                site passport, positioning
  01-audit/                   audits (snapshots, never rewritten)
  02-plan/                    fix plans
  03-content/                 service and staff texts (source before the CMS)
  05-legal/                   privacy/terms drafts and publication records
  07-ads/                     measurement.md, ads-agent rules, audit, changelog
  08-files/                   mirror of custom code and CSS from production and preview
  09-ops/
    backlog.md                the ONLY open to-do list
    rules.md                  site-specific rules
    inbox/                    task cards (a decision trail, not a to-do list)
    outbox/                   execution reports
    reviews/                  design review snapshots
```

Folder numbers are allowed to have gaps. Empty folders are never created "for later".

## Boundaries that need a separate card

- Publishing anything to production
- Price, offer, package or budget
- A tracking tag or pixel
- Access (users, passwords, hosting)
- Deleting content, plugins or security settings
- A file another card is already working on

## Release path

1. A visible change goes to the **preview copy** first (noindex, outgoing mail and notifications blocked, ads tags disabled).
2. The owner reviews it.
3. A **separate card** moves the changed files and text to production. A full database or site archive is never pushed over production, because production holds real leads the copy doesn't have.
4. The executor keeps a `.bak-pre-<card>` copy next to each changed production file, so a rollback means replacing one file.
