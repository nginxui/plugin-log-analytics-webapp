"""Split the Natural Earth admin-1 boundaries into one small GeoJSON file per
country for the region maps of the log analytics plugins.

    python3 split_admin1.py ne_10m_admin_1_states_provinces.geojson out/

Each feature keeps its ISO 3166-2 code and the names in the languages of the
host. Geometry is simplified with Douglas-Peucker and rounded to 3 decimals.
Hong Kong, Macau and Taiwan are regions of the China map, CN-HK, CN-MO and
CN-TW, as the plugins count them under CN. Polygons across the antimeridian are moved to the side of the country, and
each file names the box of the main territory in "view", the first view of the
map.
"""
import json
import math
import os
import sys

LANGS = ["ar", "de", "en", "es", "fr", "ja", "ko", "pt", "ru", "tr", "uk", "vi", "zh", "zht"]

# Regions of the China map drawn from the outlines of their own
CHINA_REGIONS = {
    "HK": {"en": "Hong Kong", "ar": "هونغ كونغ", "de": "Hongkong", "es": "Hong Kong", "fr": "Hong Kong",
           "ja": "香港", "ko": "홍콩", "pt": "Hong Kong", "ru": "Гонконг", "tr": "Hong Kong", "uk": "Гонконг",
           "vi": "Hồng Kông", "zh": "香港", "zht": "香港"},
    "MO": {"en": "Macau", "ar": "ماكاو", "de": "Macau", "es": "Macao", "fr": "Macao", "ja": "マカオ",
           "ko": "마카오", "pt": "Macau", "ru": "Макао", "tr": "Makao", "uk": "Макао", "vi": "Ma Cao",
           "zh": "澳门", "zht": "澳門"},
    "TW": {"en": "Taiwan", "ar": "تايوان", "de": "Taiwan", "es": "Taiwán", "fr": "Taïwan", "ja": "台湾",
           "ko": "타이완", "pt": "Taiwan", "ru": "Тайвань", "tr": "Tayvan", "uk": "Тайвань", "vi": "Đài Loan",
           "zh": "台湾", "zht": "臺灣"},
}


def perpendicular(p, a, b):
    if a == b:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    (x, y), (x1, y1), (x2, y2) = p, a, b
    return abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / math.hypot(y2 - y1, x2 - x1)


def simplify(points, tolerance):
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        best, index = 0.0, 0
        for i in range(start + 1, end):
            d = perpendicular(points[i], points[start], points[end])
            if d > best:
                best, index = d, i
        if best > tolerance:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [p for p, k in zip(points, keep) if k]


def ring(points, tolerance):
    out = simplify(points, tolerance)
    out = [[round(x, 3), round(y, 3)] for x, y in out]
    dedup = [out[0]]
    for p in out[1:]:
        if p != dedup[-1]:
            dedup.append(p)
    if dedup[0] != dedup[-1]:
        dedup.append(dedup[0])
    return dedup if len(dedup) >= 4 else None


def polygon(rings, tolerance):
    out = [r for r in (ring(r, tolerance) for r in rings) if r]
    return out if out else None


def geometry(geom, tolerance):
    if geom is None:
        return None
    if geom["type"] == "Polygon":
        p = polygon(geom["coordinates"], tolerance)
        return {"type": "Polygon", "coordinates": p} if p else None
    if geom["type"] == "MultiPolygon":
        ps = [p for p in (polygon(p, tolerance) for p in geom["coordinates"]) if p]
        return {"type": "MultiPolygon", "coordinates": ps} if ps else None
    return None


def bbox_span(features):
    xs, ys = [], []
    for f in features:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for p in polys:
            for x, y in p[0]:
                xs.append(x)
                ys.append(y)
    return max(max(xs) - min(xs), max(ys) - min(ys)) if xs else 1.0


def polygons_of(geom):
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]


def unwrap(features):
    """Moves the polygons across the antimeridian to the side most of the
    country lies on, so the Aleutians sit next to Alaska and Chukotka next to
    the rest of Russia."""
    polys = [p for f in features for p in polygons_of(f["geometry"])]
    lons = [x for p in polys for x, _ in p[0]]
    if not lons or max(lons) - min(lons) <= 180:
        return
    east = sum(1 for x in lons if x > 0)
    shift = -360 if east < len(lons) - east else 360
    for p in polys:
        mean = sum(x for x, _ in p[0]) / len(p[0])
        if (shift < 0 and mean > 0) or (shift > 0 and mean < 0):
            for r in p:
                for pt in r:
                    pt[0] = round(pt[0] + shift, 3)


