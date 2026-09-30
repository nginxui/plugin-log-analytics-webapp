<script setup lang="ts">
import type { ChinaMapData, WorldMapData } from '@/api/types'
import { Card as ACard, Segmented as ASegmented } from 'antdv-next'
import { computed, onMounted, ref, watch } from 'vue'
import { fetchAssetJson } from '@/assets'
import { $gettext } from '@/gettext'
import { useGeoTranslation } from '../geo'
import ChinaMapChart from './ChinaMapChart/ChinaMapChart.vue'
import HotspotMapChart from './HotspotMapChart.vue'
import RegionMapChart from './RegionMapChart.vue'
import WorldMapChart from './WorldMapChart/WorldMapChart.vue'

const props = defineProps<{
  worldData: WorldMapData[] | null
  chinaData: ChinaMapData[] | null
  enableChinaMap?: boolean
  loading: boolean
  logPath: string
  startTime: number
  endTime: number
}>()

const { isChineseLocale, translateCountry } = useGeoTranslation()

// The world map drills into the regions of a country; the hotspot map shows
// the busiest cities. The China map keeps its own provinces and cities.
type MapType = 'global' | 'hotspot' | 'china'
const mapType = ref<MapType>('global')
const regionCountry = ref<string | null>(null)
const canShowChinaMap = computed(() => isChineseLocale.value && Boolean(props.enableChinaMap))

// Countries with region outlines, from the index of the outline files
const outlinedCountries = ref<Set<string>>(new Set())
onMounted(async () => {
  try {
    const index = await fetchAssetJson<Record<string, number>>('assets/admin1/index.json')
    outlinedCountries.value = new Set(Object.keys(index))
  }
  catch (error) {
    console.error('[log-analytics] could not load the index of the region outlines', error)
  }
})

watch(canShowChinaMap, allowed => {
  if (!allowed && mapType.value === 'china')
    mapType.value = 'global'
})
watch(mapType, () => {
  regionCountry.value = null
})

function drillCountry(code: string) {
  if (code === 'CN' || code === 'HK' || code === 'MO' || code === 'TW') {
    if (canShowChinaMap.value)
      mapType.value = 'china'
    return
  }
  if (outlinedCountries.value.has(code))
    regionCountry.value = code
}

const segmentOptions = computed(() => {
  const options: { label: string, value: MapType }[] = [
    { label: $gettext('Global Map'), value: 'global' },
    { label: $gettext('Hotspots'), value: 'hotspot' },
  ]
  if (canShowChinaMap.value)
    options.push({ label: $gettext('China Map'), value: 'china' })
  return options
})

const cardTitle = computed(() => {
  if (mapType.value === 'hotspot')
    return $gettext('Access Hotspots')
  if (mapType.value === 'china')
    return $gettext('China Access Map')
  if (regionCountry.value)
    return $gettext('Access Map of %{country}', { country: translateCountry(regionCountry.value) })
  return $gettext('Global Access Map')
})
</script>

<template>
  <ACard :loading="loading">
    <template #title>
      <div class="la-flex la-items-center la-justify-between la-gap-2 la-flex-wrap">
        <span>{{ cardTitle }}</span>
        <ASegmented v-model:value="mapType" :options="segmentOptions" />
      </div>
    </template>

    <div class="geo-map-container">
      <!-- World map, or the regions of the country clicked on it -->
      <div v-show="mapType === 'global' && !regionCountry">
        <WorldMapChart
          :data="props.worldData"
          :loading="props.loading"
          @drill-country="drillCountry"
        />
      </div>
      <RegionMapChart
        v-if="mapType === 'global' && regionCountry"
        :country="regionCountry"
        :log-path="props.logPath"
        :start-time="props.startTime"
        :end-time="props.endTime"
        @back="regionCountry = null"
      />

      <!-- The busiest cities, fetched once the view is chosen -->
      <HotspotMapChart
        v-if="mapType === 'hotspot'"
        :log-path="props.logPath"
        :start-time="props.startTime"
        :end-time="props.endTime"
      />

      <!-- China Map, its outlines are only fetched once it can be shown -->
      <div v-if="canShowChinaMap" v-show="mapType === 'china'">
        <ChinaMapChart
          :data="props.chinaData"
          :loading="props.loading"
          :log-path="props.logPath"
          :start-time="props.startTime"
          :end-time="props.endTime"
        />
      </div>
    </div>
  </ACard>
</template>

<style scoped>
.geo-map-container {
  min-height: 400px;
}
</style>
