"""Split the Natural Earth admin-1 boundaries into one small GeoJSON file per
country for the region maps of the log analytics plugins.

    python3 split-admin1.py ne_10m_admin_1_states_provinces.geojson out/ [--geoboundaries DIR]

The countries listed in admin1-geoboundaries.json take their outlines from the
geoBoundaries files in DIR instead, see fetch-geoboundaries.py: Natural Earth
lacks their current regions. Each feature keeps its ISO 3166-2 code and the names in the languages of the
host. Geometry is simplified with Douglas-Peucker and rounded to 3 decimals.
Hong Kong, Macau and Taiwan are regions of the China map, CN-HK, CN-MO and
CN-TW, as the plugins count them under CN. Polygons across the antimeridian
are moved to the side of the country. The main territory is drawn in an Albers
equal-area conic projection fitted to it, and each file names its box in
"view", the first view of the map. Regions wholly outside the main territory
are drawn in projections of their own and moved into framed insets next to
it; the frames are features with "frame" set. Coordinates stay near the
longitude and latitude of the place, so the maps are drawn without a further
projection.
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


# Countries whose admin-1 features in Natural Earth are second level units. They
# are merged into the first level, whose ISO 3166-2 codes the geo database
# gives as the first subdivision.
ES_CODES = {"LO": "RI", "MU": "MC", "NA": "NC", "PM": "IB"}
GB_CODES = {"England": "ENG", "Scotland": "SCT", "Wales": "WLS", "Northern Ireland": "NIR"}
BE_CODES = {"Flemish": "VLG", "Walloon": "WAL", "Capital Region": "BRU"}


def parent_code(cc, p):
    """The first level code a feature is merged into, or None to keep it."""
    region = (p.get("region_cod") or "").strip()
    if cc == "FR" and p.get("type_en") == "Metropolitan department":
        return region
    if cc == "IT":
        return region
    if cc == "ES" and p.get("type_en") == "Autonomous Community":
        sub = region.split(".")[-1]
        return f"ES-{ES_CODES.get(sub, sub)}"
    if cc == "GB" and p.get("geonunit") in GB_CODES:
        return f"GB-{GB_CODES[p['geonunit']]}"
    if cc == "BE" and p.get("region") in BE_CODES:
        return f"BE-{BE_CODES[p['region']]}"
    return None


# Names of the regions that do not come from Natural Earth, the merged ones and
# those from geoBoundaries, in the languages of the host. From Wikidata (CC0)
# with a few corrections.
REGION_NAMES = json.load(open(os.path.join(os.path.dirname(__file__), "admin1-region-names.json"), encoding="utf-8"))

# Current ISO 3166-2 codes of regions Natural Earth still names by an older or a
# placeholder code, reviewed from the suggestions of check-admin1.py
CODE_ALIASES = json.load(open(os.path.join(os.path.dirname(__file__), "admin1-code-aliases.json"), encoding="utf-8"))


def signed_area(ring):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2


def contains(ring, point):
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def dissolve(features):
    """Merges the polygons of features into one MultiPolygon. The borders two
    features share are dropped: their edges appear twice, once each way, and
    the edges left over are chained into the new rings."""
    key = lambda pt: (round(pt[0], 7), round(pt[1], 7))
    polys = [q for f in features for q in polygons_of(f["geometry"])]
    outer_sign = 1 if sum(signed_area(q[0]) for q in polys) > 0 else -1

    counts = {}
    for q in polys:
        for r in q:
            for a, b in zip(r, r[1:]):
                a, b = key(a), key(b)
                if a != b:
                    edge = (min(a, b), max(a, b))
                    counts[edge] = counts.get(edge, 0) + 1
    nexts = {}
    for q in polys:
        for r in q:
            for a, b in zip(r, r[1:]):
                a, b = key(a), key(b)
                if a != b and counts[(min(a, b), max(a, b))] == 1:
                    nexts.setdefault(a, []).append(b)

    rings = []
    while nexts:
        start = next(iter(nexts))
        ring, at = [start], start
        while True:
            targets = nexts.get(at)
            if not targets:
                break
            nxt = targets.pop()
            if not targets:
                del nexts[at]
            ring.append(nxt)
            at = nxt
            if at == start:
                break
        if len(ring) >= 4 and ring[0] == ring[-1]:
            rings.append([list(pt) for pt in ring])

    outers = [r for r in rings if signed_area(r) * outer_sign > 0]
    holes = [r for r in rings if signed_area(r) * outer_sign <= 0]
    result = [[r] for r in outers]
    for h in holes:
        owners = [q for q in result if contains(q[0], h[0])]
        if owners:
            min(owners, key=lambda q: abs(signed_area(q[0]))).append(h)
    return {"type": "MultiPolygon", "coordinates": result}


def merge_levels(cc, features):
    """Merges second level features into their first level regions."""
    groups, kept = {}, []
    for f in features:
        code = parent_code(cc, f["properties"])
        if code:
            groups.setdefault(code, []).append(f)
        else:
            kept.append(f)
    merged = []
    for code, members in groups.items():
        props = {"iso_3166_2": code}
        names = REGION_NAMES.get(code)
        if names:
            for lang, name in names.items():
                props[f"name_{lang}"] = name
        else:
            props["name_en"] = members[0]["properties"].get("region") or code
        merged.append({"properties": props, "geometry": dissolve(members)})
    return merged + kept


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
    """Distance between two boxes in degrees of latitude."""
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    lat = (max(a[1], b[1]) + min(a[3], b[3])) / 2
    return math.hypot(dx * math.cos(math.radians(lat)), dy)


def cluster(boxes, reach):
    """Groups boxes closer than reach degrees and returns the group of each."""
    group = list(range(len(boxes)))

    def root(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    order = sorted(range(len(boxes)), key=lambda i: boxes[i][0])
    for n, i in enumerate(order):
        for j in order[n + 1:]:
            # Longitude gaps shrink toward the poles, up to 80 degrees counts
            if boxes[j][0] - boxes[i][2] > reach / math.cos(math.radians(80)):
                break
            if gap(boxes[i], boxes[j]) <= reach:
                group[root(i)] = root(j)
    return [root(i) for i in range(len(boxes))]


def union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


# Countries with more outlying groups than this keep them out of view
MAX_INSETS = 6
MAIN_SHARE = 0.25
INSET_SHARE = 0.28
INSET_GAP = 0.05


def albers(box):
    """An Albers equal-area conic projection fitted to a box of longitude and
    latitude, with its standard parallels a sixth of the height inside the
    edges. It maps a point to x and y in degrees of a great circle, offset to
    the center of the box. Close to the equator the cone flattens into a
    cylinder, there the box is drawn equirectangular at its middle latitude."""
    west, south, east, north = box
    lon0, lat0 = (west + east) / 2, (south + north) / 2
    p1 = math.radians(south + (north - south) / 6)
    p2 = math.radians(north - (north - south) / 6)
    n = (math.sin(p1) + math.sin(p2)) / 2
    if abs(n) < 0.05:
        k = math.cos(math.radians(lat0))
        return lambda lon, lat: (lon0 + (lon - lon0) * k, lat)
    c = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
    rho0 = math.sqrt(c - 2 * n * math.sin(math.radians(lat0))) / n

    def project(lon, lat):
        rho = math.sqrt(max(0.0, c - 2 * n * math.sin(math.radians(lat)))) / n
        theta = n * math.radians(lon - lon0)
        return lon0 + math.degrees(rho * math.sin(theta)), lat0 + math.degrees(rho0 - rho * math.cos(theta))
    return project


def transform(feature, project):
    for poly in polygons_of(feature["geometry"]):
        for r in poly:
            for pt in r:
                x, y = project(pt[0], pt[1])
                pt[0], pt[1] = round(x, 3), round(y, 3)


def move(feature, box, scale, target):
    """Scales a feature around the center of box and moves it to target."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for poly in polygons_of(feature["geometry"]):
        for r in poly:
            for pt in r:
                pt[0] = round(target[0] + (pt[0] - cx) * scale, 3)
                pt[1] = round(target[1] + (pt[1] - cy) * scale, 3)


