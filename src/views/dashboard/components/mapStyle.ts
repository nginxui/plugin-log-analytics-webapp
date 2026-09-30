// Colors of the maps in the light and the dark theme, shared by the region and
// hotspot maps.
import type { ComputedRef } from 'vue'
import { computed } from 'vue'
import { useHostTheme } from '@/theme'

export interface MapStyle {
  fontColor: string
  background: string
  areaColor: string
  borderColor: string
  emphasisColor: string
  scale: string[]
  pointColor: string
  tooltip: { backgroundColor: string, borderColor: string, textStyle: { color: string } }
}

export function useMapStyle(): ComputedRef<MapStyle> {
  const theme = useHostTheme()
  return computed(() => {
    const dark = theme.value === 'dark'
    return {
      fontColor: dark ? '#b4b4b4' : '#333',
      background: dark ? 'transparent' : '#fff',
      areaColor: dark ? '#2a2a2a' : '#f5f5f5',
      borderColor: dark ? '#555' : '#ddd',
      emphasisColor: dark ? '#3a5a7c' : '#ffd666',
      scale: dark ? ['#003a70', '#1890ff', '#69c0ff'] : ['#e6f3ff', '#1890ff', '#0050b3'],
      pointColor: dark ? '#ffa940' : '#fa541c',
      tooltip: {
        backgroundColor: dark ? 'rgba(50, 50, 50, 0.9)' : 'rgba(255, 255, 255, 0.9)',
        borderColor: dark ? '#555' : '#ccc',
        textStyle: { color: dark ? '#e0e0e0' : '#333' },
      },
    }
  })
}

/** Text of a tooltip, with the parts escaped for HTML. */
export function tooltipHtml(title: string, lines: string[]): string {
  const escape = (text: string) => text.replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`)
  return `<div style="font-size: 14px;"><strong>${escape(title)}</strong>${lines.map(line => `<br/>${escape(line)}`).join('')}</div>`
}
