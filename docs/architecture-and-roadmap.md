# Omelet: how it works, and where it should go

Two halves. Part 1 explains the machine as it exists today, assuming no prior contact with
Traefik, WSL or Lima. Parts 2 to 5 take the three directions you proposed — logic inside the
VM, no local UI, a public tunnel — and work out what each one actually costs.

---

# Part 1. How it works today

## 1.0 The problem

A person who is not a developer has a project that needs Docker. Giving them Docker Desktop
means a commercial licence, a heavy install, and a program whose state we do not control. So
we do not give them Docker Desktop. We give them a private Linux computer that lives inside
their own machine, put Docker in it ourselves, and hand back a web address.

Everything below is in service of that one sentence.

## 1.1 The virtual machine

A virtual machine is a whole computer simulated in software: its own operating system, its
own filesystem, its own network, isolated from the machine it runs on. Ours runs Ubuntu
Linux 24.04. The user never sees it and never logs into it.

Both operating systems can already do this. They just do it differently.

**On Windows: WSL2.** This stands for Windows Subsystem for Linux, version 2. It is not an
emulator and not a third-party product. It is a genuine Linux kernel that Microsoft ships as
part of Windows 10 and 11, running in a very lightweight virtual machine that boots in about
a second. You control it with a command called `wsl.exe`.

WSL2 can hold several separate Linux installations side by side, called distributions. Most
developers have one they use daily. **We never touch it.** We import our own, named
`omelet-vm`, from a downloaded Ubuntu image. It is invisible to the user's other work, and
deleting it harms nothing else.

**On macOS: Lima.** macOS has no built-in Linux, but since macOS 13 Apple ships a
virtualization framework in the OS. Lima is a small open-source tool that drives it and
gives us the same thing: an Ubuntu VM, managed by a command called `limactl`.

> Status note: the Windows path is implemented and exercised. The macOS path is written for
> parity and has never been run. Both source files carry an UNVERIFIED banner.

**The point of using two different tools:** what comes out of both is the same. Ubuntu 24.04
running standard Docker. Every layer above that is identical on Windows and macOS, so it is
written once. This is the single most important design decision in the project, and there is
a test that enforces it — `tests/test_no_platform_leak.py` scans every source file outside
the two provider modules for words like `sys.platform` and fails the build if it finds one.

## 1.2 Docker, installed by us, inside the VM

Once the VM exists, a setup script runs inside it once. It installs Docker from Docker's own
official repository, creates a shared network called `edge`, makes a folder for projects at
`/opt/omelet/projects`, and starts the traffic router described next.

The script is safe to run repeatedly. It finishes by writing a version number to a file at
`/opt/omelet/.bootstrapped`. On the next run, if the number already matches, it exits
immediately. That is how an app update can upgrade an existing VM instead of rebuilding it.

## 1.3 Traefik, or: why there is a receptionist

This is the part worth reading slowly, because it is where the magic is.

**The problem.** A container that serves a website listens on some port, say 8000. To reach
it from a browser you normally publish that port to your machine, and you visit
`localhost:8000`. That works for one project. With three projects it falls apart: two of them
both want 8000, the user has to remember which number is which, and every collision is a
support ticket. The blueprint puts it bluntly — the user should never have to learn the word
"port".

**The solution.** Put a receptionist in front of everything.

Traefik is a *reverse proxy*. A normal web server holds files. A reverse proxy holds nothing
and serves nothing of its own. It accepts every incoming request, decides which service the
request was meant for, forwards it there, and passes the answer back. Think of the front desk
in an office building. Every visitor comes through one door. They say who they are there to
see. The receptionist points them down the right corridor.

The "who they are there to see" is real. Every HTTP request carries a header called `Host`
containing the address the browser typed. Traefik reads it and routes on it. So:

```
myapp.<domain>  → Host: myapp.<domain>  → the myapp container
shop.<domain>   → Host: shop.<domain>   → the shop container
```

One door. Many corridors. **Exactly one port crosses from the VM to the user's machine:
39080.** Every project shares it. There is nothing to collide.

**How Traefik knows the corridors.** This is the second clever bit. Nobody edits a Traefik
config file when a project starts. Traefik is connected to Docker itself and continuously
watches it. When a container appears, Traefik reads the *labels* on it — labels are just
key-value tags you can attach to any container — and configures itself from them. Carrying
the analogy: every office hangs its own nameplate on its own door, and the receptionist walks
the corridor reading nameplates.

The labels that matter are three:

