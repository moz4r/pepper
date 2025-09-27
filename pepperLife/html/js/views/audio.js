import { api } from '../api.js';

const template = `
  <style>
    .direct-controls .control-group { margin-bottom: 1.5rem; }
    .direct-controls .control-group label { display: block; margin-bottom: 0.5rem; font-size: 0.9em; color: #555; }
    .direct-controls .input-group { display: flex; gap: 8px; }
    .direct-controls .input-group input { flex-grow: 1; }
    .direct-controls .vu-meter-bar { background: #eee; border-radius: 4px; height: 25px; overflow: hidden; }
    .direct-controls #vu-meter-level { background: #4caf50; height: 100%; width: 0%; transition: width 0.1s linear; }
  </style>
  <div class="card direct-controls">
    <div class="title">Contrôles Audio & Langue</div>
    <div class="control-group">
        <label for="lang">Langue du robot (TTS)</label>
        <div class="input-group">
            <select id="lang" style="width: 100%;">
                <option value="French">Français</option>
                <option value="English">Anglais</option>
            </select>
            <button class="btn" id="save-lang">Appliquer</button>
        </div>
        <span id="feedback-lang" style="font-size: 0.8em; margin-left: 4px;"></span>
    </div>
    <hr style="border: none; border-top: 1px solid #eee; margin: 1.5rem 0;">
    <div class="control-group">
        <label for="speak-input">Faire parler</label>
        <div class="input-group">
            <input type="text" id="speak-input" placeholder="Texte à dire...">
            <button id="speak-btn" class="btn">Parler</button>
        </div>
    </div>
    <div class="control-group">
        <label for="volume-slider">Volume</label>
        <input type="range" id="volume-slider" min="0" max="100" style="width: 100%;">
    </div>
    <div class="control-group">
        <label>Niveau sonore (écoute)</label>
        <div class="vu-meter-bar"><div id="vu-meter-level"></div></div>
    </div>
  </div>
`;

let vuMeterPoller = null;

async function updateVuMeter() {
    try {
        const data = await api.soundLevel();
        const level = Math.min(100, (data.level || 0) / 50);
        const vuLevel = document.getElementById('vu-meter-level');
        if(vuLevel) vuLevel.style.width = `${level}%`;
    } catch (e) {
        // Ignore errors if backend is not running
    }
}

export function render(root) {
  root.innerHTML = template;
}

export function init() {
  const speakBtn = document.getElementById('speak-btn');
  const speakInput = document.getElementById('speak-input');
  const volumeSlider = document.getElementById('volume-slider');
  const langSelect = document.getElementById('lang');
  const saveLangBtn = document.getElementById('save-lang');
  const feedbackLang = document.getElementById('feedback-lang');

  // --- Language Logic ---
  const loadLang = async () => {
    try {
      const settings = await api.settingsGet();
      if (settings && settings.language) {
        langSelect.value = settings.language;
      }
    } catch(e) {
      feedbackLang.textContent = `Erreur chargement`;
    }
  };

  saveLangBtn.addEventListener('click', async () => {
    const newLang = langSelect.value;
    feedbackLang.textContent = 'Enregistrement...';
    try {
      await api.settingsSet({language: newLang});
      feedbackLang.textContent = 'Enregistré !';
      setTimeout(() => feedbackLang.textContent = '', 2000);
    } catch(e) {
      feedbackLang.textContent = `Erreur: ${e.message}`;
    }
  });

  // --- Speak Logic ---
  const doSpeak = async () => {
    if (!speakInput.value) return;
    try {
      await api.speak(speakInput.value);
    } catch (e) {
      console.error("Speak API failed:", e);
      alert("L'API pour parler a échoué: " + e.message);
    }
  };

  speakBtn.addEventListener('click', doSpeak);
  speakInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') doSpeak();
  });

  // --- Volume Logic ---
  volumeSlider.addEventListener('input', async () => {
    try {
      await api.volumeSet(parseInt(volumeSlider.value, 10));
    } catch (e) {
      console.error("Volume API failed:", e);
    }
  });

  // --- Initial State & Pollers ---
  loadLang();
  api.volumeState().then(data => { 
    if(volumeSlider) volumeSlider.value = data.volume; 
  }).catch(()=>{});

  if (!vuMeterPoller) {
    vuMeterPoller = setInterval(updateVuMeter, 200);
  }
}

export function cleanup() {
  if (vuMeterPoller) {
    clearInterval(vuMeterPoller);
    vuMeterPoller = null;
  }
}
