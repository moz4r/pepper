async function jget(url){ const r = await fetch(url, {cache:'no-store'}); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function jpost(url, data){ const r = await fetch(url,{ method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data||{})}); if(!r.ok) throw new Error(await r.text()); return r.json().catch(async()=>({text: await r.text()})); }

export const api = {
  speak: (text)=> jpost('/api/speak',{text:text}),
  getVersion: ()=> fetch('/api/version').then(r => r.text()),
  heartbeat: ()=> jget('/api/heartbeat'),
  systemInfo: ()=> jget('/api/system/info'),
  soundLevel: ()=> jget('/api/sound_level'),
  volumeState: ()=> jget('/api/volume/state'),
  volumeSet: (v)=> jpost('/api/volume/set',{volume:v}),
  micToggle: ()=> jget('/api/mic_toggle'),
  lifeState: ()=> jget('/api/autonomous_life/state'),
  lifeToggle: ()=> jget('/api/autonomous_life/toggle'),
  postureState: ()=> jget('/api/posture/state'),
  postureToggle: ()=> jget('/api/posture/toggle'),
  // Extended endpoints to implement in classWebServer (or proxy to qi):
  wifiScan: ()=> jget('/api/wifi/scan'),
  wifiConnect: (ssid, psk)=> jpost('/api/wifi/connect',{ssid, psk}),
  wifiStatus: ()=> jget('/api/wifi/status'),
  appsList: ()=> jget('/api/apps/list'),
  appStart: (name)=> jpost('/api/apps/start',{name}),
  appStop: (name)=> jpost('/api/apps/stop',{name}),
  memorySearch: (pattern)=> jget('/api/memory/search?pattern='+encodeURIComponent(pattern||'')),
  memoryGet: (key)=> jget('/api/memory/get?key='+encodeURIComponent(key)),
  memorySet: (key, value)=> jpost('/api/memory/set',{key, value}),
  hardwareInfo: ()=> jget('/api/hardware/info'),
  hardwareDetails: ()=> jget('/api/hardware/details'),
  settingsGet: ()=> jget('/api/settings/get'),
  settingsSet: (patch)=> jpost('/api/settings/set', patch),
  logsTail: (n)=> jget('/api/logs/tail?n='+(n||200)),
};
