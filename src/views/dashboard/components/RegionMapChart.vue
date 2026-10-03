<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import type { RegionMapData } from '@/api/types'
import { ArrowLeftOutlined } from '@antdv-next/icons'
import { Button as AButton, Empty as AEmpty, Spin as ASpin, Table as ATable } from 'antdv-next'
import { MapChart } from 'echarts/charts'
import { TooltipComponent, VisualMapComponent } from 'echarts/components'
import { registerMap, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { computed, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { getRegionMapData } from '@/api/client'
import { fetchAssetJson } from '@/assets'
import { $gettext } from '@/gettext'
import { useHostLocale } from '@/theme'
import { regionNameOf, useGeoTranslation } from '../geo'
import MapLegend from './MapLegend.vue'
import { tooltipHtml, useMapStyle } from './mapStyle'

const props = defineProps<{
  country: string
  logPath: string
  startTime: number
  endTime: number
}>()

const emit = defineEmits<{ back: [] }>()

use([MapChart, TooltipComponent, VisualMapComponent, CanvasRenderer])

interface OutlineFeature { properties: Record<string, unknown> }
/** The top left and bottom right corners of the main territory. */
type View = [[number, number], [number, number]]
interface Outline { view?: View, features: OutlineFeature[] }
interface Known { regions: Map<string, Record<string, unknown>>, frames: string[], view?: View }

const style = useMapStyle()
const hostLocale = useHostLocale()
const { translateCountry } = useGeoTranslation()

// The outlines of the regions of a country, registered once per country
const registered = new Map<string, Known>()
const regions = ref<Map<string, Record<string, unknown>> | null>(null)
const view = ref<View>()
const frames = ref<string[]>([])
const data = ref<RegionMapData[]>([])
const loading = ref(false)
const failed = ref(false)

// The map the chart draws. It changes only once the outline of the new
// country is registered, since ECharts fails on a map it does not know.
const shownMap = ref<string>()
let latest = 0

async function load() {
  const request = ++latest
  const country = props.country
  loading.value = true
  failed.value = false
  try {
    let known = registered.get(country)
    if (!known) {
      const outline = await fetchAssetJson<Outline>(`assets/admin1/${country}.json`)
      registerMap(`admin1-${country}`, outline as unknown as Parameters<typeof registerMap>[1])
      // Frames around the insets of outlying regions are drawn but not counted
      const isFrame = (f: OutlineFeature) => Boolean(f.properties.frame)
      known = {
        regions: new Map(outline.features.filter(f => !isFrame(f)).map(f => [String(f.properties.code), f.properties])),
        frames: outline.features.filter(isFrame).map(f => String(f.properties.code)),
        view: outline.view,
      }
      registered.set(country, known)
    }
    const answer = await getRegionMapData({
      path: props.logPath,
      start_time: props.startTime,
      end_time: props.endTime,
      country,
    })
    // A newer request took over while this one waited
    if (request !== latest)
      return
    reportMissingRegions(country, answer.data ?? [], known.regions)
    shownMap.value = `admin1-${country}`
    regions.value = known.regions
    view.value = known.view
    frames.value = known.frames
    data.value = answer.data ?? []
  }
  catch (error) {
    if (request !== latest)
      return
    console.error(`[log-analytics] could not load the regions of ${country}`, error)
    failed.value = true
    data.value = []
  }
  finally {
    if (request === latest)
      loading.value = false
  }
}

// The outlines draw one level of subdivisions. A code of that level the
// outline lacks means the outline data is out of date, see the README.
function reportMissingRegions(country: string, items: RegionMapData[], outlined: Map<string, unknown>) {
  const drawnAt = (level: number) => items.filter(item => item.level === level && outlined.has(item.code)).length
  const level = drawnAt(2) > drawnAt(1) ? 2 : 1
  const missing = items.filter(item => item.level === level && !outlined.has(item.code)).map(item => item.code)
  if (missing.length > 0)
    console.warn(`[log-analytics] the region outline of ${country} lacks ${missing.join(', ')}`)
}

watch(() => [props.country, props.logPath, props.startTime, props.endTime], load, { immediate: true })

function regionName(code: string): string {
  const properties = regions.value?.get(code)
  return properties ? regionNameOf(properties, hostLocale.value) : code
}

// The counts of the regions the outlines draw. A country is drawn at one
// level, the counts of the other level are left out.
const drawn = computed(() => data.value.filter(item => regions.value?.has(item.code)))

const option = computed((): EChartsOption => {
  if (!regions.value || !shownMap.value)
    return {}
  const max = Math.max(1, ...drawn.value.map(item => item.value))
  return {
    backgroundColor: style.value.background,
    tooltip: {
      trigger: 'item',
      ...style.value.tooltip,
      formatter: raw => {
        const params = raw as { name: string, data?: RegionMapData }
        const name = regionName(params.name)
        if (!params.data)
          return tooltipHtml(name, [$gettext('No data')])
        return tooltipHtml(name, [
          `${$gettext('Visits')}: ${params.data.value.toLocaleString()}`,
          `${$gettext('Percentage')}: ${params.data.percent.toFixed(2)}%`,
        ])
      },
    },
    visualMap: {
      min: 0,
      max,
      // The scale is shown by MapLegend under the chart
      show: false,
      inRange: { color: style.value.scale },
      calculable: false,
    },
    series: [{
      name: $gettext('Visits'),
      type: 'map',
      map: shownMap.value,
      nameProperty: 'code',
      // Opens on the main territory with the insets of outlying regions
      boundingCoords: view.value,
      // The outlines are projected already, see split-admin1.py
      aspectScale: 1,
      roam: true,
      // The default layout keeps the aspect but fills only 80% of the chart
      zoom: 1.2,
      emphasis: {
        label: { show: true, color: style.value.fontColor, formatter: (p: { name: string }) => regionName(p.name) },
        itemStyle: { areaColor: style.value.emphasisColor },
      },
      itemStyle: { areaColor: style.value.areaColor, borderColor: style.value.borderColor, borderWidth: 0.5 },
      data: [
        ...drawn.value.map(item => ({ ...item, name: item.code })),
        ...frames.value.map(code => ({
          name: code,
          itemStyle: { areaColor: 'transparent', borderColor: style.value.frameColor, borderWidth: 1 },
          emphasis: { disabled: true },
          tooltip: { show: false },
        })),
      ],
    }],
  }
})

const tableData = computed(() => drawn.value.slice(0, 10).map(item => ({
  key: item.code,
  region: regionName(item.code),
  value: item.value,
  percent: item.percent.toFixed(2),
})))

const columns = computed(() => [
  { title: $gettext('Region'), dataIndex: 'region', key: 'region' },
  { title: $gettext('Visits'), dataIndex: 'value', key: 'value', align: 'right' as const, render: (value: number) => value.toLocaleString() },
  { title: $gettext('Percentage'), dataIndex: 'percent', key: 'percent', align: 'right' as const, render: (value: string) => `${value}%` },
])
</script>

<template>
  <div>
    <div class="la-mb-3 la-flex la-items-center la-gap-2">
      <AButton size="small" @click="emit('back')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ $gettext('World') }}
      </AButton>
      <span class="la-font-medium">{{ translateCountry(country) }}</span>
    </div>

    <ASpin :spinning="loading">
      <div v-if="failed || (!loading && drawn.length === 0)" class="la-flex la-items-center la-justify-center" style="height: 300px">
        <AEmpty :description="failed ? $gettext('The regions of this country could not be loaded') : $gettext('No geographic data available')" />
      </div>
      <div v-else class="la-grid la-grid-cols-1 lg:la-grid-cols-5 la-gap-6">
        <div class="lg:la-col-span-3">
          <VChart class="map-chart" :option="option" autoresize />
          <MapLegend :colors="style.scale" />
        </div>
        <div class="lg:la-col-span-2 la-flex la-flex-col la-justify-center">
          <div class="la-mb-3 la-text-sm la-font-bold">
            {{ $gettext('Top 10 Regions') }}
          </div>
          <ATable :columns="columns" :data-source="tableData" :pagination="false" size="small" :scroll="{ y: 340 }" />
        </div>
      </div>
    </ASpin>
  </div>
</template>

<style scoped>
.map-chart {
  width: 100%;
  /* The height follows the width, so narrow screens keep little blank space */
  aspect-ratio: 3 / 2;
  min-height: 240px;
  max-height: 420px;
}
</style>
