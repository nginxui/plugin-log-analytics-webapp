# Log analytics webapp

The web pages of the NGINX UI log analytics plugins, `com.nginxui.log-analytics`
(Go) and `com.nginxui.log-analytics-tantivy` (Rust): the columns of the log
list, the structured search of access and error logs and the traffic dashboard
with its maps. Both plugins answer the same HTTP API, so one source serves both.

## Builds

The plugin id is part of a bundle (its asset path and chunk names), so every
plugin gets a build of its own:

```
bun install
bun run package      # release/plugin-log-analytics-webapp-<version>.tar.gz
```

The archive holds one directory per plugin id with `main.js`, `style.css`,
`icon.svg`, `chunks/`, `assets/` and `manifest.webapp.json`, and a `.sha256`
file sits next to it. A plugin names the release it packages in its
`webapp.lock`, and its `build.sh` unpacks its own directory into
`webapp/dist`. For a single build, `PLUGIN_ID=<id> OUT_DIR=<dir> bun run build`.

## Differences between the plugins

A feature only one plugin has is announced by the plugin in the `features` of
the preflight answer, and the pages offer it only then. The search syntax help
(`features.query_syntax`) is the first.

## Development

```
bun run typecheck
bun run lint
bun test tests       # the bundle tests read dist/, build it first
bun run i18n         # the translation catalogs, from the NGINX UI catalogs
```

`@nginxui/plugin-sdk` resolves to a checkout of `plugin-sdk-web` next to this
repository. `bun run i18n` reads the catalogs of a checkout of `nginx-ui` next
to it, or of `NGINX_UI_LANGUAGE_DIR`.

## Map data

`public/assets/world.json` holds the country outlines. The region outlines in
`public/assets/admin1/` come from the admin 1 states and provinces of
[Natural Earth](https://www.naturalearthdata.com/) (public domain), one file per
country with the ISO 3166-2 code and the names in the languages of NGINX UI,
simplified by `scripts/split-admin1.py`:

```
python3 scripts/split-admin1.py ne_10m_admin_1_states_provinces.geojson public/assets/admin1
```

China, Hong Kong, Macau and Taiwan are left out: the China map covers them with
its own province and city outlines.
