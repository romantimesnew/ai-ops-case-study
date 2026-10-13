# Card: <short imperative title>

Site: <site-folder>
Date: YYYY-MM-DD
Decided by: <project chat | project chat + owner>. Backlog item: <B#>
Where: <preview copy only | production, only the files listed>
Clicks: <"no clicks" | allowed for: … after owner's yes>

## Goal (measurable)

<One sentence the executor can verify, e.g. "Header height 88 px at 1440 px and 64 px at 390 px, no jump on scroll.">

## Do

<Access: secret NAME on the executor machine. Never the value.>
<File(s): exact paths.>

1. Back up each file you change next to it as `<file>.bak-pre-<card-name>`.
2. <Step.>
3. <Step.>
4. <Check that proves the goal: HTTP code, HTML contains X, measured size Y.>

## Don't

<Files, sections, prices, tags, forms and publishing that must not change. "Don't write the password.">

## Stop and ask if

- The winning rule or code is in another file
- The goal needs a price, offer, tag, publishing or someone else's access
- A click is needed

## Done when

Report in `<site>/09-ops/outbox/YYYY-MM-DD-<name>.md` containing: what changed (with before → after), where the backup is, the checks and their results, what wasn't touched, what didn't work. Mirror copies of changed files go in the same commit. Rollback: <one line>.
