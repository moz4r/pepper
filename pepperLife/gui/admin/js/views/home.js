import {api} from '../api.js';

export function render(root) {
  const el = document.createElement('div');
  el.innerHTML = `
    <style>
      .top-card { grid-column: span 12; }
      .image-panel { 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        background: transparent; /* Fond transparent */
      }
      .image-panel img {
        max-width: 80%;
        height: auto;
        max-height: 350px;
      }
      .speak-row { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
      .speak-row input { flex: 1; }
    </style>

    <div class="grid">
      <!-- Audio Card -->
      <div class="card top-card">
        <div class="title">Audio & Parole</div>
        <div class="speak-row">
          <input type="text" id="speak-text" placeholder="Texte à dire...">
          <button class="btn" id="speak-btn">Parler</button>
        </div>
        <div class="row"><label for="vol">Volume</label><input id="vol" type="range" min="0" max="100"/><span class="chip" id="volv">…</span><button class="btn" id="setv">Appliquer</button></div>
        <div class="row"><div class="meter"><i id="snd"></i></div><button class="btn" id="sndt">Start Vumètre</button></div>
      </div>

      <!-- System Info -->
      <div class="card span-6">
        <div class="title">Système</div>
        <div class="kvs" id="kvs"></div>
      </div>

      <!-- Pepper Image -->
      <div class="card span-6 image-panel">
        <img src="./img/pepper.png" alt="Pepper Robot">
      </div>
    </div>
  `;
  root.appendChild(el);

  // --- Logic --- 
  const kvs = el.querySelector('#kvs');

  // Initial data load
  (async () => {
    try {
      const d = await api.systemInfo();
      const battery = d.battery || {};
      const info = [
        ['NAOqi', d.naoqi_version || '?'],
        ['IPs', (d.ip_addresses || []).join(', ') || '—'],
        ['Internet', d.internet_connected ? 'OK' : 'KO'],
        ['Batterie', `${battery.charge || '?'}% ${battery.plugged ? '(en charge)' : ''}`]
      ];
      kvs.innerHTML = info.map(([k, v]) => `<div class="kv"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');
    } catch (e) {
      kvs.innerHTML = `<div class="kv"><div class="k">Erreur</div><div class="v">Impossible de charger les informations système.</div></div>`;
    }
    try {
      const d = await api.volumeState();
      el.querySelector('#vol').value = d.volume;
      el.querySelector('#volv').textContent = d.volume + '%';
    } catch (e) {}
  })();

  // Speak button
  el.querySelector('#speak-btn').addEventListener('click', async () => {
    const text = el.querySelector('#speak-text').value;
    if (!text) return;
    try {
      await api.speak(text);
    } catch (e) {
      alert(e.message || e);
    }
  });

  // Volume controls
  el.querySelector('#vol').addEventListener('input', e => el.querySelector('#volv').textContent = e.target.value + '%');
  el.querySelector('#setv').addEventListener('click', async () => {
    try {
      await api.volumeSet(parseInt(el.querySelector('#vol').value, 10));
      const d = await api.volumeState();
      el.querySelector('#volv').textContent = d.volume + '%';
    } catch (e) {
      alert(e.message || e);
    }
  });

  // VU Meter
  let sndOn = false, timer = null;
  async function step() {
    if (!sndOn || !el.isConnected) return;
    try {
      const d = await api.soundLevel();
      const v = Math.max(0, Math.min(100, Math.round((d.level || 0) / 3)));
      el.querySelector('#snd').style.width = v + '%';
    } catch (e) {}
    timer = setTimeout(step, 120);
  }
  el.querySelector('#sndt').addEventListener('click', () => {
    sndOn = !sndOn;
    el.querySelector('#sndt').textContent = sndOn ? 'Stop' : 'Start';
    if (sndOn) step();
    else {
      if (timer) clearTimeout(timer);
      el.querySelector('#snd').style.width = '0%';
    }
  });
}