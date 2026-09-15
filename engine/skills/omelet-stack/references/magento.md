# Recipe: Magento Open Source (large catalog, B2B, several stores)

## When this recipe
Thousands of products, customer-group pricing, several stores, currencies or languages under
one roof, or an owner who already runs Magento elsewhere. It is the heaviest thing on the
ladder: 4 GB of memory, a ten-minute first install, and a free Adobe account for the
download keys. For anything smaller, `woocommerce.md`.

## Services
Magento has no official compose file. Start from the community-standard
`markshust/docker-magento` set (`nginx`, `phpfpm`, `db` MariaDB, `redis`, `opensearch`,
`rabbitmq`) and adapt it to the Omelet contract:

- remove every `ports:` block — Omelet routes to `nginx` by name;
- keep the named volumes for `db`, `opensearch` and `rabbitmq`;
- keep `src/` bind-mounted into `phpfpm` and `nginx` so your theme and module edits show;
- set the base URL to the one `omelet up` prints.

## .omelet/project.yml
```yaml
web:
  - service: nginx
    port: 8000
```
(Use the port the adapted nginx service listens on inside the container.)

## First run
1. Ask the owner, in plain words, to create a free account at the Adobe Commerce Marketplace
   and give you the two "access keys" from *My Profile → Access Keys*. Nothing installs
   without them.
2. `composer create-project --repository-url=https://repo.magento.com/ magento/project-community-edition src`
   through the set's `bin/composer`, with the keys in `auth.json` (git-ignored).
3. `bin/setup <URL from omelet up>` from the set; then `bin/magento admin:user:create …` and
   write the admin address and login down for the owner.

## Existing project
An imported Magento tree is the `src/` of the set above; keep its `composer.json` and
`app/etc/env.php`, restore the database dump, then `bin/magento setup:upgrade`.

## Gotchas
- The `wsl.exe`-side memory cap decides whether this runs at all; if the VM has under 4 GB,
  say so to the owner before starting rather than after a failed install.
- Magento caches aggressively; after changing a theme run `bin/magento cache:flush` or the
  owner sees the old page.
- `auth.json` holds the owner's keys; it is git-ignored and never printed in chat.
- Upgrades are a project of their own; pin the version in `composer.json` and note it in
  `docs/stack.md`.