```yaml
traefik.enable: "true"                                    # route to me at all
traefik.http.routers.<name>.rule: "Host(`myapp.<domain>`)" # under this address
traefik.http.services.<name>.loadbalancer.server.port: "8000"  # I listen on this port
```

The container must also join the `edge` network, because that is the only network Traefik
looks at.

## 1.4 The address

Traefik routes by hostname, so each project needs its own name. Getting a browser to resolve
a made-up name normally means editing the system `hosts` file, which needs administrator
rights every single time — unacceptable for our user. Names ending in `.localhost` work
automatically in Chrome, Edge and Firefox, but not in Safari.

So the project uses **sslip.io**, a free public DNS service that answers with whatever IP
address is written into the name you ask for. Ask for `myapp.127-0-0-1.sslip.io` and it
replies `127.0.0.1`. Any prefix works, so every project gets a unique name that still points
at the user's own machine. Zero setup, works in every browser.

Final shape of a URL: `http://myapp.127-0-0-1.sslip.io:39080`

Only the name lookup leaves the machine. No request and no page content ever reaches
sslip.io. But note two consequences: a brand-new project name needs internet the first time
it is resolved, and some corporate networks and routers refuse to return loopback addresses
from public domains — a protection called DNS rebinding defence — which makes the address
fail to resolve on those networks while the VM is perfectly healthy.

## 1.5 End to end: what `omelet up` actually does

1. Reads the user's `docker-compose.yml` on the host.
2. Decides the project's identity. The folder name becomes the ID and the hostname.
3. Decides which service is the website. If a service publishes ports, it is a web service.
   If there is exactly one service, it is the one. Otherwise it stops and asks. The user can
   override all of this in an optional `.omelet/project.yml`.
4. Packs the whole folder into a compressed archive **in memory**, encodes it as text, and
   pipes it into the VM to be unpacked at `/opt/omelet/projects/<id>/`. Nothing is staged on
   the host disk.
5. Generates a second compose file at `.omelet/overlay.yml` containing the Traefik labels
   and the `edge` network.
6. Runs `docker compose -f docker-compose.yml -f .omelet/overlay.yml up -d` inside the VM.
7. Inspects the containers and classifies the outcome as started, failed to start, or crash
   looping.
8. Prints the URL.

**The user's compose file is never modified.** That is deliberate and load-bearing. Because
the routing lives in a separate generated file, the user's own file stays clean and will run
unchanged with a plain `docker compose up` on any ordinary server. That portability is the
reason this design exists at all — it is the same property that makes Part 2 possible.

## 1.6 Where the code runs today

This matters for Part 2, so it is worth stating plainly.

**Almost all the logic runs on the host, in Python, on Windows or macOS.** Compose parsing,
web detection, label generation, project identity, failure classification and the project
list are all host-side. The VM is treated as a dumb executor: the host builds shell command
strings and pushes them in one at a time.

```
HOST (Windows / macOS)                 GUEST (Ubuntu)
┌──────────────────────────┐          ┌─────────────────────────────┐
│ CLI + installer          │          │ dockerd                     │
│ compose parsing          │          │ traefik  :39080             │
│ web detection            │  shell   │ ├── project-a containers    │
│ label generation         │ ───────► │ └── project-b containers    │
│ failure classification   │ commands │                             │
│ project list (SQLite)    │          │ /opt/omelet/projects/      │
│ VM control               │          │                             │
└──────────────────────────┘          └─────────────────────────────┘
        localhost:39080  ───────────────────►  traefik :39080
```

## 1.7 What is broken or missing today

An honest list, because Part 2 fixes most of it as a side effect.

| Problem | Detail |
|---|---|
| **Projects cannot exceed about 24 KB** | The push passes the whole project as one command-line argument to `wsl.exe`, and Windows caps a command line at 32,767 characters. Measured: the bundled template is 452 bytes encoded and fine; the `omelet` package alone is 90 KB and would fail. One screenshot breaks it, as a raw Windows error rather than a useful message. |
| **There is no sync** | `up` copies once. Editing on the host does nothing until it is run again, and running it again overwrites anything changed inside the VM. |
| **A wrong bind address reports success** | An app listening on `127.0.0.1` instead of `0.0.0.0` inside its container starts fine and stays running, so it is classified as healthy, and the URL then returns a proxy error with no explanation anywhere. |
| **Only one port can cross the boundary** | `forward()` deliberately raises an error when the host and guest ports differ. So there is no way to reach a database in the VM from a tool like DBeaver. The blueprint calls this the second most requested feature after the URL itself. |
| **The macOS half is unverified** | Written, never executed. |
| **The local API server runs on the wrong side** | `agent/api/server.py` is a small JSON-RPC service, built early as the attachment point for a future UI. It currently runs on the host. |

