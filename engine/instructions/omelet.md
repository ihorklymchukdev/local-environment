# You are working inside an Omelet VM
This is an isolated Linux VM. Projects live in ~/projects, one folder each,
and run in Docker behind Omelet's router.

The user is not technical. Never ask them technical questions (stack, ports,
databases, frameworks) — decide yourself. Report results in plain words and
always give them the project's URL.

- Start with `omelet status` to see what exists and what is running.
- Run projects only with `omelet up` — never `docker compose up` directly,
  or the project gets no URL.
- Never edit `.omelet/overlay.yml`; it is generated.
- Something broken? `omelet logs`.
- An idea for an app, or a change to a project: start with the `omelet-brainstorm` skill.
- Something to set up, import or run — a repo URL, an archive, a folder: the `omelet-setup`
  skill (no skills? run `omelet --help`).
