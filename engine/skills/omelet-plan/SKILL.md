---
name: omelet-plan
description: Use when a brief or spec exists and code is about to be written for it, when a change adds a capability or touches many files, or when a file under docs/plans has unticked steps to continue — "build the first version", "add accounts", "continue where we left off". Use it before writing the code, not after; a landing-page-sized change confirmed in one message does not need it.
---

# Planning, then building one checked step at a time

Agents build better from a written list of small, checked steps than from a brief held in
mind: each step has a test of done, nothing is half-built when the session ends, and a new
session — or the other agent sharing this VM — continues from the file instead of from
memory. The owner never reads the plan; they get the URL and plain words at the end.

## Input

`docs/brief.md` (a new project: its *First slice* section) or `docs/specs/<date>-<slug>.md`
(a change). No brief or spec → **use `omelet-brainstorm`** first. No `AGENTS.md` → **use
`omelet-rules`** first.

## Write `docs/plans/<date>-<slug>.md`

A numbered list of steps. Each step is small enough to do and check in one go, and holds:

- **Files** it touches.
- **Change**: what is written, specific enough that another session could do it.
- **Check**: how you know it worked — a curl against the project URL, a page to open and what
  it must show, a command through compose, a test to run.
- A checkbox.

Rules of shape:

- The first step of a new project is always: scaffold from the recipe, `docker-compose.yml`,
  `.omelet/project.yml`, `omelet up`, the URL answers 200. Nothing else lands before the URL
  works.
- A step that adds a screen ends with the owner being able to open it.
- Data model before screens that show it; the editing screen before the pages that display
  edited content, so the owner can put real content in early.
- Items in the brief's *Later* section are not steps.

```markdown
# First slice — plan

Spec: docs/brief.md (First slice)

- [ ] 1. Scaffold and run
  Files: docker-compose.yml, .omelet/project.yml, wp-content/
  Change: the WordPress recipe as written; `omelet up`.
  Check: `curl -s -o /dev/null -w '%{http_code}' <URL>` prints 200 (install page).
- [ ] 2. Install and create the editor login
  Files: —
  Change: `wp core install` with the printed URL; theme twentytwentyfive; admin user "owner".
  Check: `<URL>/wp-admin` shows the login; logging in shows the dashboard.
- [ ] 3. Menu as content the sister edits
  Files: wp-content/themes/bakery/ (child theme), functions.php
  Change: a "Menu item" post type with price and photo; a menu page listing them.
  Check: add one item in wp-admin with a photo; `<URL>/menu` shows it.
- [ ] 4. Home page: hours, address, phone
  Files: wp-content/themes/bakery/front-page.php, style.css
  Change: hours and address as site options editable under Settings; front page shows them.
  Check: change the hours in wp-admin; the home page shows the new hours.
```

## Execute

1. Take the first unticked step. Do it.
2. Run its check. It fails → fix inside the step; do not move on with a red check.
3. Tick the step in the file. Commit ("Menu page shows items the sister adds").
4. The step turns out to hide more work than one go → split it in the file into two or three
   steps, tick what is done, continue. Never push through a step that grew.
5. All ticked → open the URL once more, then tell the owner in plain words what they can now
   do and where, with the URL and any login you created.

## Resume

A session that finds a plan with unticked steps continues from the first unticked one. Read
`AGENTS.md` and the plan's spec first; do not re-plan what is already written unless the spec
changed.

## Common mistakes

- Steps without a check, or with "verify it works" as the check. Name the URL, the command,
  the expected output.
- Ticking a step before its check has run.
- A first step that writes application code before `omelet up` has printed a URL.
- Planning the *Later* section because it was easy to reach from here.
- Finishing with "done" instead of the URL and what the owner can try.
