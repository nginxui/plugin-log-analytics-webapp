<script setup lang="ts">
import { computed } from 'vue'
import { $gettext } from '@/gettext'

// The color scale of a map, shown under the chart so it never covers the map
const props = defineProps<{ colors: string[] }>()

const gradient = computed(() => `linear-gradient(to right, ${props.colors.join(', ')})`)
</script>

<template>
  <div class="map-legend">
    <span>{{ $gettext('Low') }}</span>
    <span class="map-legend-bar" :style="{ background: gradient }" />
    <span>{{ $gettext('High') }}</span>
  </div>
</template>

<style scoped>
.map-legend {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.map-legend-bar {
  width: 120px;
  height: 8px;
  border-radius: 4px;
}
</style>
