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

function tryParseJson(text) {
    if (!text) {
        return null;
    }
    try {
        return JSON.parse(text);
    } catch (_) {
        return null;
    }
}

async function buildHttpError(response) {
    const raw = await response.text();
    let message = raw || `HTTP error ${response.status}`;
    const payload = tryParseJson(raw);
    if (payload && typeof payload.error === 'string') {
        message = payload.error;
    }
    const error = new Error(message);
    error.status = response.status;
    if (payload) {
        error.payload = payload;
        if (payload.store_agent_unreachable) {
            error.storeAgentUnreachable = true;
        }
    }
    return error;
}

async function jget(url) {
    const r = await fetch(API_BASE + url, {cache: 'no-store'});
    if (!r.ok) {
        throw await buildHttpError(r);
    }
    const data = await r.json();
    if (data.error) {
        const err = new Error(data.error);
        err.payload = data;
        if (data.store_agent_unreachable) {
            err.storeAgentUnreachable = true;
        }
        throw err;
    }
    return data;
}
async function jpost(url, data) {
    const r = await fetch(API_BASE + url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data || {})
    });

    if (!r.ok) {
        throw await buildHttpError(r);
    }

    // Vérifier si la réponse est bien du JSON avant de la parser
    const contentType = r.headers.get("content-type");
    if (contentType && contentType.indexOf("application/json") !== -1) {
        return r.json();
    } else {
        return { text: await r.text() };
    }
}

