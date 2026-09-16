---
name: omelet-rules
description: Use when a project in ~/projects has no AGENTS.md or CLAUDE.md, when an imported repository is about to be worked on for the first time, or right after the stack of a new project has been chosen — before the first line of code is written or changed in it. Also use when the owner asks to "set up rules", "document the project", or when two sessions have visibly worked differently on the same project.
---

# Writing the rules of the house

Two coding agents share this VM (Claude Code and Codex) and neither remembers the last
session. Rules that are not written down are re-decided every time: one session writes
tests for coverage, the next deletes them; one commits after each step, the next leaves a
week of work uncommitted. `AGENTS.md` is where the project says how it is worked on.

`AGENTS.md` is the source. `CLAUDE.md` contains one line, `@AGENTS.md`, so both agents read
the same file. The project's documents live next to it:

| File | Holds | Written by |
|---|---|---|
| `AGENTS.md` | how this project is worked on | this skill |
| `CLAUDE.md` | `@AGENTS.md` | this skill |
| `docs/brief.md` | what the owner asked for | `omelet-brainstorm`, or this skill when reconstructing |
| `docs/stack.md` | what it is built with and why | `omelet-stack`, or this skill when detecting |
| `docs/specs/`, `docs/plans/` | one file per change | `omelet-brainstorm`, `omelet-plan` |

## Which path

**The project already has code** → *Existing project* below. Otherwise → *New project*.

## New project

`docs/brief.md` and `docs/stack.md` exist (if not, **use `omelet-brainstorm`** and
**`omelet-stack`** first).

1. Copy `assets/AGENTS.md` to the project root and fill every section from the brief, the
   stack record and the recipe `omelet-stack` used: the exact run, migration and admin-user
   commands, the folder layout the scaffold produced. Remove sections that do not apply and
   every `<!-- … -->` hint.
2. Write `CLAUDE.md` containing exactly `@AGENTS.md`.
3. `git init` if the folder is not a repository; write `.gitignore` from the recipe; commit
   everything so far as "Project set up: <stack in three words>".

Then hand back to **`omelet-setup`**, which continues with `omelet-plan`.

## Existing project

An imported repository was written by someone else with their own habits. Learn them before
writing anything; the rules must describe this project, not a generic one.

1. **Explore**, without changing anything: manifests (`package.json`, `requirements.txt`,
   `composer.json`, `Gemfile`…), entrypoints, how it is run and tested (`Makefile`, scripts,
   CI files), folder layout, migrations, existing `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`,
   `README`.
2. **Reconstruct `docs/brief.md`** from what the code does — the same sections
   `omelet-brainstorm` writes — and say it back to the owner in plain words: "As far as I can
   see, this tracks orders for the shop and staff enter them by hand. Is that right, and is
   anything missing?" Write the file after the answer, marking anything the owner corrected.
3. **`docs/stack.md`** with `Detected, not chosen.` as its first line, unless `omelet-stack`
   already wrote it (imports without a compose file go through that skill first).
4. **`AGENTS.md`**:
   - none exists → the template, filled from what you found; the *Conventions* section quotes
     the project's own commands (`make test`, its migration command), not the recipe's.
   - one exists (or a `CLAUDE.md` with content) → keep it whole and append a block between
     `<!-- omelet:begin -->` and `<!-- omelet:end -->` holding only *Running it*, *Talking to
     the owner*, *Working on changes* and *Keeping this file current*. The markers let the
     block be replaced later without touching the owner's text. If a `CLAUDE.md` with content
     exists and no `AGENTS.md`, treat `CLAUDE.md` as the source and create `AGENTS.md` with
     `@CLAUDE.md` instead.
   - a `CONTRIBUTING.md` says how tests and migrations run → point at it from *Conventions*
     rather than copying it.
5. Commit, if the repository is git: "Omelet: project notes and rules".

## Keep it small

A page the next session reads in a minute. Framework documentation is not repeated; what is
specific to this project is. If a section grows past ten lines, the extra belongs in a file
under `docs/` with a one-line pointer here.

## Common mistakes

- Leaving template hints (`<!-- … -->`) or the `…` placeholders in the written file.
- Restating the framework's docs ("Django uses `manage.py`") instead of this project's habits
  ("migrations are committed; make them with `docker compose run --rm web python manage.py makemigrations`").
- Overwriting an existing `AGENTS.md`, `CLAUDE.md` or `CONTRIBUTING.md`. The owner's or the
  previous developer's text stays; ours goes in the marked block.
- Writing the brief for an imported project without saying it back to the owner first.
- Writing rules and then not following them in the same session.