def frame(index, west, south, east, north):
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    ring = [[round(x, 3), round(y, 3)] for x, y in ring]
    return {"type": "Feature", "properties": {"code": f"~frame{index}", "frame": True},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


def layout(features, reach=3.0):
    """Finds the main territory and moves the regions that lie wholly outside
    of it, such as Alaska, Hawaii or French Guiana, into framed insets next to
    it. Polygons closer than reach degrees form groups and the group with the
    largest area is the main territory. The main territory and each inset are
    projected with an Albers projection of their own, so every part keeps its
    shape. Returns the view box and the frames."""
    parts = [(fi, p) for fi, f in enumerate(features) for p in polygons_of(f["geometry"])]
    boxes = [bounds(p[0]) for _, p in parts]
    groups = cluster(boxes, reach)
    totals = {}
    for i, (_, p) in enumerate(parts):
        totals[groups[i]] = totals.get(groups[i], 0.0) + area(p[0])
    # Groups of a quarter of the largest, like Peninsular Malaysia next to
    # Borneo, are part of the main territory too
    largest = max(totals.values())
    main = {g for g, total in totals.items() if total >= largest * MAIN_SHARE}
    main_box = union([b for i, b in enumerate(boxes) if groups[i] in main])

    in_main = {fi for i, (fi, _) in enumerate(parts) if groups[i] in main}
    outlying = [fi for fi in range(len(features)) if fi not in in_main]
    feature_boxes = {fi: union([boxes[i] for i, (f, _) in enumerate(parts) if f == fi]) for fi in outlying}
    insets = {}
    for fi, g in zip(outlying, cluster([feature_boxes[fi] for fi in outlying], reach)):
        insets.setdefault(g, []).append(fi)
    insets = sorted((union([feature_boxes[fi] for fi in members]), members) for members in insets.values())

    project = albers(main_box)
    for fi in in_main:
        transform(features[fi], project)
    # Polygons are projected in place, the parts see the new coordinates
    west, south, east, north = union([bounds(p[0]) for i, (_, p) in enumerate(parts) if groups[i] in main])
    projected = []
    for box, members in insets:
        project = albers(box)
        for fi in members:
            transform(features[fi], project)
        projected.append((union([bounds(p[0]) for fi in members for p in polygons_of(features[fi]["geometry"])]), members))
    insets = projected

    frames = []
    if 0 < len(insets) <= MAX_INSETS:
        width, height = east - west, north - south
        if width >= height:
            cell, space = INSET_SHARE * height, INSET_GAP * height
            x, top = west, south - space
            for box, members in insets:
                scale = min(cell * 0.85 / max(box[3] - box[1], 1e-6), width / len(insets) * 0.85 / max(box[2] - box[0], 1e-6), 8.0)
                cell_width = (box[2] - box[0]) * scale / 0.85
                for fi in members:
                    move(features[fi], box, scale, (x + cell_width / 2, top - cell / 2))
                frames.append(frame(len(frames), x, top - cell, x + cell_width, top))
                x += cell_width + space / 2
            south = top - cell
        else:
            # A tall country leaves room at its side, so the column is as wide as
            # a strip below a wide country would be tall
            cell, space = INSET_SHARE * height * 1.5, INSET_GAP * height
            right, y = west - space, north
            for box, members in insets:
                scale = min(cell * 0.85 / max(box[2] - box[0], 1e-6), height / len(insets) * 0.85 / max(box[3] - box[1], 1e-6), 8.0)
                cell_height = (box[3] - box[1]) * scale / 0.85
                for fi in members:
                    move(features[fi], box, scale, (right - cell / 2, y - cell_height / 2))
                frames.append(frame(len(frames), right - cell, y - cell_height, right, y))
                y -= cell_height + space / 2
            west = right - cell
        west, south = min(west, *(f["geometry"]["coordinates"][0][0][0] for f in frames)), south
        east = max(east, *(f["geometry"]["coordinates"][0][1][0] for f in frames))
    # Top left and bottom right, as boundingCoords of ECharts takes them
    return [[round(west, 2), round(north, 2)], [round(east, 2), round(south, 2)]], frames


def geoboundaries(directory):
    """Features of the countries whose outlines come from geoBoundaries."""
    countries = json.load(open(os.path.join(os.path.dirname(__file__), "admin1-geoboundaries.json"), encoding="utf-8"))
    result = {}
    for cc in countries:
        path = os.path.join(directory, f"{cc}.geojson")
        if not os.path.exists(path):
            raise SystemExit(f"{path} is missing, run fetch-geoboundaries.py first")
        features = []
        for f in json.load(open(path, encoding="utf-8"))["features"]:
            code = (f["properties"].get("shapeISO") or "").strip()
            # Parts without a code of the country, such as disputed areas
            if not code.startswith(f"{cc}-") or f["geometry"] is None:
                continue
            props = {"iso_3166_2": code, "name_en": f["properties"].get("shapeName") or code}
            for lang, name in REGION_NAMES.get(code, {}).items():
                props[f"name_{lang}"] = name
            features.append({"properties": props, "geometry": f["geometry"]})
        result[cc] = features
    return result


def main(src, dst, gb_dir=None):
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
        members = by_country.pop(cc, [])
        if members:
            props = {"iso_3166_2": f"CN-{cc}", **{f"name_{lang}": name for lang, name in names.items()}}
            by_country.setdefault("CN", []).append({"properties": props, "geometry": dissolve(members)})

    for cc in ("FR", "IT", "ES", "GB", "BE"):
        if cc in by_country:
            by_country[cc] = merge_levels(cc, by_country[cc])

    if gb_dir:
        by_country.update(geoboundaries(gb_dir))

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
            # A region of small islands can vanish whole, keep its finer outline
            g = g or geometry(f["geometry"], 0.0005)
            if not g:
                continue
            p = f["properties"]
            code = p["iso_3166_2"].strip()
            props = {"code": CODE_ALIASES.get(code, code), "name": (p.get("name_en") or p.get("name") or "").strip()}
            for lang in LANGS:
                value = (p.get(f"name_{lang}") or "").strip()
                if value and value != props["name"]:
                    props[f"name_{lang}"] = value
            out.append({"type": "Feature", "properties": props, "geometry": g})
        if not out:
            continue
        unwrap(out)
        view, frames = layout(out)
        # Frames come first so the regions inside them are drawn on top
        collection = {"type": "FeatureCollection", "view": view, "features": frames + out}
        text = json.dumps(collection, ensure_ascii=False, separators=(",", ":"))
        with open(os.path.join(dst, f"{cc}.json"), "w", encoding="utf-8") as fh:
            fh.write(text)
        index[cc] = len(out)
        total += len(text.encode("utf-8"))
    with open(os.path.join(dst, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, separators=(",", ":"), sort_keys=True)
    print(f"{len(index)} countries, {total / 1024 / 1024:.1f} MiB")


if __name__ == "__main__":
    args = sys.argv[1:]
    gb = None
    if "--geoboundaries" in args:
        at = args.index("--geoboundaries")
        gb = args[at + 1]
        del args[at:at + 2]
    main(args[0], args[1], gb)
