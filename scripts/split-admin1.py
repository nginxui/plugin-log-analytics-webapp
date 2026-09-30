"""Split the Natural Earth admin-1 boundaries into one small GeoJSON file per
country for the region maps of the log analytics plugins.

    python3 split_admin1.py ne_10m_admin_1_states_provinces.geojson out/

Each feature keeps its ISO 3166-2 code and the names in the languages of the
host. Geometry is simplified with Douglas-Peucker and rounded to 3 decimals.
China, Hong Kong, Macau and Taiwan are left out: the China map covers them.
"""
import json
import math
import os
import sys

LANGS = ["ar", "de", "en", "es", "fr", "ja", "ko", "pt", "ru", "tr", "uk", "vi", "zh", "zht"]
SKIP = {"CN", "HK", "MO", "TW"}


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


def main(src, dst):
    data = json.load(open(src, encoding="utf-8"))
    by_country = {}
    for f in data["features"]:
        p = f["properties"]
        cc = (p.get("iso_a2") or "").strip()
        code = (p.get("iso_3166_2") or "").strip()
        if len(cc) != 2 or cc == "-9" or cc in SKIP or not code or f["geometry"] is None:
            continue
        by_country.setdefault(cc, []).append(f)

    os.makedirs(dst, exist_ok=True)
    total = 0
    index = {}
    for cc, features in sorted(by_country.items()):
        # Larger countries tolerate coarser outlines: about 1/400 of their span
        tolerance = max(0.002, min(0.05, bbox_span(features) / 400))
        out = []
        for f in features:
            g = geometry(f["geometry"], tolerance)
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
        text = json.dumps({"type": "FeatureCollection", "features": out}, ensure_ascii=False, separators=(",", ":"))
        with open(os.path.join(dst, f"{cc}.json"), "w", encoding="utf-8") as fh:
            fh.write(text)
        index[cc] = len(out)
        total += len(text.encode("utf-8"))
    with open(os.path.join(dst, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, separators=(",", ":"), sort_keys=True)
    print(f"{len(index)} countries, {total / 1024 / 1024:.1f} MiB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
