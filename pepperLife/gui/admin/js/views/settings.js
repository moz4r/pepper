
import {api} from '../api.js';
export function render(root){
  const el = document.createElement('section'); el.className='card span-12';
  el.innerHTML = `<div class="title">Réglages</div>
    <div class="row">
        <label for="lang">Langue du robot (TTS)</label>
        <select id="lang">
            <option value="French">Français</option>
            <option value="English">Anglais</option>
            <!-- D'autres langues peuvent être ajoutées ici -->
        </select>
        <button class="btn" id="save">Appliquer</button>
        <span id="feedback" style="margin-left: 10px;"></span>
    </div>`;
  root.appendChild(el);

  const langSelect = el.querySelector('#lang');
  const saveButton = el.querySelector('#save');
  const feedback = el.querySelector('#feedback');

  async function loadSettings() {
    try {
      const settings = await api.settingsGet();
      if (settings && settings.language) {
        langSelect.value = settings.language;
      }
    } catch(e) {
      feedback.textContent = `Erreur: ${e.message || e}`;
      feedback.style.color = 'red';
    }
  }

  saveButton.addEventListener('click', async()=>{
    const newLang = langSelect.value;
    feedback.textContent = 'Enregistrement...';
    feedback.style.color = 'inherit';
    try {
      await api.settingsSet({language: newLang});
      feedback.textContent = 'Enregistré !';
      setTimeout(() => feedback.textContent = '', 2000);
    } catch(e) {
      feedback.textContent = `Erreur: ${e.message || e}`;
      feedback.style.color = 'red';
    }
  });

  // Charger les réglages initiaux
  loadSettings();
}
