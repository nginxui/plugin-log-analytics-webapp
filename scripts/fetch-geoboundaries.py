"""Download the first level boundaries of geoBoundaries for the countries the
Natural Earth outlines cannot serve, listed in admin1-geoboundaries.json.

    python3 fetch-geoboundaries.py geoboundaries/

Each country is saved as <ISO2>.geojson with the simplified geometry of the
current gbOpen release, and admin1-geoboundaries-sources.json next to this
script records the license, source and year of each, for the attribution.
split-admin1.py takes the directory with --geoboundaries. Only boundaries under
a license that allows redistribution with attribution are kept.
"""
import json
import os
import sys
import urllib.request

API = "https://www.geoboundaries.org/api/current/gbOpen/{iso3}/ADM1/"
LIST = os.path.join(os.path.dirname(__file__), "admin1-geoboundaries.json")
SOURCES = os.path.join(os.path.dirname(__file__), "admin1-geoboundaries-sources.json")
ALLOWED = ("public domain", "cc0", "cc by 4.0", "cc by 3.0", "creative commons attribution 4.0",
           "creative commons attribution 3.0", "open data commons attribution", "cc by 3.0 igo",
           "creative commons attribution 3.0 intergovernmental organisations (cc by 3.0 igo)")


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "nginx-ui-plugin-log-analytics-webapp"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main(out, codes=None):
    countries = json.load(open(LIST, encoding="utf-8"))
    if codes:
        countries = {cc: iso3 for cc, iso3 in countries.items() if cc in codes}
    os.makedirs(out, exist_ok=True)
    sources = json.load(open(SOURCES, encoding="utf-8")) if os.path.exists(SOURCES) else {}
    for cc, iso3 in sorted(countries.items()):
        try:
            meta = json.loads(fetch(API.format(iso3=iso3)))
        except Exception as error:  # noqa: BLE001
            print(f"{cc}: no ADM1 boundaries ({error})")
            continue
        license_name = (meta.get("boundaryLicense") or "").strip()
        if not license_name.lower().startswith(ALLOWED):
            print(f"{cc}: skipped, license {license_name}")
            continue
        with open(os.path.join(out, f"{cc}.geojson"), "wb") as fh:
            fh.write(fetch(meta["simplifiedGeometryGeoJSON"]))
        sources[cc] = {
            "license": license_name,
            "source": meta.get("boundarySource"),
            "year": meta.get("boundaryYearRepresented"),
            "units": meta.get("admUnitCount"),
        }
        print(f"{cc}: {meta.get('admUnitCount')} units, {license_name}")
    with open(SOURCES, "w", encoding="utf-8") as fh:
        json.dump(sources, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main(sys.argv[1], set(sys.argv[2:]))
