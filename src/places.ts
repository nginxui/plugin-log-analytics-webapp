// Names of cities and regions in the language of the host. The backend answers
// the English names with the GeoNames id of a city and the ISO 3166-2 code of
// its region; the names of the other languages are files of the package, see
// scripts/build-place-names.ts. Only the file of the current language is
// fetched, and a place without a name in it keeps its English name.
import { ref, watchEffect } from 'vue'
import { fetchAssetJson } from '@/assets'
import { useHostLocale } from '@/theme'

interface PlaceNames {
  cities: Record<string, string>
  regions: Record<string, string>
}

const names = new Map<string, PlaceNames>()
const loading = new Map<string, Promise<void>>()
// Bumped when a language finished loading, so names re-render.
const loadedVersion = ref(0)

function ensurePlaceNames(locale: string): Promise<void> {
  let pending = loading.get(locale)
  if (!pending) {
    pending = fetchAssetJson<PlaceNames>(`assets/places/${locale}.json`)
      .then(file => {
        names.set(locale, file)
        loadedVersion.value += 1
      })
      .catch(() => {
        // English names stay, a later view retries.
        loading.delete(locale)
      })
    loading.set(locale, pending)
  }
  return pending
}

export function usePlaceNames() {
  const hostLocale = useHostLocale()
  watchEffect(() => {
    const locale = hostLocale.value
    if (locale && locale !== 'en')
      void ensurePlaceNames(locale)
  })

  function lookup(kind: keyof PlaceNames, key: string | number | undefined, english: string): string {
    void loadedVersion.value
    if (!key)
      return english
    return names.get(hostLocale.value)?.[kind][String(key)] || english
  }

  return {
    /** The name of a city by its GeoNames id, the English name without one. */
    cityName: (id: number | undefined, english: string) => lookup('cities', id, english),
    /** The name of a region by its ISO 3166-2 code, the English name without one. */
    regionName: (code: string | undefined, english: string) => lookup('regions', code, english),
  }
}
