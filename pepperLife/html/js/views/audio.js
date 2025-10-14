import { api } from '../api.js';

const template = `
  <style>
    .direct-controls .control-group { margin-bottom: 1.5rem; }
    .direct-controls .control-group label { display: block; margin-bottom: 0.5rem; font-size: 0.9em; color: #555; }
    .direct-controls .input-group { display: flex; gap: 8px; }
    .direct-controls .input-group input { flex-grow: 1; }
    .direct-controls .vu-meter-bar { background: #eee; border-radius: 4px; height: 25px; overflow: hidden; }
    .direct-controls #vu-meter-level { background: #4caf50; height: 100%; width: 0%; transition: width 0.1s linear; }
    .direct-controls .btn.on { border-color: #1e6b2d; background-color: #28a745; color: white; }
    .direct-controls .btn.off { border-color: #e02727; background-color: #dc3545; color: white; }
    .direct-controls .btn i { margin-right: 8px; }
  </style>
  <div class="card direct-controls">
    <div class="title">Contrôles Audio & Langue</div>

    <div class="control-group">
        <label>Microphone</label>
        <button class="btn" id="mic-toggle-btn">
            <i class="bi bi-mic-slash"></i>
            <span>Chargement...</span>
        </button>
    </div>
    <hr style="border: none; border-top: 1px solid #eee; margin: 1.5rem 0;">

    <div class="control-group">
        <label for="lang">Langue du robot (TTS)</label>
        <div class="input-group">
            <select id="lang" style="width: 100%;">
                <option>Chargement...</option>
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
let micStatusPoller = null;

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

async function updateMicStatus() {
    const micToggleBtn = document.getElementById('mic-toggle-btn');
    if (!micToggleBtn) return;

    try {
        const data = await api.micStatus();
        if (data && typeof data.enabled !== 'undefined') {
            const micIcon = micToggleBtn.querySelector('i');
            const micLabel = micToggleBtn.querySelector('span');
            if (data.enabled) {
                micIcon.className = 'bi bi-mic-fill';
                micLabel.textContent = ' Micro ON';
                micToggleBtn.classList.add('on');
                micToggleBtn.classList.remove('off');
            } else {
                micIcon.className = 'bi bi-mic-mute-fill';
                micLabel.textContent = ' Micro OFF';
                micToggleBtn.classList.add('off');
                micToggleBtn.classList.remove('on');
            }
        }
    } catch (e) {
        console.warn("Could not get mic status:", e);
    }
}

export function render(root) {
  root.innerHTML = template;
  init();
}

export function init() {

  const speakBtn = document.getElementById('speak-btn');

  const speakInput = document.getElementById('speak-input');

  const volumeSlider = document.getElementById('volume-slider');

  const langSelect = document.getElementById('lang');

  const saveLangBtn = document.getElementById('save-lang');

  const feedbackLang = document.getElementById('feedback-lang');

  const micToggleBtn = document.getElementById('mic-toggle-btn');

  const micIcon = micToggleBtn.querySelector('i');

  const micLabel = micToggleBtn.querySelector('span');



  let currentConfig = {};



  // --- Mic Toggle Logic ---

  micToggleBtn.addEventListener('click', async () => {

    micLabel.textContent = ' ...';

    micIcon.className = 'bi';

    try {

        const data = await api.micToggle();

        if (data && typeof data.enabled !== 'undefined') {

            updateMicStatus(); // Update UI based on new state

        }

    } catch (e) {

        console.error("Mic toggle failed:", e);

        micLabel.textContent = ' Erreur';

    }

  });



  // --- Language Logic ---

  const loadAndPopulateLanguages = async () => {

    try {

      feedbackLang.textContent = 'Chargement...';

      const data = await api.getTtsLanguages();

      

      if (data.error) {

        throw new Error(data.error);

      }



      langSelect.innerHTML = ''; // Clear options

      

      data.available.forEach(lang => {

          const option = document.createElement('option');

          option.value = lang;

          option.textContent = lang;

          langSelect.appendChild(option);

      });

      

      if (data && data.current) {

        langSelect.value = data.current;

      }

      feedbackLang.textContent = '';

    } catch(e) {

      feedbackLang.textContent = e.message || 'Erreur de chargement';

      langSelect.innerHTML = '<option>Erreur</option>';

    }

  };



  saveLangBtn.addEventListener('click', async () => {

    const newLang = langSelect.value;

    feedbackLang.textContent = 'Enregistrement...';

    try {

      await api.setTtsLanguage(newLang);

      feedbackLang.textContent = 'Enregistré !';

      setTimeout(() => feedbackLang.textContent = '', 2000);

    } catch(e) {

      feedbackLang.textContent = `Erreur: ${e.message}`;

    }

  });



  // --- Speak Logic ---

  const doSpeak = async () => {

    let text = speakInput.value;

    if (!text) return;



    if (currentConfig.audio?.add_wait_tag) {

      text += " ^wait()";

    }



    try {

      await api.speak(text);

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

  const loadConfig = async () => {

      try {

          currentConfig = await api.configGetUser();

      } catch (e) {

          console.warn("Could not load user config:", e);

          currentConfig = {}; // Fallback to empty config

      }

  };



  loadConfig();

  loadAndPopulateLanguages();

  updateMicStatus(); // Initial call



  api.volumeState().then(data => { 

    if (data.error) {

      console.warn("Impossible de récupérer l'état du volume:", data.error);

    } else if(volumeSlider) {

      volumeSlider.value = data.volume; 

    }

  }).catch(e => {

    console.warn("L'appel à volumeState a échoué:", e.message);

  });



  if (!vuMeterPoller) {

    vuMeterPoller = setInterval(updateVuMeter, 200);

  }

  if (!micStatusPoller) {

    micStatusPoller = setInterval(updateMicStatus, 2000);

  }

}

export function cleanup() {
  if (vuMeterPoller) {
    clearInterval(vuMeterPoller);
    vuMeterPoller = null;
  }
  if (micStatusPoller) {
    clearInterval(micStatusPoller);
    micStatusPoller = null;
  }
}