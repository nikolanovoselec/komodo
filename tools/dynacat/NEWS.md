# News Digest integration

The Endpoints & Services page intentionally shows a compact link to
https://news.graymatter.ch/ and a pending-integration notice, not sample articles.
The former BBC / Ars Technica / The Register RSS widget has been removed.

## Read-only discovery (2026-09-15)

Requests were unauthenticated and did not follow redirects:

| Route | Result |
| --- | --- |
| `/` | HTTP 200, HTML landing page: **News Digest — personalised daily tech news** |
| `/feed` | HTTP 404, HTML |
| `/rss.xml` | HTTP 404, HTML |
| `/api` | HTTP 404, HTML |
| `/api/articles` | HTTP 404, HTML |
| `/digest` | HTTP 303, Location `/` |

The landing page identifies an LLM-curated daily tech digest by Gray Matter
GmbH, with Astro-generated assets. It advertises GitHub and Google application
sign-in, with POST form actions `/api/auth/github/login` and
`/api/auth/google/login`. No sign-in was attempted. No verified article feed/API
was discovered. These observations do not establish an upstream product name
or rule out other authenticated routes.

The root currently returns the application's own sign-in page, **not** a
Cloudflare Access challenge. Cloudflare service credentials alone may therefore
be insufficient: the application also needs a supported server-to-server,
user-scoped article endpoint.

## Future server-side authentication

Once supplied and provisioned as deployment secrets, map:

- `DYNACAT_NEWS_CF_CLIENT_ID` → request header `CF-Access-Client-Id`
- `DYNACAT_NEWS_CF_CLIENT_SECRET` → request header `CF-Access-Client-Secret`

Send these only from the server-side collector to the explicitly allowlisted
News Digest origin. Never put their values in frontend HTML/JS, URL parameters,
logs, browser storage, tracked configuration, or commits. Do not forward them
across redirects. No unresolved Komodo/TOML variable or runtime secret reference
has been added by this change.

Before enabling article polling:

1. Confirm the exact supported article endpoint and any application-level
   authentication/user scope with the site owner.
2. Provision the Cloudflare service token and the site's Service Auth policy if
   required; independently satisfy the application's authorization requirements.
3. Verify real article JSON or RSS/Atom, not HTTP-200 login HTML. Reject login
   redirects and show an explicit unavailable state rather than fabricated data.
4. Normalize, escape and cache article titles, URLs and publication times
   server-side; verify real articles in the staged dashboard before deployment.

## Personalized YouTube recommendations

The inspected Hermes-controlled browser showed **Sign in**, an untouched
consent dialog, and **Your YouTube history is off** at https://www.youtube.com/.
No authenticated recommendation session was available on this browser surface.
No cookies, tokens or browser credentials were read or copied; no consent or
account setting was changed. This does not establish the state of another
browser/profile on the user's workstation.

The official [activities.list documentation](https://developers.google.com/youtube/v3/docs/activities/list)
says the `home` parameter is deprecated and returns content similar to a
logged-out homepage, not the user's personalized Home recommendations.
`mine=true` retrieves the user's own activities, not recommendations. A public
API key or ordinary OAuth authorization therefore does not provide the requested
personalized strip through that endpoint.

No generic videos have been substituted. A durable, explicitly authorized
source of the user's actual recommendations must be identified before adding
this feature; merely signing in for a one-off browser scrape is not a secure,
maintainable server-side integration.
