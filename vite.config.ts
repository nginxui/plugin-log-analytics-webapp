// Builds the entry bundle of the log analytics plugin: one IIFE plus
// style.css and manifest.webapp.json. The heavy views live in the chunks
// built by vite.search.config.ts and vite.dashboard.config.ts.
import type { Plugin } from 'vite'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { nginxUiPlugin } from '@nginxui/plugin-sdk/vite'
import vue from '@vitejs/plugin-vue'
import * as OpenCC from 'opencc-js'
import UnoCSS from 'unocss/vite'
import { defineConfig } from 'vite'
import { OUT_DIR, PLUGIN_ID } from './build.constants'

// Country name files of i18n-iso-countries, one per language the host offers.
// They ship as static files so a view only fetches the language it shows.
const COUNTRY_LANGUAGES = ['en', 'zh', 'fr', 'es', 'de', 'ru', 'vi', 'ko', 'tr', 'ar', 'uk', 'ja', 'pt', 'it']

// The package has no traditional Chinese names, zht.json converts the
// simplified ones to the characters and words used in Taiwan
const toTaiwan = OpenCC.Converter({ from: 'cn', to: 'twp' })
function traditional(value: unknown): unknown {
  if (typeof value === 'string')
    return toTaiwan(value)
  if (Array.isArray(value))
    return value.map(traditional)
  return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, traditional(item)]))
}

function countryNames(): Plugin {
  return {
    name: 'log-analytics-country-names',
    apply: 'build',
    generateBundle() {
      const read = (language: string) => JSON.parse(readFileSync(fileURLToPath(new URL(`./node_modules/i18n-iso-countries/langs/${language}.json`, import.meta.url)), 'utf8'))
      for (const language of COUNTRY_LANGUAGES) {
        this.emitFile({ type: 'asset', fileName: `assets/countries/${language}.json`, source: JSON.stringify(read(language)) })
      }
      const zh = read('zh') as { locale: string, countries: Record<string, unknown> }
      this.emitFile({
        type: 'asset',
        fileName: 'assets/countries/zht.json',
        source: JSON.stringify({ locale: 'zht', countries: traditional(zh.countries) }),
      })
    },
  }
}

export default defineConfig({
  plugins: [
    vue(),
    UnoCSS(),
    nginxUiPlugin({ id: PLUGIN_ID, chunks: ['search', 'dashboard'], outDir: OUT_DIR }),
    countryNames(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
    '__PLUGIN_ID__': JSON.stringify(PLUGIN_ID),
  },
})
