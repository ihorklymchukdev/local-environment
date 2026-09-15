---
name: omelet-setup
description: Use when the owner wants a project set up, imported, cloned or running in this Omelet VM — a repository URL, an archive, a folder, or a new app described in plain words — and whenever they ask for a link to open. Use it even when the request is one sentence; it decides how much process the request needs and hands off to the other omelet skills.
---

# Setting up a project with Omelet

Projects live in `~/projects/<name>/`, one folder each. Omelet runs them in Docker and gives
each one a URL. The owner is not technical: decide everything yourself, in the open, and never
ask them about technology. What you do ask, you ask one question at a time.

## 1. Get the project into ~/projects

| The owner gives you | Do |
|---|---|
| A description of an app | `omelet new <name>`, then flow A |
| A repository URL | `omelet clone <url>` — it also starts the project if it can; then flow B |
| An archive (zip, tar) | unpack it so its `docker-compose.yml` sits directly in `~/projects/<name>/`; flow B |
| A folder already in `~/projects` | flow B |
| A folder elsewhere in the VM | move it into `~/projects/`; flow B |
| A change to a project that is already here | flow C |

If `omelet up` asks you to rename the folder, rename it to the name it gives and run
`omelet up` again. If it says the compose file has another name (`compose.yaml`,
`compose.yml`, `docker-compose.yaml`), rename that file to `docker-compose.yml` and run
`omelet up` again.

If `omelet clone` could not download the repository, read git's message. For a missing or
private repository, tell the owner in plain words that it cannot be reached and needs access
or a correct link; do not ask for tokens or keys unprompted.

## Flow A: a new app from a description

Every step writes a file the next session reads, so nothing is decided twice.

1. **Use `omelet-brainstorm`** → `docs/brief.md`, confirmed by the owner.
2. **Use `omelet-stack`** → `docs/stack.md` and the recipe to follow.
3. **Use `omelet-rules`** → `AGENTS.md`, `CLAUDE.md`, git initialised.
4. **Use `omelet-plan`** → `docs/plans/<date>-first-slice.md`, then work it. Its first step is
   the scaffold, the compose file, `omelet up` and a URL that answers; nothing else lands
   before that.
5. Tell the owner the URL and what they can try, in one plain paragraph.

Do not skip to writing code because the idea sounds small. A description that already answers
every brainstorm question still gets the one-message confirmation, the stack record and the
rules; they take minutes and save the rebuild.

## Flow B: an imported project

1. Has `docker-compose.yml` → section 3. No compose file → **use `omelet-stack`** (its
   *Existing project* path detects the stack and writes the compose file from the recipe) →
   section 3.
2. Once the URL answers: **use `omelet-rules`** (its *Existing project* path) so the project
   has `docs/brief.md`, `docs/stack.md` and `AGENTS.md` before anyone changes it. The URL
   comes first because it is what the owner is waiting for; the notes take minutes.
3. Then the owner's change, if they asked for one → flow C.

## Flow C: a change to a project that is here

Size it first, by what you can observe:

| Size | Test | Do |
|---|---|---|
| Small | the finished result fits in one sentence and touches a few files | say what you will do in one message, do it, check it, commit |
| Feature | adds a capability (accounts, payments, an editing screen, a new screen flow, an outside service), touches many files, or the result does not fit one sentence | **use `omelet-brainstorm`** → spec; **use `omelet-plan`** → plan, then work it |

When in doubt, the larger size. A small change that grows while you work is re-sized to a
feature there and then — spec, plan, continue — never finished as if it were still small.
No `AGENTS.md` in the project → **use `omelet-rules`** before either.

## 2. The Omelet compose contract

Every compose file, written by you or adapted from a recipe, follows this; the recipes under
`omelet-stack` already do.

- Everything runs in `docker-compose.yml`. Language tools run inside containers
  (`docker compose run --rm <service> <command>`); never install them on the VM.
- The app listens on `0.0.0.0`, not `127.0.0.1`, or its URL never answers.
- No host ports are published. Omelet is told which service serves the web page in
  `.omelet/project.yml`, with only a `web:` key:

  ```yaml
  web:
    - service: app
      port: 3000
  ```
  With several web services, the first keeps the bare project address and the others get a
  `<service>.` prefix.
- The source is mounted into the container and a development server reloads on change, so
  edits show when the owner refreshes.
- Data lives in a named volume (SQLite file or a database service), never in the source tree.
- `.omelet/overlay.yml` is generated; never edit it.

## 3. Start it and prove it works

1. Run `omelet up` inside the project folder. It prints the URL.
2. Check the URL answers before telling the owner it works:
   `curl -s -o /dev/null -w '%{http_code}\n' <url>`. Some stacks take a while on first start;
   poll for a minute before reading it as failure.
3. On a failure or no answer: read `omelet logs`, fix the cause, run `omelet up` again.
4. Give the owner the URL in one plain sentence, with any login you created for them.
