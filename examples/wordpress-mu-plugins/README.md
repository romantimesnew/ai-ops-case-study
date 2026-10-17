# WordPress mu-plugin examples

Generic versions of small must-use plugins the executor agent wrote and shipped from task cards. Client names, IDs and hosts are replaced with constants you define in `wp-config.php`.

Why mu-plugins: they're always on, can't be switched off by accident in the admin, survive theme updates, and each one is a single file that's easy to mirror into the repo and roll back (delete the file).

| File | What it does |
|---|---|
| `ads-conversion-tag.php` | One gtag loader for Google Ads + GA4; Ads conversion on the form plugin's success event only |
| `preview-only-pixel.php` | Meta Pixel `PageView` + `Lead`, hard-guarded to run only on the preview host |
| `preview-guard.php` | Makes a preview copy safe: noindex everywhere, no sitemaps, all outgoing mail and chat notifications blocked |
| `junk-url-403.php` | Returns 403 for spam URL patterns before WordPress renders anything; never touches POST, admin, REST, UTM or click IDs |
| `form-to-chat-notify.php` | Forwards successful form submissions to a team chat channel; fails soft and never logs tokens |
| `lead-events.php` | *(added 2026-10-17)* GA4 `generate_lead` / `phone_click` / `messenger_click` with placement parameters, plus Ads lead (primary) and phone (secondary) conversions. Deployed on production 2026-10-16, verified with one test lead and one test call on 2026-10-17 |
| `legacy-301-redirects.php` | *(added 2026-10-17)* 301s for old URLs that still get search clicks, before WordPress routing; query strings kept; same file safe on preview and production |
| `theme-file-rest.php` | *(added 2026-10-17)* Regular plugin, not mu: child-theme file read/write over REST for the executor when the host's file channel is unreliable; admin-only, realpath-guarded, extension allowlist, no deletes |

Each file was verified by the executor with explicit before and after checks (HTTP codes, page HTML, event counts) recorded in its report.
