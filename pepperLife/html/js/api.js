const API_BASE = (() => {
    const hostname = window.location.hostname;
    // Si le nom d'hôte est localhost ou 127.0.0.1, on est probablement sur la tablette.
    // On doit utiliser l'IP spéciale que la tablette utilise pour voir le robot.
    if (hostname === '127.0.0.1' || hostname === 'localhost') {
        return 'http://198.18.0.1:8088';
    }
    // Sinon, on est sur un PC externe, on utilise l'IP du robot visible depuis le réseau.
    return 'http://' + hostname + ':8088';
})();

async function jget(url){ const r = await fetch(API_BASE + url, {cache:'no-store'}); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function jpost(url, data){ const r = await fetch(API_BASE + url,{ method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data||{})}); if(!r.ok) throw new Error(await r.text()); return r.json().catch(async()=>({text: await r.text()})); }

export const api = {
  getVersion: ()=> fetch(API_BASE + '/api/version').then(r => r.text()),
  speak: (text)=> jpost('/api/speak',{text:text}),
  heartbeat: ()=> jget('/api/heartbeat'),
  systemInfo: ()=> jget('/api/system/info'),
  restartRobot: () => jpost('/api/system/restart'),
  shutdownRobot: () => jpost('/api/system/shutdown'),
  systemStatus: ()=> jget('/api/system/status'),
  cameraStartStream: () => jpost('/api/camera/start_stream'),
  cameraStopStream: () => jpost('/api/camera/stop_stream'),
  soundLevel: ()=> jget('/api/sound_level'),
  volumeState: ()=> jget('/api/volume/state'),
  volumeSet: (v)=> jpost('/api/volume/set',{volume:v}),
  micToggle: ()=> jget('/api/mic_toggle'),
  lifeState: ()=> jget('/api/autonomous_life/state'),
  lifeToggle: ()=> jpost('/api/autonomous_life/toggle'),
  postureState: ()=> jget('/api/posture/state'),
  postureToggle: ()=> jpost('/api/posture/toggle'),
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
  configGetDefault: ()=> fetch(API_BASE + '/api/config/default').then(r => r.text()),
  configGetUser: ()=> jget('/api/config/user'),
  configSetUser: (data)=> jpost('/api/config/user', data),
  logsTail: (n)=> jget('/api/logs/tail?n='+(n||200)),
  // Chat API
  getChatStatus: () => jget('/api/chat/status'),
  startChat: (mode) => jpost('/api/chat/start', { mode: mode }),
  stopChat: () => jpost('/api/chat/stop'),
};