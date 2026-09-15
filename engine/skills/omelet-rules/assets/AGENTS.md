# <Project name>

<!-- Fill every section from docs/brief.md and docs/stack.md. Remove a section that does not
apply rather than leaving it empty. Delete these comments. A page, not a manual. -->

## What this is
<!-- Two sentences: what it does and for whom. Point at the brief and the stack record. -->
… See `docs/brief.md` for what the owner asked for and `docs/stack.md` for why it is built
the way it is.

## Running it
- `omelet up` starts it and prints the URL. `omelet status` shows what is running,
  `omelet logs` shows why something is not.
- Never `docker compose up` directly: the project gets no URL that way.
- Language tools run inside the containers: `docker compose run --rm <service> <command>`.
  Nothing is installed on the VM.
- `.omelet/overlay.yml` is generated; never edit it. `.omelet/project.yml` is ours.

## Layout
<!-- Five lines at most: where pages, data models, styles and tests live. -->

## Conventions of this stack
<!-- Only what is not obvious from the framework's own docs: how migrations are made and
committed, where a new page goes, the formatter if the framework ships one, how an admin user
is created. Copy the exact commands from the recipe. -->

## Testing
A test must be able to fail for a reason that matters. If you cannot name the bug it would
catch, do not write it.
- Do not write tests that only prove a function exists, that the framework works, or that a
  type accepts a value. Do not write tests to raise coverage.
- Do write tests for logic with branches and edge cases: dates and boundaries, prices and
  totals, parsing, permissions, mapping data into what a screen shows.
- Test through the public surface (a URL, a form, a function the rest of the code calls),
  not private internals, so a refactor that keeps behaviour keeps the tests.
- When unsure, do not write the test, and say what was left untested.

## Comments
Only for edge cases, workarounds and logic that is not obvious from the code. Two specific
lines beat a paragraph. Never restate what the code says.

## Talking to the owner
- Plain words. No technical questions: decide yourself and say what you decided.
- One question per message when something only they can answer.
- Always give the URL. Before saying something works, open it:
  `curl -s -o /dev/null -w '%{http_code}\n' <url>`.
- Say plainly when something failed or was skipped.

## Git
Commit after each working step, with a message that says what changed for the owner
("Menu page shows photos", not "update templates"). Never commit `.env`, uploads or
generated folders.

## Working on changes
Size it first. Small (fits in one sentence, a few files): confirm in one message, do it,
check it, commit. Feature (a new capability, a new screen flow, many files, or you cannot say
the result in one sentence): write `docs/specs/<date>-<slug>.md`, then `docs/plans/<date>-<slug>.md`,
then work the plan step by step. When in doubt, the larger size.

## Keeping this file current
- Learned something non-obvious about this project (a gotcha, a command, a decision)? Add it
  here, in the section it belongs to.
- A part of the project with its own rules gets its own `AGENTS.md` in that folder.
- A changed stack decision goes into `docs/stack.md`, with the reason.
