// Access to the host through the registry captured in main.ts: the plugin
// http client, the theme and the address of plugin websockets.
import type { PluginHttpClient } from '@nginxui/plugin-sdk'
import { requireRegistry } from './runtime'

/**
 * The plugin http client. Each request names the language of the host, so the
 * backend answers place names in it rather than in the browser's language.
 */
export function getHttp(): PluginHttpClient {
  const { http, host } = requireRegistry()
  const withLanguage = (config?: Record<string, unknown>): Record<string, unknown> => {
    // A host without a locale, like the one the tests set up, sends none
    const locale = host?.locale
    if (!locale)
      return config ?? {}
    return { ...config, headers: { ...(config?.headers as Record<string, string> | undefined), 'X-Language': locale } }
  }
  return {
    get: (url, config) => http.get(url, withLanguage(config)),
    post: (url, data, config) => http.post(url, data, withLanguage(config)),
    put: (url, data, config) => http.put(url, data, withLanguage(config)),
    patch: (url, data, config) => http.patch(url, data, withLanguage(config)),
    delete: (url, config) => http.delete(url, withLanguage(config)),
    request: config => http.request(withLanguage(config)),
  }
}

export function getTheme(): 'light' | 'dark' {
  return requireRegistry().host.theme
}

export function getLocale(): string {
  return requireRegistry().host.locale
}

/**
 * Opens a websocket to a path of the plugin backend. The host builds the
 * address, because only it knows how a browser websocket authenticates.
 */
export async function openPluginSocket(path: string): Promise<WebSocket> {
  const { wsUrl } = requireRegistry()
  if (!wsUrl)
    throw new Error('[log-analytics] this host cannot open plugin websockets')

  return new WebSocket(wsUrl(path))
}