---

# Part 2. Moving the logic inside the VM

> Your proposal: a thin VM shell for Windows and macOS, with all logic and structure inside
> the VM, so the same thing can be reused for cloud deployment.

This is the right call, and the existing code is unusually well positioned for it.

## 2.1 The inversion

Today the host is the brain and the guest is the hands. Flip it. Put a small service — call
it the **agent** — inside the VM. It owns projects, files, compose lifecycle, routing and
state. The host keeps only what genuinely cannot be done from inside a VM.

```
HOST (thin)                            GUEST (everything)
┌──────────────────────┐              ┌──────────────────────────────┐
│ preflight checks     │              │ AGENT (container)            │
│ enable hypervisor    │   HTTP over  │ ├── projects API             │
│ create / start / stop│ ───────────► │ ├── file storage + sync      │
│ port forward         │  one local   │ ├── compose lifecycle        │
│ autostart at login   │     port     │ ├── health + diagnosis       │
│ installer UX         │              │ └── state (SQLite)           │
└──────────────────────┘              │ dockerd                      │
                                      │ traefik :39080               │
                                      │ project containers           │
                                      └──────────────────────────────┘
```

## 2.2 What the host must keep

This list is irreducible. Everything on it is an operation on the VM from outside, so no
amount of restructuring moves it inward.

- Checking whether the machine can run a VM at all: Windows build number, virtualization
  enabled in firmware, WSL feature state, free disk.
- Turning on Windows features, which requires an elevation prompt, and handling the restart
  that follows.
- Downloading the Linux image and creating or importing the VM.
- Start, stop, destroy.
- Forwarding ports.
- Registering Omelet to start at login.
- The installer window, which is the only UI the user must see before an account exists.

That is roughly what the two provider files already contain. Call it 200 to 300 lines per
platform, changing rarely.

## 2.3 Make the agent a container

The strongest version of your idea. Do not install the agent into the guest OS — **ship it as
a Docker image** that runs inside the VM next to Traefik, with the Docker socket mounted so
it can manage sibling containers.

Consequences, all good:

- Installing the agent becomes `docker run`. The bootstrap script shrinks to: install Docker,
  create the `edge` network, start Traefik, start the agent.
- Updating the agent becomes an image pull. No host reinstall, no VM rebuild.
- **The guest OS stops mattering.** The unit of logic is an image, so it runs identically on
  WSL2, on Lima, and on any cloud server that has Docker. That is your cloud reuse, achieved
  by construction rather than by discipline.
- The agent can be written in whatever language suits it, independent of the host CLI.

## 2.4 The API the agent should expose

Roughly this surface, over HTTP with JSON:

| Area | Operations |
|---|---|
| Projects | create, list, get, delete |
| Files | upload archive, write file, read file, list tree, delete |
| Lifecycle | up, down, restart, rebuild, logs (streaming), status |
| Routing | which hostnames a project answers on, add or remove |
| Diagnostics | health, disk, Docker state, why-is-this-broken |
| System | agent version, upgrade |

Two demands on it that are easy to get wrong. **Logs must stream**, not return a blob, or the
UI is useless during a slow build. And **long operations must be jobs** with an ID that can be
polled, because a first image build can take minutes and no HTTP request should be held open
that long.

## 2.5 What this fixes for free

Look back at the table in 1.7. A real HTTP API kills the 24 KB command-line ceiling outright,
because files arrive as a request body rather than as a command argument. It gives you a real
place to put file sync, since the agent owns the canonical copy and can accept uploads, watch
for changes, or clone a git repository directly. It gives the health check somewhere to live,
so an app bound to the wrong address can be detected by probing it and reported honestly
instead of being called healthy. And the JSON-RPC server that already exists simply moves to
the side of the boundary where it belongs.

## 2.6 The migration is cheaper than it looks

The `agent/core/` package is already free of platform-specific code, and there is a test
that fails the build if anyone breaks that. It was written to keep Windows and macOS from
diverging. The unintended payoff is that the same property makes it portable *into the guest*
essentially unchanged — compose parsing, detection, label generation, identity, state and
classification can move as they are.

Sequence:

1. Wrap `agent/core/` in an HTTP service. Containerize it.
2. Have the bootstrap start that container.
3. Forward the agent's port from guest to host.
4. Point the existing CLI at the agent over HTTP instead of calling core directly.
5. Delete the host-side copies of the logic.
6. Reduce the providers to the list in 2.2.

