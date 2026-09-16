---
name: omelet-stack
description: Use when a brief exists and no code does, when a project in ~/projects has no docker-compose.yml, or when the owner wants something added that changes what the project is made of — an editing screen, accounts, a shop, payments, answering questions from documents, a database. Use it before any framework, language or product is named, even when one seems obvious; the choice is recorded in docs/stack.md and read by every later session.
---

# Choosing the stack

## The client

The people who will maintain this project are a coding agent and an owner who cannot read
code. That changes the usual trade-offs:

- **Conventions over elegance.** The agent works from what it has seen most; the framework with
  the deepest documentation and the most examples is the one it changes correctly.
- **Batteries over toolkits.** Every future change means fewer decisions when auth, admin,
  migrations and forms already exist in the framework.
- **Buy the commodity parts.** Login, admin screens, content editing, payments, email are
  products or libraries. Custom versions of them are where the owner's money disappears.

## Principles, in priority order

1. **Cover every need in the brief natively.** An editing screen is the simple choice when the
   brief names an editor and bloat when it does not. "Simplest" is measured after the needs are
   known, never before.
2. **Boring and mainstream.** Deepest docs, biggest community, LTS releases. Nothing released in
   the last year, nothing with a small community, however elegant.
3. **Buy the commodity parts.** A hand-rolled login or admin panel is a decision failure, not a
   feature.
4. **One language front and back** unless a need demands a second. Never three.
5. **SQLite until** several people write at once or a chosen product needs Postgres or MySQL.
   Then one database service with a named volume.
6. **Reversible where cheap, recorded where not.** Keep an ORM in front of the database. Write
   down why this framework, so the next session does not reopen it.
7. **Fits Omelet.** Everything in compose; a dev server that reloads on the mounted source;
   listens on `0.0.0.0`; no published host ports; web services declared in
   `.omelet/project.yml`; starts in seconds.

## The ladder: adopt, assemble, build

Walk it top down and stop at the first rung that covers the brief.

1. **Adopt** a mature open-source product when it covers the whole need. Run it in compose and
   customize through its own themes, plugins and settings. The owner gets a finished editing
   screen and years of documentation; the agent gets a product it has seen thousands of times.
   Sites and blogs: WordPress. Publishing and newsletters: Ghost. Shops: WooCommerce, Magento
   Open Source, PrestaShop. Data with an editing screen and an API: Directus, Strapi.
   Dashboards on existing data: Metabase. Automation: n8n. Bookings: Cal.com. Communities:
   Discourse. Inventory, invoicing, CRM: Odoo. Team wiki: BookStack, Outline. Public docs:
   Docusaurus.
2. **Assemble** when a product covers a part and the rest needs a custom face: a framework front
   with a headless product behind it (Astro or Next.js with Payload or Strapi; Next.js with Medusa).
3. **Build** on a batteries-included framework when nothing fits, in the ecosystem the hardest
   need points to.

## Choosing the ecosystem when building

There is no default language. Each ecosystem has a home ground; pick the one where the brief's
hardest need is native.

| Ecosystem | Home ground | Typical picks |
|---|---|---|
| PHP | content sites, shops, anything near WordPress or Magento, business apps with staff screens; the cheapest hosting when the owner goes online later | WordPress, Laravel + Filament |
| Node / TypeScript | rich interactive screens, live updates, one language front and back, the largest frontend ecosystem; smart features that are only calls to a model (AI SDK) | Next.js, Astro, Hono, Prisma |
| Python | processing documents and data, embeddings, ML libraries, scientific and automation work; business apps that are mostly forms and an admin | Django (+ admin), FastAPI, Streamlit |
| Ruby | business apps; mature, smaller pool — an accepted alternative, not a default | Rails |
| Go, Java, .NET | only when integrating with an existing system that already uses them | — |

A chat feature alone does not pull a project to Python: a JS app calls a model through an SDK.
Reading, splitting, embedding or analysing documents does, because those libraries live there.

