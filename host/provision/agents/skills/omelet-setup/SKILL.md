---
name: omelet-setup
description: Set up, create, import, clone or run a project in this Omelet VM — a repository URL, an archive, a folder, or a new app described in plain words. Use whenever the user wants something running with a link to open.
---

# Setting up a project with Omelet

Projects live in `~/projects/<name>/`, one folder each. Omelet runs them in
Docker and gives each one a URL. The user is not technical: choose everything
yourself and never ask them about technology.

## 1. Get the project into ~/projects

| The user gives you | Do |
|---|---|
| A repository URL | `omelet clone <url>` — it also starts the project if it can |
| An archive (zip, tar) | unpack it so its `docker-compose.yml` sits directly in `~/projects/<name>/` |
| A folder already in `~/projects` | go to step 2 if it has no `docker-compose.yml`, otherwise step 3 |
| A folder elsewhere in the VM | move it into `~/projects/` |
| A description of an app | `omelet new <name>`, then build it there following step 2 |

If `omelet up` asks you to rename the folder, rename it to the name it gives
and run `omelet up` again. If it says the project's compose file has another
name (`compose.yaml`, `compose.yml`, `docker-compose.yaml`), rename that file
to `docker-compose.yml` and run `omelet up` again.

If `omelet clone` could not download the repository, read git's message. For a
missing or private repository, tell the user in plain words that it cannot be
reached and needs access or a correct link; do not ask for tokens or keys
unprompted.

## 2. Writing a compose file (new apps, or projects without one)

- Pick the simplest mainstream stack for the job yourself.
- Everything runs in `docker-compose.yml`. Run language tools inside containers
  (`docker compose run --rm <service> <command>`); never install them on the VM.
- The app must listen on `0.0.0.0`, not `127.0.0.1`, or its URL never answers.
- Publish no host ports. Tell Omelet which service serves the web page in
  `.omelet/project.yml`, with only a `web:` key:

  ```yaml
  web:
    - service: app
      port: 3000
  ```
- Mount the source into the container and run a development server that
  reloads on change, so edits show when the user refreshes the page.
- Keep data in SQLite, or in a database service with a named volume.

## 3. Start it and prove it works

1. Run `omelet up` inside the project folder. It prints the URL.
2. Check the URL answers before telling the user it works:
   `curl -s -o /dev/null -w '%{http_code}\n' <url>`.
3. On a failure or no answer: read `omelet logs`, fix the cause, run
   `omelet up` again.
4. Give the user the URL in one plain sentence.
