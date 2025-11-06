

const template = `
  <style>
    .state-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }
    .control-group { margin-bottom: 1.5rem; }
    .control-group label { display: block; margin-bottom: 0.5rem; font-weight: bold; }
    .control-group .input-group { display: flex; gap: 8px; align-items: center;}
    .control-group select { flex-grow: 1; }
    .status-indicator {
        display: inline-block;
        padding: 0.25em 0.6em;
        font-size: 75%;
        font-weight: 700;
        line-height: 1;
        text-align: center;
        white-space: nowrap;
        vertical-align: baseline;
        border-radius: 0.25rem;
        color: #fff;
    }
    .status-indicator.ok { background-color: #28a745; }
    .status-indicator.off { background-color: #dc3545; }
    .status-indicator.warn { background-color: #ffc107; color: #000;}
  </style>
  <div class="card span-12">
    <div class="title">État du Robot</div>
    <div class="state-grid">
        <!-- Autonomous Life Section -->
        <div class="control-group">
            <label for="life-select">Vie Autonome</label>
            <div class="input-group">
                <select id="life-select"><option>Chargement...</option></select>
                <button class="btn" id="life-save-btn">Appliquer</button>
            </div>
            <p style="margin-top: 0.5rem;">État actuel: <span id="life-current-status" class="status-indicator">...</span></p>
        </div>

        <!-- Posture Section -->
        <div class="control-group">
            <label for="posture-select">Posture</label>
            <div class="input-group">
                <select id="posture-select">
                    <option value="awake">Debout</option>
                    <option value="rest">Au repos</option>
                </select>
                <button class="btn" id="posture-save-btn">Appliquer</button>
            </div>
            <p style="margin-top: 0.5rem;">État actuel: <span id="posture-current-status" class="status-indicator">...</span></p>
        </div>
    </div>
  </div>
`;

export function render(root, api){
  root.innerHTML = template;
  init(api);
}

export function init(api) {
  // --- Elements ---
  const lifeSelect = document.getElementById('life-select');
  const lifeSaveBtn = document.getElementById('life-save-btn');
  const lifeStatus = document.getElementById('life-current-status');
  
  const postureSelect = document.getElementById('posture-select');
  const postureSaveBtn = document.getElementById('posture-save-btn');
  const postureStatus = document.getElementById('posture-current-status');

  // --- Autonomous Life Logic ---
  async function refreshLife() {
    try {
      const data = await api.lifeState();
      if (data.error) throw new Error(data.error);
      
      // Populate dropdown if not already populated
      if (lifeSelect.options.length <= 1) {
        lifeSelect.innerHTML = '';
        data.all_states.forEach(state => {
          const option = document.createElement('option');
          option.value = state;
          option.textContent = state.charAt(0).toUpperCase() + state.slice(1);
          lifeSelect.appendChild(option);
        });
      }

      // Set current state
      lifeSelect.value = data.current_state;
      lifeStatus.textContent = data.current_state;
      lifeStatus.className = 'status-indicator'; // reset
      if (data.current_state === 'disabled') {
        lifeStatus.classList.add('off');
      } else if (data.current_state === 'interactive') {
        lifeStatus.classList.add('ok');
      } else {
        lifeStatus.classList.add('warn');
      }

    } catch (e) {
      if (e.message.includes('Failed to fetch')) {
        lifeStatus.textContent = 'Offline';
      } else {
        console.error("Erreur lors de la récupération de l'état de vie:", e);
        lifeStatus.textContent = 'Erreur';
      }
      lifeStatus.className = 'status-indicator off';
    }
  }

  lifeSaveBtn.addEventListener('click', async () => {
    const newState = lifeSelect.value;
    lifeSaveBtn.disabled = true;
    lifeSaveBtn.textContent = '...';
    try {
      await api.lifeSetState(newState);
      await refreshLife();
    } catch (e) {
      alert(`Erreur lors du changement d'état de vie: ${e.message || e}`);
    } finally {
      lifeSaveBtn.disabled = false;
      lifeSaveBtn.textContent = 'Appliquer';
    }
  });

  // --- Posture Logic ---
  async function refreshPosture() {
    try {
      const data = await api.postureState();
      if (data.error) throw new Error(data.error);
      const isAwake = data.is_awake;
      postureSelect.value = isAwake ? 'awake' : 'rest';
      postureStatus.textContent = isAwake ? 'Debout' : 'Au repos';
      postureStatus.className = 'status-indicator'; // reset
      postureStatus.classList.add(isAwake ? 'ok' : 'off');
    } catch (e) {
      if (e.message.includes('Failed to fetch')) {
        postureStatus.textContent = 'Offline';
      } else {
        console.error("Erreur lors de la récupération de la posture:", e);
        postureStatus.textContent = 'Erreur';
      }
      postureStatus.className = 'status-indicator off';
    }
  }

  postureSaveBtn.addEventListener('click', async () => {
    const newState = postureSelect.value;
    postureSaveBtn.disabled = true;
    postureSaveBtn.textContent = '...';
    try {
      await api.postureSetState(newState);
      await refreshPosture();
    } catch (e) {
      alert(`Erreur lors du changement de posture: ${e.message || e}`);
    } finally {
      postureSaveBtn.disabled = false;
      postureSaveBtn.textContent = 'Appliquer';
    }
  });

  // --- Initial Load ---
  refreshLife();
  refreshPosture();
}

export function cleanup() {
  // No timers or pollers to clean up in this view
}