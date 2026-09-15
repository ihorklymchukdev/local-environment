# Recipe: WooCommerce (small shop on WordPress)

## When this recipe
A shop with up to a few hundred products, run by the owner from an editing screen, with cards
paid through Stripe or PayPal. For a large catalog, B2B pricing or several stores see
`magento.md`; for a custom shopping experience see `medusa.md`.

## Services
Exactly `wordpress.md`. Follow that recipe first.

## First run (after the WordPress install)
```bash
docker compose run --rm wpcli wp plugin install woocommerce --activate
docker compose run --rm wpcli wp plugin install woocommerce-gateway-stripe --activate
docker compose run --rm wpcli wp theme install storefront --activate
docker compose run --rm wpcli wp wc --user=owner tool run install_pages
```
Products, shipping, taxes and payment keys are entered by the owner in
`<URL>/wp-admin/admin.php?page=wc-admin`; walk them through it in plain words rather than
inserting products yourself unless they hand you a list.

## Gotchas
- Stripe test keys go in through the WooCommerce settings screen, never in files. Card data
  never touches the project.
- The WooCommerce setup wizard asks for the store address and currency; tell the owner it is
  safe to skip anything they do not know and come back later.
- Emails (order confirmations) need a real mail service before going online; in the VM they
  are simply not delivered. Say so when the owner asks why no email arrived.
