"""Check the region outlines against the subdivision codes of a GeoLite2 City
database, the codes the plugins count visitors under.

    python3 check-admin1.py GeoLite2-City.mmdb public/assets/admin1
    python3 check-admin1.py --suggest GeoLite2-City.mmdb public/assets/admin1
    python3 check-admin1.py --write-baseline GeoLite2-City.mmdb public/assets/admin1

For every country the outline draws one level of subdivisions. The report
lists the codes of that level the database knows and the outline lacks:
visitors from those regions are counted but not drawn. Run it after updating
the Natural Earth data or the database, see the README. Gaps that cannot be
closed with the Natural Earth geometry, such as regions created after its
release, are kept in admin1-known-gaps.json; the check exits with 1 only for
gaps not listed there. --write-baseline rewrites that list.

With --suggest it prints, as JSON, outline codes that match a missing code by
name. Codes change when ISO 3166-2 is revised, and Natural Earth can lag; after
a review the pairs go into admin1-code-aliases.json, which the split script
applies.

Only the standard library is used, so the database is read by a small MMDB
decoder below.
"""
import json
import os
import re
import struct
import sys
import unicodedata

# Countries the plugins count under CN, as regions of the China map
CHINA_REGIONS = {"HK", "MO", "TW"}
METADATA_MARKER = b"\xab\xcd\xefMaxMind.com"


class Reader:
    def __init__(self, path):
        with open(path, "rb") as fh:
            self.buf = fh.read()
        start = self.buf.rfind(METADATA_MARKER)
        if start < 0:
            raise ValueError(f"{path} is not a MaxMind database")
        self.meta, _ = self.decode(start + len(METADATA_MARKER), 0)
        self.node_count = self.meta["node_count"]
        self.record_size = self.meta["record_size"]
        self.tree_size = self.node_count * self.record_size // 4
        self.data_start = self.tree_size + 16

    def records(self):
        """Every record of the search tree that points into the data section."""
        buf, size, count = self.buf, self.record_size, self.node_count
        seen = set()
        for node in range(count):
            base = node * size // 4
            if size == 24:
                left = int.from_bytes(buf[base:base + 3], "big")
                right = int.from_bytes(buf[base + 3:base + 6], "big")
            elif size == 28:
                middle = buf[base + 3]
                left = ((middle & 0xF0) << 20) | int.from_bytes(buf[base:base + 3], "big")
                right = ((middle & 0x0F) << 24) | int.from_bytes(buf[base + 4:base + 7], "big")
            else:
                left, right = struct.unpack(">II", buf[base:base + 8])
            for value in (left, right):
                if value > count and value not in seen:
                    seen.add(value)
                    yield self.data_start + value - count - 16

    def decode(self, offset, base):
        """Decodes the value at offset. base is where pointers count from."""
        ctrl = self.buf[offset]
        offset += 1
        kind = ctrl >> 5
        if kind == 1:
            size = (ctrl >> 3) & 0x3
            value = ctrl & 0x7
            if size == 0:
                pointer = (value << 8) | self.buf[offset]
            elif size == 1:
                pointer = ((value << 16) | int.from_bytes(self.buf[offset:offset + 2], "big")) + 2048
            elif size == 2:
                pointer = ((value << 24) | int.from_bytes(self.buf[offset:offset + 3], "big")) + 526336
            else:
                pointer = int.from_bytes(self.buf[offset:offset + 4], "big")
            value, _ = self.decode(base + pointer, base)
            return value, offset + size + 1
        if kind == 0:
            kind = 7 + self.buf[offset]
            offset += 1
        size = ctrl & 0x1F
        if size >= 29:
            extra = size - 28
            number = int.from_bytes(self.buf[offset:offset + extra], "big")
            size = {1: 29, 2: 285, 3: 65821}[extra] + number
            offset += extra
        if kind == 2:
            return self.buf[offset:offset + size].decode("utf-8"), offset + size
        if kind == 3:
            return struct.unpack(">d", self.buf[offset:offset + 8])[0], offset + 8
        if kind == 4:
            return self.buf[offset:offset + size], offset + size
        if kind in (5, 6, 9, 10):
            return int.from_bytes(self.buf[offset:offset + size], "big"), offset + size
        if kind == 8:
            return int.from_bytes(self.buf[offset:offset + size], "big", signed=True), offset + size
        if kind == 7:
            result = {}
            for _ in range(size):
                key, offset = self.decode(offset, base)
                result[key], offset = self.decode(offset, base)
            return result, offset
        if kind == 11:
            items = []
            for _ in range(size):
                item, offset = self.decode(offset, base)
                items.append(item)
            return items, offset
        if kind == 14:
            return bool(size), offset
        if kind == 15:
            return struct.unpack(">f", self.buf[offset:offset + 4])[0], offset + 4
        raise ValueError(f"unknown data type {kind} at {offset}")


