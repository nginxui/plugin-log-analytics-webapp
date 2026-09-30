<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import type { CityPointData } from '@/api/types'
import { Empty as AEmpty, Spin as ASpin, Table as ATable } from 'antdv-next'
import { EffectScatterChart, ScatterChart } from 'echarts/charts'
import { GeoComponent, TooltipComponent } from 'echarts/components'
import { getMap, registerMap, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { computed, onMounted, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { getCityPoints } from '@/api/client'
import { fetchAssetJson } from '@/assets'
import { $gettext } from '@/gettext'
import { useGeoTranslation } from '../geo'
import { tooltipHtml, useMapStyle } from './mapStyle'

const props = defineProps<{
  logPath: string
  startTime: number
  endTime: number
}>()

use([ScatterChart, EffectScatterChart, GeoComponent, TooltipComponent, CanvasRenderer])

/** Most cities drawn on the map. */
const POINT_LIMIT = 500
/** The busiest cities pulse. */
const PULSING = 10

const style = useMapStyle()
const { translateCountry } = useGeoTranslation()

const mapReady = ref(Boolean(getMap('world')))
const points = ref<CityPointData[]>([])
const loading = ref(false)

onMounted(async () => {
  if (mapReady.value)
    return
  try {
    registerMap('world', await fetchAssetJson<Parameters<typeof registerMap>[1]>('assets/world.json'))
    mapReady.value = true
  }
  catch (error) {
    console.error('[log-analytics] could not load the world outline', error)
  }
})

async function load() {
  loading.value = true
  try {
    const answer = await getCityPoints({
      path: props.logPath,
      start_time: props.startTime,
      end_time: props.endTime,
      limit: POINT_LIMIT,
    })
    points.value = answer.data ?? []
  }
  catch (error) {
    console.error('[log-analytics] could not load the cities', error)
    points.value = []
  }
  finally {
    loading.value = false
  }
}

watch(() => [props.logPath, props.startTime, props.endTime], load, { immediate: true })

function placeOf(point: CityPointData): string {
  return `${point.city} · ${translateCountry(point.country)}`
}

const option = computed((): EChartsOption => {
  if (!mapReady.value)
    return {}
  const max = Math.max(1, ...points.value.map(p => p.value))
  // The area of a point follows the visits
  const size = (value: number) => 4 + 22 * Math.sqrt(value / max)
  const toItem = (p: CityPointData) => ({ name: placeOf(p), value: [p.lon, p.lat, p.value], point: p })
  const tooltip = (raw: unknown) => {
    const { data } = raw as { data?: { point?: CityPointData } }
    const point = data?.point
    if (!point)
      return ''
    return tooltipHtml(placeOf(point), [
      `${$gettext('Visits')}: ${point.value.toLocaleString()}`,
      `${$gettext('Percentage')}: ${point.percent.toFixed(2)}%`,
    ])
  }
  return {
    backgroundColor: style.value.background,
    tooltip: { trigger: 'item', ...style.value.tooltip, formatter: tooltip },
    geo: {
      map: 'world',
      roam: true,
      itemStyle: { areaColor: style.value.areaColor, borderColor: style.value.borderColor, borderWidth: 0.5 },
      emphasis: { disabled: true },
    },
    series: [
      {
        type: 'scatter',
        coordinateSystem: 'geo',
        data: points.value.slice(PULSING).map(toItem),
        symbolSize: (value: number[]) => size(value[2]),
        itemStyle: { color: style.value.pointColor, opacity: 0.7 },
      },
      {
        type: 'effectScatter',
        coordinateSystem: 'geo',
        data: points.value.slice(0, PULSING).map(toItem),
        symbolSize: (value: number[]) => size(value[2]),
        rippleEffect: { scale: 3, brushType: 'stroke' },
        itemStyle: { color: style.value.pointColor },
        zlevel: 1,
      },
    ],
  }
})

const tableData = computed(() => points.value.slice(0, 10).map(p => ({
  key: `${p.country}|${p.city}|${p.lat}|${p.lon}`,
  city: placeOf(p),
  value: p.value,
  percent: p.percent.toFixed(2),
})))

const columns = computed(() => [
  { title: $gettext('City'), dataIndex: 'city', key: 'city' },
  { title: $gettext('Visits'), dataIndex: 'value', key: 'value', align: 'right' as const, render: (value: number) => value.toLocaleString() },
  { title: $gettext('Percentage'), dataIndex: 'percent', key: 'percent', align: 'right' as const, render: (value: string) => `${value}%` },
])
</script>

<template>
  <ASpin :spinning="loading">
    <div v-if="!loading && points.length === 0" class="la-flex la-items-center la-justify-center" style="height: 300px">
      <AEmpty :description="$gettext('No city data available')" />
    </div>
    <div v-else class="la-grid la-grid-cols-1 lg:la-grid-cols-2 la-gap-6">
      <VChart :option="option" style="height: 400px; width: 100%" autoresize />
      <div class="la-flex la-flex-col la-justify-center">
        <div class="la-mb-3 la-text-sm la-font-bold">
          {{ $gettext('Top 10 Cities') }}
        </div>
        <ATable :columns="columns" :data-source="tableData" :pagination="false" size="small" :scroll="{ y: 340 }" />
      </div>
    </div>
  </ASpin>
</template>
