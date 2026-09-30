// The plugins this webapp is built for. PLUGIN_ID picks the plugin of one
// build, OUT_DIR where it goes. Without them the build is the one of the first
// plugin in dist/.
export const PLUGIN_IDS = ['com.nginxui.log-analytics', 'com.nginxui.log-analytics-tantivy']

/** The plugin id of a build, checked against the known plugins. */
export function pluginIdOf(value: string | undefined): string {
  const id = value?.trim() || PLUGIN_IDS[0]
  if (!PLUGIN_IDS.includes(id))
    throw new Error(`unknown plugin id ${id}, expected one of ${PLUGIN_IDS.join(', ')}`)
  return id
}

export const PLUGIN_ID = pluginIdOf(process.env.PLUGIN_ID)
export const OUT_DIR = process.env.OUT_DIR?.trim() || 'dist'
