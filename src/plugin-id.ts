// The id of the plugin the bundle was built for. The build defines it, see
// build.constants.ts; code run without a build, like the tests, gets the first
// plugin.
declare const __PLUGIN_ID__: string | undefined

export const PLUGIN_ID: string = typeof __PLUGIN_ID__ === 'string' ? __PLUGIN_ID__ : 'com.nginxui.log-analytics'
