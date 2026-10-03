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
file sits next to it. A release `v<version>` publishes both files: a plugin
names the version it packages in its `webapp.lock`, and its `build.sh`
downloads the archive, checks it against the `.sha256` file and unpacks its own
directory into `webapp/dist`. After a release, change the version in the
`webapp.lock` of both plugins. A local build of a plugin takes the archive of a
checkout next to it. For a single build, `PLUGIN_ID=<id> OUT_DIR=<dir> bun run build`.

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

`@nginxui/plugin-sdk` comes from npm. Until it is published there, `bun.lock`
names only its version range and installs fail; once it is out, run
`bun install` and commit `bun.lock`. To work against a local checkout of
`plugin-sdk-web`, link it once; `package.json` and `bun.lock` stay as they are:

```
(cd ../plugin-sdk-web && bun install && bun run build && bun link)
bun link @nginxui/plugin-sdk
```

`bun run i18n` reads the catalogs of a checkout of `nginx-ui` next
to it, or of `NGINX_UI_LANGUAGE_DIR`.

## Map data

The dashboard draws three maps: the world by country, the regions of one
country after a click on it, and the busiest cities. `public/assets/world.json`
holds the country outlines. The region outlines are in `public/assets/admin1/`,
one file per country, loaded when the country is opened. They add about
1.3 MiB to the compressed archive, the place names below about 2.8 MiB.

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
- The main territory and each inset are drawn in an Albers equal-area conic
  projection fitted to them, so northern and southern regions keep their
  shape. Close to the equator the projection is equirectangular. The projected
  coordinates stay near the longitude and latitude of the place.
- Outlines are simplified and rounded to three decimals.

Each file is a GeoJSON FeatureCollection with an extra member that
`RegionMapChart` reads: `view`, the top left and bottom right corners of the
first view in projected coordinates. A feature carries `code`, `name` and `name_<language>`; the
frames of the insets are features with `frame` set and are not counted.

### Place names

The backends answer the English names of a visitor's region and city, with the
ISO 3166-2 code of the region and the GeoNames id of the city. The page names
them in the language of the host from `public/assets/places/<locale>.json`,
fetched once for the current language. Each file holds `cities`, names by
GeoNames id, and `regions`, names by code; a place it lacks keeps its English
name.

- City names come from [Wikidata](https://www.wikidata.org/), CC0, whose
  items name their GeoNames id in property P1566, the id GeoLite2 gives a city.
  Some large cities link another GeoNames feature there, the district rather
  than the town, so the alternate names of
  [GeoNames](https://www.geonames.org/), CC BY 4.0, fill in after Wikidata. In
  the Latin script GeoNames counts only with a name it marks preferred, its
  other names are often old or local spellings. Traditional Chinese takes the
  names used in Taiwan, then other traditional names, and converts the
  simplified name with [OpenCC](https://github.com/BYVoid/OpenCC) (s2twp) for
  the rest. The names the GeoLite2 database itself carries are not shipped,
  its license does not allow it.
- `scripts/fetch-city-names.py` lists the cities of a GeoLite2 City database,
  asks Wikidata for their labels and reads the GeoNames dump. This happens
  here, when the files are built; the plugins never fetch these sources.
- Region names are the `name_<language>` members of the region outlines.

`scripts/build-place-names.ts` writes the files from the cache the fetch script
leaves and the region outlines.

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
- the rules of the split script change;
- the GeoLite2 database has gained many cities the place names lack, or
  Wikidata many names, which only the place names need.

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

6. Download `alternateNamesV2.zip` from the
   [GeoNames dump](https://download.geonames.org/export/dump/), about 200 MB,
   and collect the city names. Asking Wikidata takes a quarter of an hour and
   resumes where an interrupted run stopped. Then build the place names from
   them and the region files:

   ```
   python3 scripts/fetch-city-names.py GeoLite2-City.mmdb city-names.json --geonames alternateNamesV2.zip
   bun scripts/build-place-names.ts city-names.json public/assets/admin1 public/assets/places
   ```

7. Open a few changed countries on the dashboard, then release the webapp and
   update the `webapp.lock` of both plugins.
