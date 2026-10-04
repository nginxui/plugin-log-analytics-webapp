"""Collect the names of the cities of a GeoLite2 City database in the languages
of the host, for the place names of the dashboards.

    python3 fetch-city-names.py GeoLite2-City.mmdb city-names.json [--geonames alternateNamesV2.zip]

Every city of the database is listed with the names the database has, then
Wikidata is asked for its labels: a Wikidata item names its GeoNames id in
property P1566, and the database identifies its cities by the same id.
Wikidata is CC0. Some large cities link another GeoNames feature on Wikidata,
the district rather than the town, so --geonames also reads the alternate names
of the GeoNames dump (https://download.geonames.org/export/dump/), CC BY 4.0,
which use the ids of the database. The result is a cache that
build-place-names.ts turns into the files of public/assets/places; it is not
committed, and neither source is read anywhere else. A second run asks
Wikidata only for the cities the cache lacks, so an interrupted run resumes.
"""
import importlib.util
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "nginx-ui-log-analytics-place-names/1.0 (https://github.com/nginxui/plugin-log-analytics-webapp)"
# Wikidata label languages the place files are built from
LABELS = ["ar", "de", "en", "es", "fr", "it", "ja", "ko", "pt", "pt-br", "ru", "tr", "uk", "vi",
          "zh", "zh-cn", "zh-hans", "zh-hant", "zh-hk", "zh-tw"]
BATCH = 250
# GeoNames languages the place files are built from
GEONAMES_LANGUAGES = {"ar", "de", "es", "fr", "it", "ja", "ko", "pt", "pt-BR", "ru", "tr", "uk", "vi",
                      "zh", "zh-CN", "zh-Hans", "zh-Hant", "zh-HK", "zh-TW"}


def load_reader():
    path = os.path.join(os.path.dirname(__file__), "check-admin1.py")
    spec = importlib.util.spec_from_file_location("check_admin1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Reader


def database_cities(path):
    """The cities of the database by GeoNames id, with their country and the
    names the database gives them."""
    reader = load_reader()(path)
    cities = {}
    for offset in reader.records():
        record, _ = reader.decode(offset, reader.data_start)
        city = record.get("city") or {}
        gid = city.get("geoname_id")
        if not gid or str(gid) in cities:
            continue
        cities[str(gid)] = {
            "country": (record.get("country") or {}).get("iso_code", ""),
            "geolite": city.get("names") or {},
        }
    return cities


def query(ids):
    values = " ".join(f'"{i}"' for i in ids)
    langs = ",".join(f'"{lang}"' for lang in LABELS)
    sparql = (f"SELECT ?gid ?lang ?label WHERE {{ VALUES ?gid {{ {values} }} ?item wdt:P1566 ?gid . "
              f"?item rdfs:label ?label . BIND(LANG(?label) AS ?lang) FILTER(?lang IN ({langs})) }}")
    body = urllib.parse.urlencode({"query": sparql, "format": "json"}).encode()
    request = urllib.request.Request(ENDPOINT, data=body, headers={
        "User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)["results"]["bindings"]
        except (urllib.error.URLError, TimeoutError) as error:
            # The query service asks clients to back off on 429 and 5xx
            wait = 2 ** attempt * 5
            retry = getattr(error, "headers", None) and error.headers.get("Retry-After")
            if retry and retry.isdigit():
                wait = int(retry)
            print(f"  {error}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit("the query service keeps failing, run again later to resume")


def geonames_names(path, ids):
    """The alternate names of the cities, one per language: a preferred name
    first, then a full one, then a short one. Colloquial and historic names
    are left out. Returns the names and, per city, the languages whose name
    is a preferred one."""
    best = {}
    with zipfile.ZipFile(path) as archive, archive.open("alternateNamesV2.txt") as raw:
        for line in io.TextIOWrapper(raw, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8 or parts[1] not in ids or parts[2] not in GEONAMES_LANGUAGES:
                continue
            preferred, short, colloquial, historic = parts[4:8]
            if colloquial == "1" or historic == "1":
                continue
            rank = 0 if preferred == "1" else 2 if short == "1" else 1
            names = best.setdefault(parts[1], {})
            if parts[2] not in names or rank < names[parts[2]][0]:
                names[parts[2]] = (rank, parts[3])
    return ({gid: {lang: name for lang, (_, name) in names.items()} for gid, names in best.items()},
            {gid: sorted(lang for lang, (rank, _) in names.items() if rank == 0) for gid, names in best.items()})


def main(mmdb, out, geonames=None):
    cities = database_cities(mmdb)
    cache = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
    for gid, city in cities.items():
        entry = cache.setdefault(gid, {})
        entry["country"], entry["geolite"] = city["country"], city["geolite"]
    # Cities of the cache the database no longer has
    for gid in set(cache) - set(cities):
        del cache[gid]
    pending = [gid for gid in cities if "wikidata" not in cache[gid]]
    print(f"{len(cities)} cities, {len(pending)} to ask Wikidata for")
    for start in range(0, len(pending), BATCH):
        ids = pending[start:start + BATCH]
        labels = {gid: {} for gid in ids}
        for row in query(ids):
            labels[row["gid"]["value"]].setdefault(row["lang"]["value"], row["label"]["value"])
        for gid, names in labels.items():
            cache[gid]["wikidata"] = names
        with open(out + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(out + ".tmp", out)
        print(f"  {min(start + BATCH, len(pending))}/{len(pending)}")
        time.sleep(1)
    found = sum(1 for entry in cache.values() if entry.get("wikidata"))
    print(f"{found} of {len(cache)} cities have Wikidata labels")
    if geonames:
        names, preferred = geonames_names(geonames, set(cache))
        for gid, entry in cache.items():
            entry["geonames"] = names.get(gid, {})
            entry["geonames_preferred"] = preferred.get(gid, [])
        with open(out + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(out + ".tmp", out)
        print(f"{len(names)} of {len(cache)} cities have GeoNames alternate names")


if __name__ == "__main__":
    args = sys.argv[1:]
    dump = None
    if "--geonames" in args:
        at = args.index("--geonames")
        dump = args[at + 1]
        del args[at:at + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    main(args[0], args[1], dump)
