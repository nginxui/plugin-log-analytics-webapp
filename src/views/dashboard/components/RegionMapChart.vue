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
interface Outline { features: OutlineFeature[] }

const style = useMapStyle()
const hostLocale = useHostLocale()
const { translateCountry } = useGeoTranslation()

// The outlines of the regions of a country, registered once per country
const registered = new Map<string, Map<string, Record<string, unknown>>>()
const regions = ref<Map<string, Record<string, unknown>> | null>(null)
const data = ref<RegionMapData[]>([])
const loading = ref(false)
const failed = ref(false)

const mapName = computed(() => `admin1-${props.country}`)

async function load() {
  loading.value = true
  failed.value = false
  try {
    let known = registered.get(props.country)
    if (!known) {
      const outline = await fetchAssetJson<Outline>(`assets/admin1/${props.country}.json`)
      registerMap(mapName.value, outline as unknown as Parameters<typeof registerMap>[1])
      known = new Map(outline.features.map(f => [String(f.properties.code), f.properties]))
      registered.set(props.country, known)
    }
    regions.value = known
    const answer = await getRegionMapData({
      path: props.logPath,
      start_time: props.startTime,
      end_time: props.endTime,
      country: props.country,
    })
    data.value = answer.data ?? []
  }
  catch (error) {
    console.error(`[log-analytics] could not load the regions of ${props.country}`, error)
    failed.value = true
    data.value = []
  }
  finally {
    loading.value = false
  }
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
  if (!regions.value)
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
      left: 'left',
      top: 'bottom',
      text: [$gettext('High'), $gettext('Low')],
      textStyle: { color: style.value.fontColor },
      inRange: { color: style.value.scale },
      calculable: false,
    },
    series: [{
      name: $gettext('Visits'),
      type: 'map',
      map: mapName.value,
      nameProperty: 'code',
      roam: true,
      emphasis: {
        label: { show: true, color: style.value.fontColor, formatter: (p: { name: string }) => regionName(p.name) },
        itemStyle: { areaColor: style.value.emphasisColor },
      },
      itemStyle: { areaColor: style.value.areaColor, borderColor: style.value.borderColor, borderWidth: 0.5 },
      data: drawn.value.map(item => ({ ...item, name: item.code })),
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
      <div v-else class="la-grid la-grid-cols-1 lg:la-grid-cols-2 la-gap-6">
        <VChart :option="option" style="height: 400px; width: 100%" autoresize />
        <div class="la-flex la-flex-col la-justify-center">
          <div class="la-mb-3 la-text-sm la-font-bold">
            {{ $gettext('Top 10 Regions') }}
          </div>
          <ATable :columns="columns" :data-source="tableData" :pagination="false" size="small" :scroll="{ y: 340 }" />
        </div>
      </div>
    </ASpin>
  </div>
</template>