export const api = {
  getVersion: ()=> fetch(API_BASE + '/api/version').then(r => r.text()),
  speak: (text)=> jpost('/api/speak',{text:text}),
  heartbeat: ()=> jget('/api/heartbeat'),
  systemInfo: ()=> jget('/api/system/info'),
  clearSystemLogs: () => jpost('/api/system/clear_logs'),
  systemStatus: ()=> jget('/api/system/status'),
  cameraStartStream: () => jpost('/api/camera/start_stream'),
  cameraStopStream: () => jpost('/api/camera/stop_stream'),
  cameraStatus: () => jget('/api/camera/status'),
  cameraSwitch: (data) => jpost('/api/camera/switch', data),
  soundLevel: ()=> jget('/api/sound_level'),
  volumeState: ()=> jget('/api/volume/state'),
  volumeSet: (v)=> jpost('/api/volume/set',{volume:v}),
  micToggle: ()=> jget('/api/mic_toggle'),
  micStatus: ()=> jget('/api/mic/status'),
  lifeState: ()=> jget('/api/autonomous_life/state'),
  lifeSetState: (st)=> jpost('/api/autonomous_life/set_state', {state: st}),
  postureState: ()=> jget('/api/posture/state'),
  postureSetState: (st)=> jpost('/api/posture/set_state', {state: st}),
  wifiScan: ()=> jget('/api/wifi/scan'),
  wifiConnect: (ssid, psk)=> jpost('/api/wifi/connect',{ssid, psk}),
  wifiStatus: ()=> jget('/api/wifi/status'),
  appsList: ()=> jget('/api/apps/list'),
  appStart: (name)=> jpost('/api/apps/start',{name}),
  appStop: (name)=> jpost('/api/apps/stop',{name}),
  choreoState: ()=> jget('/api/choreo/state'),
  choreoAddProgram: (payload)=> jpost('/api/choreo/programs/add', payload),
  choreoRemoveProgram: (programId)=> jpost('/api/choreo/programs/remove',{program_id: programId}),
  choreoSelectRobots: (robotIds)=> jpost('/api/choreo/robots/select',{robot_ids: robotIds}),
  choreoStart: (metadata)=> jpost('/api/choreo/start',{metadata: metadata || {}}),
  choreoConnect: ()=> jpost('/api/choreo/connect',{}),
  choreoDisconnect: ()=> jpost('/api/choreo/disconnect',{}),
  choreoResetRemote: ()=> jpost('/api/choreo/reset_remote',{}),
  memorySearch: (pattern)=> jget('/api/memory/search?pattern='+encodeURIComponent(pattern||'')),
  memoryGet: (key)=> jget('/api/memory/get?key='+encodeURIComponent(key)),
  memorySet: (key, value)=> jpost('/api/memory/set',{key, value}),
  hardwareInfo: ()=> jget('/api/hardware/info'),
  hardwareDetails: ()=> jget('/api/hardware/details'),
  motionJoints: ()=> jget('/api/motion/joints'),
  settingsGet: ()=> jget('/api/settings/get'),
  settingsSet: (patch)=> jpost('/api/settings/set', patch),
  configGetDefault: ()=> fetch(API_BASE + '/api/config/default').then(r => r.text()),
  configGetUser: ()=> jget('/api/config/user'),
  configSetUser: (data)=> jpost('/api/config/user', data),
  configReload: ()=> jpost('/api/config/reload', {}),
  logsTail: (n)=> jget('/api/logs/tail?n='+(n||200)),
  // Chat API
  getChatStatus: () => jget('/api/chat/status'),
  getDetailedChatStatus: () => jget('/api/chat/detailed_status'),
  startChat: (mode) => jpost('/api/chat/start', { mode: mode }),
  stopChat: () => jpost('/api/chat/stop'),
  chatSend: (payload) => jpost('/api/chat/send', payload),
  chatSendStream: async (payload, { onChunk } = {}) => {
    const requestPayload = Object.assign({}, payload, { debug_stream: true });
    const response = await fetch(API_BASE + '/api/chat/send', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/x-ndjson',
        'X-Debug-Stream': '1'
      },
      body: JSON.stringify(requestPayload || {})
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `HTTP error ${response.status}`);
    }

    const events = [];
    const notify = (event) => {
      events.push(event);
      if (typeof onChunk === 'function') {
        try {
          onChunk(event);
        } catch (err) {
          console.warn('chatSendStream onChunk error', err);
        }
      }
    };

    let finalResult = null;

    if (!response.body || typeof response.body.getReader !== 'function') {
      const data = await response.json();
      const event = { type: 'result', result: data };
      notify(event);
      return { result: data, events };
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          let newlineIndex;
          while ((newlineIndex = buffer.indexOf('\n')) !== -1) {
            const line = buffer.slice(0, newlineIndex).trim();
            buffer = buffer.slice(newlineIndex + 1);
            if (!line) {
              continue;
            }
            let event;
            try {
              event = JSON.parse(line);
            } catch (_) {
              continue;
            }
            notify(event);
            if (event.type === 'result') {
              finalResult = event.result;
            } else if (event.type === 'error') {
              const err = new Error(event.error || 'Erreur de streaming.');
              err.streamEvents = events;
              throw err;
            }
          }
        }
        if (done) {
          break;
        }
      }
      buffer += decoder.decode();
      const trimmed = buffer.trim();
      if (trimmed) {
        try {
          const event = JSON.parse(trimmed);
          notify(event);
          if (event.type === 'result') {
            finalResult = event.result;
          } else if (event.type === 'error') {
            const err = new Error(event.error || 'Erreur de streaming.');
            err.streamEvents = events;
            throw err;
          }
        } catch (_) {
          // Ignore trailing parse errors
        }
      }
    } finally {
      reader.releaseLock();
    }

    if (!finalResult && events.length > 0) {
      const lastEvent = events[events.length - 1];
      if (lastEvent.type === 'result') {
        finalResult = lastEvent.result;
      }
    }

    return { result: finalResult, events };
  },
  getSystemPrompt: (provider) => {
    const suffix = provider ? ('?provider=' + encodeURIComponent(provider)) : '';
    return jget('/api/system_prompt' + suffix);
  },
  setSystemPrompt: (content, provider) => {
    const suffix = provider ? ('?provider=' + encodeURIComponent(provider)) : '';
    return jpost('/api/system_prompt' + suffix, { content: content });
  },
  probeOllama: (server) => jget('/api/ollama/probe?server=' + encodeURIComponent(server || '')),
  probeStt: (server, health) => jget('/api/stt/probe?server=' + encodeURIComponent(server || '') + (health ? '&health=' + encodeURIComponent(health) : '')),
  // TTS Language
  getTtsLanguages: () => jget('/api/tts/languages'),
  setTtsLanguage: (lang) => jpost('/api/tts/set_language', { lang }),
  storeGetInfo: () => jget('/api/store/info'),
  storeStatus: () => jget('/api/store/status'),
  storeTestConnection: ({server, username, password} = {}) => jpost('/api/store/test_connection', {server, username, password}),
  storeSave: ({server, email, password} = {}) => jpost('/api/store/save', {server, email, password}),
  storeLogout: () => jpost('/api/store/logout', {}),
  // Generic getter for new endpoints
  get: (url) => jget(url),
};
