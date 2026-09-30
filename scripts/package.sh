#!/usr/bin/env bash
# Builds the webapp once for every log analytics plugin and packs the builds
# into one archive for the plugin packages:
#
#   release/plugin-log-analytics-webapp-<version>.tar.gz
#     <plugin id>/main.js, style.css, icon.svg, chunks/, assets/, manifest.webapp.json
#
# The plugin id is part of the bundle (its asset path, the chunk names), so
# each plugin gets a build of its own from the same source. A .sha256 file sits
# next to the archive. Dependencies must be installed first (bun install).
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION=$(bun -e "console.log(require('./package.json').version)")
IDS=$(bun -e "import { PLUGIN_IDS } from './build.constants'; console.log(PLUGIN_IDS.join(' '))")
NAME="plugin-log-analytics-webapp-${VERSION}"

rm -rf build release
mkdir -p build release
for id in ${IDS}; do
  echo "building ${id}"
  PLUGIN_ID="${id}" OUT_DIR="build/${id}" bun run build >/dev/null
  test -f "build/${id}/main.js" && test -f "build/${id}/chunks/search.js" && test -f "build/${id}/chunks/dashboard.js"
  # The fragment names the files where a plugin package holds them
  bun -e "
    const file = 'build/${id}/manifest.webapp.json'
    const m = JSON.parse(await Bun.file(file).text())
    const at = path => 'webapp/dist/' + path.split('/build/${id}/')[1]
    m.bundle_path = at(m.bundle_path)
    m.style_path = at(m.style_path)
    for (const name of Object.keys(m.chunks ?? {})) m.chunks[name] = at(m.chunks[name])
    await Bun.write(file, JSON.stringify(m, null, 2) + '\\n')
  "
done

# shellcheck disable=SC2086
COPYFILE_DISABLE=1 tar -C build -czf "release/${NAME}.tar.gz" ${IDS}
(cd release && shasum -a 256 "${NAME}.tar.gz" > "${NAME}.tar.gz.sha256")
echo "release/${NAME}.tar.gz"