Each step is independently shippable and independently testable.

## 2.7 The costs, stated plainly

- **Two release artifacts instead of one**: a host installer per platform, and an agent image.
  You need a version compatibility rule between them and a way to say "your agent is too old".
- **The agent holds the Docker socket**, which is equivalent to root inside the VM. Acceptable
  because that is the VM's entire purpose, but it means the agent must never expose an
  unauthenticated port beyond the VM boundary.
- **The debugging story changes.** When something breaks, the answer is now inside a container
  inside a VM. Budget for a diagnostics bundle command early, not late.

---

# Part 3. No local UI, management from the service

> Your proposal: skip building a desktop UI. The user creates an account on our service and
> manages projects from there.

Sound, for a real reason: a cross-platform desktop UI is a permanent tax, and a web UI ships
instantly to everyone. An account also buys identity, support, collaboration and billing in
one move. But there is one technical obstacle that decides the whole shape of the design, so
it needs settling first.

## 3.1 The obstacle: a web page cannot reliably talk to a local machine

Your service is a page on `https://app.yourservice.com`. The agent is inside a VM on the
user's computer. For the page to control the agent, the browser must connect to something
local — and browsers are steadily closing that door.

It is not flatly forbidden. Chrome and Firefox treat `localhost` as trustworthy and will
generally allow the call. But Safari has historically refused it, Chrome now requires a
special preflight negotiation for requests from public sites into private network addresses,
and that policy has been tightening release by release. Any product built on it inherits a
permanent risk of being broken by a browser update. Several have been.

You could work around it by giving the agent a real TLS certificate for a domain you own that
resolves to `127.0.0.1`, obtained per-installation. It works — several desktop products do
exactly this. It is also real machinery: your own DNS, per-install certificate issuance and
renewal, and a hard rule never to ship a shared private key, because it will be extracted and
the certificate authority will revoke it.

## 3.2 The recommendation: let the agent dial out

Do not let the browser reach the machine at all. **Have the agent open and hold a connection
outward to your service.** The browser only ever talks to your service, over ordinary HTTPS,
like any normal web app. Your service relays commands down the open connection.

```
browser ──https──► your service ◄──persistent outbound──── agent in the VM
                                    (WebSocket, held open)
```

Everything difficult evaporates. No mixed content, no private-network preflight, no
certificate on the user's machine, no inbound port, no firewall rule, works behind any
router. And critically, **this is the same connection Part 4 needs** — build it once and the
tunnel becomes an extension of it rather than a second system.

## 3.3 Binding a machine to an account

Use the pattern that TV apps use, because users already understand it.

1. The installer finishes and displays a short pairing code.
2. The user signs in to your service and enters the code.
3. The service issues the agent a long-lived device token, stored inside the VM.
4. From then on the agent connects and authenticates itself with that token.

The agent never accepts an inbound connection from anywhere, which means it needs no
listening port exposed and no local authentication story.

## 3.4 What must still work when the service is unreachable

Decide this deliberately, and say it in the product.

**Projects keep running.** Everything is local; a container does not care that a management
service is down. Nothing should be architected so that a service outage stops a user's work.

**Management stops.** No UI, no start and stop, no logs. Which is why the CLI should survive
as a maintained escape hatch rather than being deleted once the web UI lands. It is also the
tool you will need for support and for your own development.

## 3.5 What it costs

- **A trust conversation.** Project metadata, and possibly source and logs, now transit your
  servers. Be explicit and specific about what is sent, because your users' work is on their
  machine and they will notice.
- **You are now an uptime commitment.** If your service is down, nobody can manage anything.
- **Two systems to version.** A web UI and a fleet of agents at assorted versions in the
  field. The UI must degrade gracefully against an old agent.

---

# Part 4. Publishing an app through your service

> Your proposal: a proxy through our service to publish the app, like ngrok. How complicated
> is it?

**Mechanically: moderate, and much easier if Part 3 is built first.** The hard parts are not
the code.

## 4.1 How it works

You already have the important half. Traefik in the VM routes by hostname, and every project
already has one. A tunnel just extends that path across the internet.

```
visitor ──https──► your edge server ──over the agent's existing
                   (*.yourservice.app)  outbound connection──► agent ──► traefik :39080 ──► container
```

1. Public request arrives at your edge for `myapp-a7f3.yourservice.app`.
2. Edge looks up which connected agent owns that name.
3. Edge forwards the request down that agent's already-open connection.
4. Agent hands it to Traefik with the right `Host` header, exactly as a local browser would.
5. Response streams back the same way.