def area(points):
    """Rough area of a ring in square degrees, scaled by its latitude."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        s += x1 * y2 - x2 * y1
    lat = sum(y for _, y in points) / len(points)
    return abs(s) / 2 * math.cos(math.radians(lat))


def bounds(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def gap(a, b):
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def main_view(features, reach=5.0):
    """The box of the main territory. Polygons closer than reach degrees form
    groups and the group with the largest area wins, so regions far overseas
    such as French Guiana or Hawaii stay out of the first view."""
    parts = [(bounds(p[0]), area(p[0])) for f in features for p in polygons_of(f["geometry"])]
    group = list(range(len(parts)))

    def root(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    order = sorted(range(len(parts)), key=lambda i: parts[i][0][0])
    for n, i in enumerate(order):
        for j in order[n + 1:]:
            if parts[j][0][0] - parts[i][0][2] > reach:
                break
            if gap(parts[i][0], parts[j][0]) <= reach:
                group[root(i)] = root(j)
    totals = {}
    for i, (_, a) in enumerate(parts):
        totals[root(i)] = totals.get(root(i), 0.0) + a
    best = max(totals, key=totals.get)
    boxes = [b for i, (b, _) in enumerate(parts) if root(i) == best]
    west, south = min(b[0] for b in boxes), min(b[1] for b in boxes)
    east, north = max(b[2] for b in boxes), max(b[3] for b in boxes)
    # Top left and bottom right, as boundingCoords of ECharts takes them
    return [[round(west, 2), round(north, 2)], [round(east, 2), round(south, 2)]]


def main(src, dst):
    data = json.load(open(src, encoding="utf-8"))
    by_country = {}
    for f in data["features"]:
        p = f["properties"]
        cc = (p.get("iso_a2") or "").strip()
        code = (p.get("iso_3166_2") or "").strip()
        if len(cc) != 2 or not cc.isalpha() or not code or f["geometry"] is None:
            continue
        by_country.setdefault(cc, []).append(f)

    for cc, names in CHINA_REGIONS.items():
        parts = [q for f in by_country.pop(cc, []) for q in polygons_of(f["geometry"])]
        if parts:
            props = {"iso_3166_2": f"CN-{cc}", **{f"name_{lang}": name for lang, name in names.items()}}
            geom = {"type": "MultiPolygon", "coordinates": parts}
            by_country.setdefault("CN", []).append({"properties": props, "geometry": geom})

    os.makedirs(dst, exist_ok=True)
    total = 0
    index = {}
    for cc, features in sorted(by_country.items()):
        # Larger countries tolerate coarser outlines: about 1/400 of their span
        tolerance = max(0.002, min(0.05, bbox_span(features) / 400))
        out = []
        for f in features:
            # Small regions such as Macau keep enough points to stay visible
            g = geometry(f["geometry"], min(tolerance, max(0.0005, bbox_span([f]) / 20)))
            if not g:
                continue
            p = f["properties"]
            props = {"code": p["iso_3166_2"].strip(), "name": (p.get("name_en") or p.get("name") or "").strip()}
            for lang in LANGS:
                value = (p.get(f"name_{lang}") or "").strip()
                if value and value != props["name"]:
                    props[f"name_{lang}"] = value
            out.append({"type": "Feature", "properties": props, "geometry": g})
        if not out:
            continue
        unwrap(out)
        collection = {"type": "FeatureCollection", "view": main_view(out), "features": out}
        text = json.dumps(collection, ensure_ascii=False, separators=(",", ":"))
        with open(os.path.join(dst, f"{cc}.json"), "w", encoding="utf-8") as fh:
            fh.write(text)
        index[cc] = len(out)
        total += len(text.encode("utf-8"))
    with open(os.path.join(dst, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, separators=(",", ":"), sort_keys=True)
    print(f"{len(index)} countries, {total / 1024 / 1024:.1f} MiB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
