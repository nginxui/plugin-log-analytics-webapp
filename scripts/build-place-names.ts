// Builds the place names of the dashboards, one file per language of the host:
//
//   bun scripts/build-place-names.ts city-names.json public/assets/admin1 public/assets/places
//
// public/assets/places/<locale>.json holds { cities, regions }: the names of the
// cities by GeoNames id, from the cache fetch-city-names.py writes, and the
// names of the regions by ISO 3166-2 code, from the region outlines. A name
// equal to the English one is left out, the page shows the English name the
// backend answers then. English has no file. The files are built here and
// shipped with the package; the plugins never fetch these sources.
import { Buffer } from 'node:buffer'
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import * as OpenCC from 'opencc-js'

interface CachedCity {
  country: string
  /** The names of the database, only to leave out names equal to the English one. */
  geolite: Record<string, string>
  wikidata?: Record<string, string>
  geonames?: Record<string, string>
  /** Languages whose GeoNames name is marked preferred. */
  geonames_preferred?: string[]
}

// Simplified names to the characters and words used in Taiwan, and any
// Chinese name to simplified characters
const toTaiwan = OpenCC.Converter({ from: 'cn', to: 'twp' })
const toSimplified = OpenCC.Converter({ from: 't', to: 'cn' })

type Pick = (city: CachedCity) => string | undefined

// Wikidata labels come first. GeoNames fills in, mostly for large cities whose
// Wikidata item links another GeoNames feature. The names the GeoLite2
// database carries are not shipped, its license does not allow it.
const wd = (lang: string): Pick => city => city.wikidata?.[lang]
const gn = (lang: string): Pick => city => city.geonames?.[lang]
const first = (...picks: Pick[]): Pick => city => picks.map(pick => pick(city)?.trim()).find(Boolean)
// Names in the Latin script mostly equal the English one, there GeoNames often
// has an old or a local spelling unless the name is marked preferred
const gnPreferred = (lang: string): Pick => city => city.geonames_preferred?.includes(lang) ? city.geonames?.[lang] : undefined
const both = (lang: string): Pick => first(wd(lang), gn(lang))
const latin = (lang: string): Pick => first(wd(lang), gnPreferred(lang))
function inSimplified(pick: Pick): Pick {
  return city => {
    const name = pick(city)
    return name && toSimplified(name)
  }
}

const simplified = first(wd('zh-cn'), wd('zh-hans'), gn('zh-CN'), gn('zh-Hans'), inSimplified(wd('zh')), inSimplified(gn('zh')))

// The city names of each locale, the best source first
const CITY_NAMES: Record<string, Pick> = {
  ar: both('ar'),
  de_DE: latin('de'),
  es: latin('es'),
  fr_FR: latin('fr'),
  it_IT: latin('it'),
  ja_JP: both('ja'),
  ko_KR: both('ko'),
  pt_PT: first(wd('pt'), wd('pt-br'), gnPreferred('pt'), gnPreferred('pt-BR')),
  ru_RU: both('ru'),
  tr_TR: latin('tr'),
  uk_UA: both('uk'),
  vi_VN: latin('vi'),
  zh_CN: simplified,
  // The names used in Taiwan where a source has them, others are converted
  zh_TW: first(wd('zh-tw'), gn('zh-TW'), wd('zh-hant'), gn('zh-Hant'), wd('zh-hk'), gn('zh-HK'), city => {
    const name = simplified(city)
    return name && toTaiwan(name)
  }),
}

// The name_<language> members of the region outlines, see split-admin1.py
const REGION_LANGUAGE: Record<string, string> = {
  ar: 'ar',
  de_DE: 'de',
  es: 'es',
  fr_FR: 'fr',
  it_IT: 'it',
  ja_JP: 'ja',
  ko_KR: 'ko',
  pt_PT: 'pt',
  ru_RU: 'ru',
  tr_TR: 'tr',
  uk_UA: 'uk',
  vi_VN: 'vi',
  zh_CN: 'zh',
  zh_TW: 'zht',
}

// The Chinese names of the outlines mix both scripts, these bring each to one
const REGION_SCRIPT: Record<string, (name: string) => string> = {
  zh_CN: name => name && toSimplified(name),
  zh_TW: name => name && toTaiwan(name),
}

function regionsOf(dir: string): Record<string, string>[] {
  const regions: Record<string, string>[] = []
  for (const file of readdirSync(dir).filter(name => /^[A-Z]{2}\.json$/.test(name))) {
    const outline = JSON.parse(readFileSync(join(dir, file), 'utf8')) as { features: { properties: Record<string, string> }[] }
    for (const { properties } of outline.features) {
      if (!properties.frame)
        regions.push(properties)
    }
  }
  return regions
}

function main(cachePath: string, admin1Dir: string, outDir: string) {
  const cities = JSON.parse(readFileSync(cachePath, 'utf8')) as Record<string, CachedCity>
  const regions = regionsOf(admin1Dir)
  mkdirSync(outDir, { recursive: true })
  for (const [locale, pick] of Object.entries(CITY_NAMES)) {
    const cityNames: Record<string, string> = {}
    for (const [id, city] of Object.entries(cities)) {
      const name = pick(city)
      if (name && name !== city.geolite.en)
        cityNames[id] = name
    }
    const regionNames: Record<string, string> = {}
    for (const properties of regions) {
      const name = REGION_SCRIPT[locale]?.(properties[`name_${REGION_LANGUAGE[locale]}`] ?? '') ?? properties[`name_${REGION_LANGUAGE[locale]}`]
      if (name && name !== properties.name)
        regionNames[properties.code] = name
    }
    const text = JSON.stringify({ cities: cityNames, regions: regionNames })
    writeFileSync(join(outDir, `${locale}.json`), text)
    console.warn(`${locale}: ${Object.keys(cityNames).length} cities, ${Object.keys(regionNames).length} regions, ${(Buffer.byteLength(text) / 1024).toFixed(0)} KiB`)
  }
}

const [cachePath, admin1Dir, outDir] = process.argv.slice(2)
if (!cachePath || !admin1Dir || !outDir)
  throw new Error('usage: bun scripts/build-place-names.ts city-names.json public/assets/admin1 public/assets/places')
main(cachePath, admin1Dir, outDir)
