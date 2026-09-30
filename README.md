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

The dashboard draws three maps: the world by country, the regions of one
country after a click on it, and the busiest cities. `public/assets/world.json`
holds the country outlines. The region outlines are in `public/assets/admin1/`,
one file per country, loaded when the country is opened. They add about
1.3 MiB to the compressed archive.

### Sources

- Region outlines: the admin 1 states and provinces of
  [Natural Earth](https://www.naturalearthdata.com/) at 1:10m, public domain.
- Region outlines of the countries listed in `scripts/admin1-geoboundaries.json`,
  whose current regions Natural Earth lacks (Kenya's counties, for example):
  [geoBoundaries](https://www.geoboundaries.org/) (Runfola et al. 2020, PLoS
  ONE 15(4): e0231866), gbOpen release, first level. Only public domain, CC0
  and CC BY data is used; `scripts/admin1-geoboundaries-sources.json` lists
  the license, source and year of each country.
- Names of the regions that do not come from Natural Earth:
  [Wikidata](https://www.wikidata.org/), CC0, with a few corrections, in
  `scripts/admin1-region-names.json`.

### How the region files are built

`scripts/split-admin1.py` turns the Natural Earth file and the geoBoundaries
files into the region files:

- Every region is keyed by its ISO 3166-2 code, the code the GeoLite2 database
  gives as a visitor's first or second subdivision. Natural Earth still uses
  older or placeholder codes for some regions; `scripts/admin1-code-aliases.json`
  maps them to the current codes.
- Where Natural Earth has second level units, they are merged into the first
  level the database reports: the metropolitan departments of France, the
  provinces of Italy and Spain, the council areas of the United Kingdom and the
  provinces of Belgium.
- Hong Kong, Macau and Taiwan are regions of the China map (`CN-HK`, `CN-MO`,
  `CN-TW`), since the plugins count their visitors under CN.
- The main territory of a country opens the map. Regions wholly outside of it,
  such as Alaska, Hawaii or French Guiana, are moved into framed insets next to
  it.
- Outlines are simplified and rounded to three decimals.

Each file is a GeoJSON FeatureCollection with two extra members that
`RegionMapChart` reads: `view`, the top left and bottom right corners of the
first view, and `aspect`, the width of a degree of longitude at the latitude
of the country. A feature carries `code`, `name` and `name_<language>`; the
frames of the insets are features with `frame` set and are not counted.

### Checking the codes

A region the outline lacks is counted but not drawn. Two checks find these:

- `scripts/check-admin1.py` reads a GeoLite2 City database and lists, per
  country, the codes of the level the outline draws that have no outline. Gaps
  that the Natural Earth geometry cannot close, such as regions created after
  its release, are listed in `scripts/admin1-known-gaps.json`; the check fails
  only for gaps not listed there.
- At run time the plugins return the level of every code, and the region map
  logs a warning in the browser console when it cannot draw a code of the level
  its outline uses.

### When to update

The data rarely changes. Update it when:

- ISO 3166-2 revises the subdivisions of a country and the GeoLite2 database
  follows, which the check reports as new gaps;
- Natural Earth publishes a new release;
- the rules of the split script change.

### Updating

1. Download `ne_10m_admin_1_states_provinces.geojson` from Natural Earth and
   the geoBoundaries files, which also refreshes their sources list:

   ```
   python3 scripts/fetch-geoboundaries.py geoboundaries
   ```

2. Build the region files:

   ```
   python3 scripts/split-admin1.py ne_10m_admin_1_states_provinces.geojson public/assets/admin1 --geoboundaries geoboundaries
   ```

3. Check them against a current GeoLite2 City database, for example the one a
   plugin downloaded into its data directory under `geolite/`:

   ```
   python3 scripts/check-admin1.py GeoLite2-City.mmdb public/assets/admin1
   ```

4. For new gaps, let the check suggest the outline codes that match by name,
   review them and add the right pairs to `scripts/admin1-code-aliases.json`,
   then build again:

   ```
   python3 scripts/check-admin1.py --suggest GeoLite2-City.mmdb public/assets/admin1
   ```

   A merged region, or a region from geoBoundaries, needs its names in
   `scripts/admin1-region-names.json`. A country whose regions only
   geoBoundaries has goes into `scripts/admin1-geoboundaries.json`, if its
   license is one of those above.
5. When the remaining gaps cannot be closed, record them:

   ```
   python3 scripts/check-admin1.py --write-baseline GeoLite2-City.mmdb public/assets/admin1
   ```

6. Open a few changed countries on the dashboard, then release the webapp and
   update the `webapp.lock` of both plugins.