**Tie-breakers, in order:** the ecosystem where the hardest need is covered natively → where the
project can be hosted or handed over most easily later (the brief's *Where it will live*) →
documentation depth → consistency with the owner's other projects in `~/projects`.

## Archetypes

Match the brief to a row. Candidates are product first; the condition says when each wins.

| Shape | Candidates and when each wins |
|---|---|
| Landing page, portfolio, brochure site | Astro static when the owner edits rarely; WordPress when a non-technical person edits |
| Content site, blog, publication | WordPress (widest); Ghost (publishing, newsletters, memberships); Astro or Next.js + Payload/Strapi/Directus when a custom front matters more than the editing screen |
| Shop | WooCommerce (small, content-heavy shop); Magento Open Source (large catalog, B2B pricing, several stores or currencies); PrestaShop (EU small business); Medusa + Next.js storefront (the shopping experience is the product); Saleor (a Python house, GraphQL) |
| Business app: bookings, inventory, CRM-lite, forms with staff behind them | Odoo when it is really ERP, CRM or invoicing; Laravel + Filament; Django + admin; Rails |
| Bookings or appointments only | Cal.com; otherwise the business-app row |
| Rich interactive app: dashboards with heavy client screens, editors, drag-and-drop | Next.js + Prisma + Auth.js; SvelteKit as an accepted alternative |
| Smart app: chat, questions over documents, generation | Next.js + AI SDK when the smart part is model calls in a JS app; FastAPI or Django + Next.js when documents are processed, embedded or analysed; Streamlit alone for an internal tool for a few people |
| Data or internal dashboard | Metabase on an existing database; Streamlit to build quickly; Django when it needs accounts and forms |
| Automation, bots, scheduled jobs | n8n; Python + scheduler + a small status page |
| Backend only, for a phone app or other systems | FastAPI or Hono, with OpenAPI docs |
| Live collaboration, chat between users | Next.js + Socket.IO + Postgres + Redis |
| Community, forum | Discourse |
| Docs, wiki, knowledge base | Docusaurus (public docs); BookStack or Outline (team wiki) |

**Overrides that cut across rows**

- A non-technical editor in the brief → an editing screen exists: the product's own, Django
  admin, Filament, or Payload. Never a custom one.
- Public accounts → an auth library or the product's own accounts. Never hand-rolled.
- A CMS, a shop, or several people writing at once → Postgres or MySQL, whichever the product
  prefers.
- Payments → Stripe through its official library. Card data is never stored.
- Documents or data processed → Python for that part, keeping the row's frontend.

**Anti-patterns**: microservices; more than two languages; hand-rolled auth or admin; a
framework chosen because it is new; anything justified by "we might need it later"; asking the
owner to choose between technologies.

## Rationalizations that end in a rebuild

These are the exact thoughts observed in agents that built the wrong thing.

| Thought | Reality |
|---|---|
| "A full CMS is overkill for a menu and photos; a small admin page is simpler" | The admin page is a login, a form, an upload, image resizing and a data model — a product ships all of it, documented, with videos the owner can watch. Every field the owner asks for later is code in yours and a click in theirs. |
| "She would have to learn WordPress" | She would have to learn your admin too, with no documentation and nobody but you to ask. |
| "Two services and a database are more to maintain" | Two images with a version tag are less to maintain than a thousand lines of custom code. |
| "No login needed, it is only on this computer" | The brief says colleagues use it. Accounts come from the product or a library now, or from a rewrite later. |
| "I will keep it simple with Flask/Express and add things as needed" | Batteries you add one by one are the assembled toolkit principle 1 warns about. Start with the framework that has them. |
| "Python is fine for this, I know it best" | The owner's hosting and the hardest need choose the ecosystem; the tie-breakers are in order for a reason. |

## Existing project: detect, do not choose

A project that already has code has already chosen. Read the manifests and write compose for
what is there, from the matching recipe when one exists.

| Found | Stack |
|---|---|
| `package.json` with `next` / `astro` / `@sveltejs/kit` / `express` / `hono` | Node; that framework |
| `manage.py` | Django |
| `pyproject.toml` or `requirements.txt` with `fastapi` / `django` / `streamlit` / `flask` | Python; that framework |
| `composer.json` with `laravel/framework`; `wp-config.php` or `wp-content/` | Laravel; WordPress |
| `Gemfile` with `rails` | Rails |
| `go.mod`, `pom.xml`, `build.gradle`, `*.csproj` | Go, Java, .NET — use the project's own Dockerfile if present |
| a `Dockerfile` | build from it; still add the compose file and `project.yml` |

## Record the decision: `docs/stack.md`

Every later session reads this instead of deciding again. Sections, in order:

```markdown
# Stack

## Needs
- non-technical editor changes menu and photos weekly
- public visitors, no accounts
- cheap shared hosting later

## Ladder step
Adopt: WordPress.

## Why
An editing screen for a non-technical person is the hardest need; WordPress ships it, and
the hosting the owner named runs it everywhere. One language (PHP), one database (MySQL).

## Rejected
- Astro static: the sister cannot edit Markdown files.
- Astro + Payload: a custom front the brief does not ask for, two services to maintain.

## Would change this if
Online ordering becomes real → WooCommerce on the same site, no rebuild.

## Services
- wordpress: image wordpress:6-php8.3-apache, the site, volume wp_data
- db: image mysql:8, volume db_data
```

For an existing project the first line under the title is `Detected, not chosen.` and *Rejected*
is omitted.

## Then

Read the recipe for the choice and follow its compose skeleton: `references/astro.md`,
`references/nextjs.md`, `references/wordpress.md`, `references/woocommerce.md`,
`references/laravel.md`, `references/django.md`, `references/fastapi-nextjs.md`,
`references/streamlit.md`, `references/payload.md`, `references/medusa.md`,
`references/magento.md`. For any other product, start from its official docker compose file and
adapt it to the Omelet contract in principle 7. Then hand back to **`omelet-setup`**, which
continues with `omelet-rules`.