You need a wildcard DNS record and a wildcard certificate for the public domain, both routine.
The agent side is genuinely small, because it is forwarding to a proxy that already knows how
to route.

## 4.2 Build or buy

**Buy first.** Cloudflare Tunnel and the open-source frp both do this today, run as a
container, and can operate under your own domain. Integrating one is days of work: lifecycle,
naming, enable and disable per project.

**Build later, if volume justifies it.** Your own edge is weeks of work plus a permanent
operational burden — capacity, streaming, WebSocket passthrough, abuse handling, denial of
service. Only worth it when the economics or the product experience demand it.

Either way, do not invent a multiplexing protocol. That problem is solved.

## 4.3 The three risks that are always underestimated

**Abuse is the big one.** A service that hands anyone a public HTTPS address on your domain
will be used for phishing and malware distribution, and it will start within days of launch,
not months. Every provider in this space has landed here. You need abuse reporting and fast
takedown, an account behind every tunnel so there is someone to ban, rate limits on creation,
and probably an interstitial warning page for anonymous visitors — which is exactly why ngrok
shows one. Domain reputation is hard to earn and easy to lose. **Budget for this as a
feature, not as an incident.**

**Security, on the user's side.** These are development environments. They have debug
endpoints, seeded credentials, unauthenticated admin panels, and stack traces. Publishing one
to the internet is genuinely dangerous, and our user is by definition not equipped to judge
that. So: off by default, explicitly enabled per project, an unmissable warning, optional
password protection on the tunnel, and an expiry so that nothing stays public because someone
forgot.

**Bandwidth costs money** and flows through your infrastructure. Quotas from day one, not
after the first surprise bill.

## 4.4 Worth knowing

This same mechanism is how you would later offer "deploy this to the cloud". The difference
between a tunnel to a laptop and a deployment to a server is where the container runs, not
how traffic reaches it. If Part 2 is done properly, the agent is the same in both places.

---

# Part 5. Build order

Each phase depends on the one above it, and each is shippable on its own.

| Phase | Work | Unlocks |
|---|---|---|
| **1. Agent in the VM** | Wrap `core/` in an HTTP service, containerize it, start it from bootstrap, point the CLI at it. | Kills the 24 KB limit. Real file handling. Honest health checks. The foundation for everything else. |
| **2. Thin the host** | Reduce the providers to VM lifecycle only. Delete host-side logic. | Two small, stable platform files. macOS finally verifiable. |
| **3. Outbound channel and accounts** | Agent dials your service and holds the connection. Pairing flow. Web UI. | No desktop UI to maintain. The transport Part 4 needs. |
| **4. Public tunnels** | Edge server or a bought tunnel, riding the Phase 3 channel. Off by default. | Sharing, demos, mobile testing. |
| **5. Cloud** | Run the same agent image on a server. Swap sslip.io and port 39080 for a real domain and TLS. | Deployment, at close to zero marginal engineering. |

One design rule that makes Phase 5 nearly free, and that should be honoured from Phase 1:
**the domain and the entry port must be configuration, not constants.** Locally the agent is
told `127-0-0-1.sslip.io` and `39080`. In the cloud it is told a real domain and `443`, and
Traefik obtains certificates automatically. Same image, same code path, different
configuration. If either value is ever hardcoded outside a config object, Phase 5 turns into
a rewrite.

---

# Appendix: today's map

**Inside the VM**

| Path | Contents |
|---|---|
| `/opt/omelet/projects/<id>/` | project files, copied from the host |
| `/opt/omelet/projects/<id>/.omelet/overlay.yml` | generated routing labels |
| `/opt/omelet/bin/` | bootstrap script and Traefik config, as pushed |
| `/opt/omelet/traefik/traefik.yml` | the config Traefik actually reads |
| `/opt/omelet/.bootstrapped` | provisioning version marker |

**On Windows, under `%LOCALAPPDATA%\Omelet`**

| Path | Contents |
|---|---|
| `vm\` | the virtual disk |
| `cache\` | downloaded Ubuntu image, about 400 MB |
| `state.db` | the project list |
| `install-state.json` | which setup steps completed |

**Ports**

| Port | Role |
|---|---|
| 39080 | the only port between VM and host; Traefik's entrance |
| 39099 | local JSON-RPC API, host-side today, moves into the VM in Phase 1 |

**Reaching the VM's files from Windows**

```
\\wsl.localhost\omelet-vm\opt\omelet\projects
```