def database_codes(path):
    """The subdivision codes of each country at level 1 and 2, with their
    English names."""
    reader = Reader(path)
    codes = {}
    for offset in reader.records():
        record, _ = reader.decode(offset, reader.data_start)
        country = (record.get("country") or {}).get("iso_code")
        if not country:
            continue
        if country in CHINA_REGIONS:
            codes.setdefault("CN", ({}, {}))[0][f"CN-{country}"] = country
            continue
        levels = codes.setdefault(country, ({}, {}))
        for level, sub in enumerate((record.get("subdivisions") or [])[:2]):
            if sub.get("iso_code"):
                levels[level][f"{country}-{sub['iso_code']}"] = (sub.get("names") or {}).get("en", "")
    return codes


# Words that differ between the two sources without changing the place
FILLER = re.compile(r"\b(province|provincia|region|regione|county|state|district|department|voivodeship|"
                    r"governorate|municipality|oblast|prefecture|city|of|the|autonomous|special|capital)\b")


def plain(name):
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]+", " ", FILLER.sub(" ", name)).strip()


def drawn_level(codes, drawn):
    """The level of the database codes an outline draws: the one it shares more
    codes with, the first when it shares none."""
    first, second = codes
    return second if len(drawn & set(second)) > len(drawn & set(first)) else first


def suggest(outlines, codes, index):
    """Outline codes no database code uses, paired by name with the database
    codes the outline lacks, at the level it draws."""
    aliases = {}
    for country in sorted(codes):
        if country not in index:
            continue
        outline = json.load(open(os.path.join(outlines, f"{country}.json"), encoding="utf-8"))
        features = [f["properties"] for f in outline["features"] if not f["properties"].get("frame")]
        drawn = {p["code"] for p in features}
        known = set(codes[country][0]) | set(codes[country][1])
        unused = {plain(p.get("name", "")): p["code"] for p in features if p["code"] not in known}
        for code, name in drawn_level(codes[country], drawn).items():
            match = code not in drawn and unused.get(plain(name))
            if match:
                aliases[match] = code
    return aliases


BASELINE = os.path.join(os.path.dirname(__file__), "admin1-known-gaps.json")


def main(mmdb, outlines, suggesting=False, baseline=False):
    index = json.load(open(os.path.join(outlines, "index.json"), encoding="utf-8"))
    codes = database_codes(mmdb)
    if suggesting:
        print(json.dumps(suggest(outlines, codes, index), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    known = {} if baseline or not os.path.exists(BASELINE) else json.load(open(BASELINE, encoding="utf-8"))
    gaps, problems = {}, 0
    for country in sorted(codes):
        first, second = (set(level) for level in codes[country])
        if not first:
            continue
        if country not in index:
            gaps[country] = sorted(first)
            new = "" if known.get(country) == gaps[country] else "new, "
            print(f"{country}: {new}no outline, {len(first)} regions in the database")
            problems += bool(new)
            continue
        outline = json.load(open(os.path.join(outlines, f"{country}.json"), encoding="utf-8"))
        drawn = {f["properties"]["code"] for f in outline["features"] if not f["properties"].get("frame")}
        level = set(drawn_level(codes[country], drawn))
        missing = sorted(level - drawn)
        if missing:
            gaps[country] = missing
            fresh = sorted(set(missing) - set(known.get(country, [])))
            note = f" (new: {', '.join(fresh)})" if fresh else ""
            print(f"{country}: {len(missing)} of {len(level)} lack an outline: {', '.join(missing)}{note}")
            problems += bool(fresh)
    if baseline:
        with open(BASELINE, "w", encoding="utf-8") as fh:
            json.dump(gaps, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"{len(gaps)} countries with known gaps written to {os.path.basename(BASELINE)}")
        return 0
    print(f"{len(codes)} countries checked, {len(gaps)} with gaps, {problems} with new gaps")
    return 1 if problems else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(main(args[0], args[1], "--suggest" in sys.argv, "--write-baseline" in sys.argv))
