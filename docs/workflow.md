# Workflow: backlog → card → report

## Lifecycle and statuses

`backlog.md` is the only list of open work. Statuses are `open` → `decided` → `in-card` → `done`, or `dropped` with a one-line reason. Rows are never deleted.

| Step | Who | Artefact |
|---|---|---|
| Idea, finding, ads-agent request | anyone | backlog row, `open` |
| Decision | project chat + owner | row → `decided` |
| Card | project chat | `09-ops/inbox/YYYY-MM-DD-short-name.md`, row → `in-card` + path |
| Dispatch | project chat, *after* owner confirms | a single line: `Execute card <repo>, branch main, path: <path>.` |
| Execution | executor | changes on the preview copy, mirror update |
| Report | executor | `09-ops/outbox/<same name>.md`, committed together with the mirrored files; the same text goes back to the chat that sent the task |
| Acceptance | owner | row → `done` |

The project chat doesn't wait for the run to finish. It hands over the card, confirms the executor has started, tells the owner, and stops. The owner reports completion.

A finished card is never rewritten. A follow-up change gets a new card. This keeps `inbox/` an honest decision trail.

## Sample task card (anonymised, translated)

This is the real card that added GA4 to Client A's existing tag block. IDs and hosts are replaced with placeholders.

```markdown
# Card: Google Analytics line

Site: site-a
Date: 2026-10-01
Decided by: project chat
Publish file: yes, this line only

## Do

Access: file transfer secret {FILE_ACCESS_SECRET_NAME} on the executor's machine.
File: wp-content/mu-plugins/{ads_tag_plugin}.php

1. Download the file and save a copy next to it on the server as
   {ads_tag_plugin}.php.bak-pre-ga4.
2. In the existing gtag block, right after gtag('config', '{ADS_TAG_ID}');,
   add the line gtag('config', '{GA4_MEASUREMENT_ID}');.
3. Do not add a second script or a second gtag.js loader.
   Do not use {OLD_WRONG_GA4_ID}.
4. Check the public homepage HTML: both {ADS_TAG_ID} and {GA4_MEASUREMENT_ID} present.

## Don't

Don't change other files, the form, prices or the header. Don't install the Meta pixel.
Don't upload a site copy. Don't write the password.

## Done when

Report in site-a/09-ops/outbox/2026-10-01-ga4-config.md: what changed,
where the backup is, what the HTML shows.
```

### The report that came back (abridged)

> **What changed:** one line added in the existing gtag block. No second script or loader. The diff is one added line. After upload, the server file was compared byte for byte with the local one.
> **Backup:** `{ads_tag_plugin}.php.bak-pre-ga4` next to the file (original, compared byte for byte). Rollback: put it back.
> **Seen in HTML (200):** ads tag present (loader, config, conversion); GA4 config right after it; exactly one `gtag/js` loader; the old wrong ID absent; form present.
> **Didn't touch:** other files, form, prices, header, pixel; plugin version header left unchanged because the card didn't ask for it.
> **Didn't verify:** data arriving in GA4 real-time reports. The executor has no GA4 access, and that check wasn't part of the card.

Why this format works: the *Don't* list and the *Didn't touch / Didn't verify* sections make scope creep visible, and the report records the evidence, not only the claim.

## Second example: verification table from a report

Card: "Return 403 for junk spam URLs that currently render the full homepage with 200. Never block UTM, gclid or fbclid links, the form, admin or REST."

| URL pattern | Before | After |
|---|---|---|
| `/?shop%2Fitems%2F<id>%2F` (junk) | 200, full homepage | **403**, 9 bytes |
| `/` | 200 | **200**, identical size |
| `/?utm_source=…&utm_medium=paid&utm_campaign=…` | 200 | **200**, identical size |
| double-encoded variant, HEAD request | — | 403 |
| POST to a junk URL | — | 200 (POST deliberately not filtered) |
| `/?gclid=…` | — | 200 |

## Design review flow (proposals ≠ decisions)

1. The owner asks for a review. The design chat looks at the live page **and** the mirrored CSS, not at build memory.
2. The snapshot goes to `09-ops/reviews/YYYY-MM-DD-design.md`: what was looked at, what wasn't, a one-paragraph verdict, what already works (so the next edit doesn't break it), and numbered findings `F1…`.
3. Proposals go to `design-backlog.md` (`D1…`), each pointing to a finding.
4. Only items the project chat has decided become cards.

The first review scored Client A's landing page 7/10 as an ad landing page and 5/10 as a reusable design system. That's why the clean-up items went to the backlog instead of becoming one-off fixes.
