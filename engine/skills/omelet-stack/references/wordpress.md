# Recipe: WordPress (site edited by a non-technical person)

## When this recipe
A site, blog or brochure where someone who is not a developer changes text, pictures, pages
or posts themselves. Add `woocommerce.md` on top for a shop.

## Services
- `wordpress`: the official image, Apache + PHP.
- `db`: MySQL 8.
- `wpcli`: the official CLI image, for scripted install and plugin/theme commands.

## docker-compose.yml
```yaml
services:
  wordpress:
    image: wordpress:6-php8.3-apache
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: wp
      WORDPRESS_DB_PASSWORD: wp
      WORDPRESS_DB_NAME: wp
    volumes:
      - wp_html:/var/www/html
      - ./wp-content:/var/www/html/wp-content
    depends_on:
      - db
  db:
    image: mysql:8
    environment:
      MYSQL_DATABASE: wp
      MYSQL_USER: wp
      MYSQL_PASSWORD: wp
      MYSQL_ROOT_PASSWORD: root
    volumes:
      - db_data:/var/lib/mysql
  wpcli:
    image: wordpress:cli-php8.3
    user: "33:33"
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: wp
      WORDPRESS_DB_PASSWORD: wp
      WORDPRESS_DB_NAME: wp
    volumes:
      - wp_html:/var/www/html
      - ./wp-content:/var/www/html/wp-content
    depends_on:
      - db
    profiles: ["tools"]
volumes:
  wp_html:
  db_data:
```
`./wp-content` is the source you edit (a child theme, a plugin). Core lives in `wp_html`.

## .omelet/project.yml
```yaml
web:
  - service: wordpress
    port: 80
```

## First run
`omelet up` first — the URL it prints is needed below. Then, once the site answers:
```bash
docker compose run --rm wpcli wp core install --url=<URL from omelet up> --title="<site name>" \
  --admin_user=owner --admin_password=<generate one> --admin_email=owner@example.com --skip-email
docker compose run --rm wpcli wp theme install twentytwentyfive --activate
docker compose run --rm wpcli wp plugin install wordpress-seo --activate
```
Write the admin address (`<URL>/wp-admin`), user and password down for the owner and tell
them to change the password. A child theme in `wp-content/themes/<name>/` is where your CSS
and templates go; never edit a downloaded theme in place.
`.gitignore`: `wp-content/uploads/`, `wp-content/upgrade/`.

## Existing project
A repository with `wp-content/` only: mount it as above. A repository with the whole WordPress
tree: mount `.` to `/var/www/html` and drop the `wp_html` volume.

## Gotchas
- The install must be run with the real URL (`--url`), because WordPress stores its address in
  the database. If the URL ever changes:
  `wp option update siteurl <new> && wp option update home <new>` through `wpcli`.
- `user: "33:33"` on the CLI keeps files it creates owned by `www-data`, so the web container
  can still write uploads. Files the agent creates under `wp-content` should be world-readable.
- First page load after install can take ten seconds while caches warm; poll the URL rather
  than declaring failure.
- The `tools` profile keeps `wpcli` out of `omelet up`; `docker compose run` still finds it.
