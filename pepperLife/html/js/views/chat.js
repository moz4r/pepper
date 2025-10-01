export function render(root, api) {
    const template = `
    <style>
      .chat-container { max-width: 800px; margin: auto; }
      .status-bar { display: flex; align-items: center; gap: 1rem; padding: 0.5rem; background: #f5f5f5; border-radius: 8px; margin-bottom: 1.5rem; color: #333; }
      .status-bar .status { font-weight: bold; color: #333; }
      .status-bar .filler { flex-grow: 1; }
      .options-grid { display: grid; grid-template-columns: 1fr; gap: 1.5rem; }
      .chat-option .title { font-size: 1.2em; font-weight: bold; margin-bottom: 0.5rem; }
      .chat-option .description { margin-bottom: 1rem; font-size: 0.95em; }
      .chat-option .settings { border-left: 3px solid #007bff; padding-left: 1rem; margin-top: 1rem; }
      .hidden { display: none; }
      .form-group { margin-bottom: 1rem; }
      .form-group label { display: block; margin-bottom: 0.25rem; font-weight: 500; }
      .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
      .form-group textarea { min-height: 120px; font-family: monospace; }
    </style>
    <div class="chat-container">
        <h2><i class="bi bi-sliders"></i> Configuration du Chatbot</h2>

        <div class="status-bar">
            <strong>État actuel :</strong> <span id="current-chat-status" class="status">INCONNU</span>
            <div class="filler"></div>
            <button id="main-chat-btn" class="btn"><i class="bi bi-power"></i> Activer</button>
        </div>

        <div class="options-grid">
            <div class="card chat-option">
                <div class="title"><input type="radio" name="chat_mode" value="basic" id="mode-basic"> <label for="mode-basic">Basic Channel</label></div>
                <p class="description">Le robot écoute les commandes locales simples, sans IA externe. Utile pour le débogage.</p>
            </div>

            <div class="card chat-option">
                <div class="title"><input type="radio" name="chat_mode" value="gpt" id="mode-gpt"> <label for="mode-gpt">ChatGPT (OpenAI)</label></div>
                <p class="description">Active le chatbot complet avec l'intelligence artificielle d'OpenAI.</p>
                <div id="gpt-settings" class="settings hidden">
                    <h4>Paramètres OpenAI</h4>
                    <div class="form-group">
                        <label for="gpt-api-key">Clé API OpenAI</label>
                        <input type="password" id="gpt-api-key" placeholder="sk-...">
                    </div>
                    <div class="form-group">
                        <label for="gpt-model">Modèle</label>
                        <select id="gpt-model">
                            <option value="gpt-4o-mini">gpt-4o-mini</option>
                            <option value="gpt-4o">gpt-4o</option>
                            <option value="gpt-5-mini">gpt-5-mini</option>
                            <option value="gpt-5">gpt-5</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="gpt-prompt">Custom Prompt</label>
                        <textarea id="gpt-prompt"></textarea>
                    </div>
                    <button id="save-gpt-settings" class="btn">Enregistrer les paramètres</button>
                </div>
            </div>

            <div class="card chat-option" style="opacity: 0.6;">
                <div class="title"><input type="radio" name="chat_mode" value="ollama" id="mode-ollama" disabled> <label for="mode-ollama">Ollama Distant</label></div>
                <p class="description">Utilise une instance d'Ollama sur le réseau local pour le chat. (Fonctionnalité à venir)</p>
            </div>
        </div>
    </div>
    `;
    root.innerHTML = template;
    init(api);
}

function init(api) {
    const mainChatBtn = document.getElementById('main-chat-btn');
    const statusEl = document.getElementById('current-chat-status');
    const gptSettings = document.getElementById('gpt-settings');
    const saveGptBtn = document.getElementById('save-gpt-settings');

    const apiKeyInput = document.getElementById('gpt-api-key');
    const modelSelect = document.getElementById('gpt-model');
    const promptTextarea = document.getElementById('gpt-prompt');

    let currentConfig = {};
    let currentStatus = {};

    function updateMainButton(status) {
        mainChatBtn.disabled = false;
        if (status.is_running) {
            mainChatBtn.innerHTML = `<i class="bi bi-stop-circle-fill"></i> Arrêter le Chat`;
            mainChatBtn.classList.add('btn-danger');
            mainChatBtn.classList.remove('btn-success');
        } else {
            mainChatBtn.innerHTML = `<i class="bi bi-play-circle-fill"></i> Activer le Chat`;
            mainChatBtn.classList.add('btn-success');
            mainChatBtn.classList.remove('btn-danger');
        }
    }

    function updateStatus(status) {
        currentStatus = status;
        statusEl.textContent = status.is_running ? `Actif (${status.mode})` : 'Arrêté';
        document.getElementById(`mode-${status.mode || 'basic'}`).checked = true;
        if (status.mode === 'gpt') {
            gptSettings.classList.remove('hidden');
        } else {
            gptSettings.classList.add('hidden');
        }
        updateMainButton(status);
    }

    function loadConfig() {
        return api.configGetUser().then(config => {
            currentConfig = config;
            apiKeyInput.value = config.openai?.api_key || '';
            modelSelect.value = config.openai?.chat_model || 'gpt-4o-mini';
            promptTextarea.value = config.openai?.custom_prompt || '';
        });
    }

    function getStatus() {
        return api.getChatStatus().then(updateStatus);
    }

    // Event Listeners
    document.querySelectorAll('input[name="chat_mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.value === 'gpt') {
                gptSettings.classList.remove('hidden');
            } else {
                gptSettings.classList.add('hidden');
            }
        });
    });

    saveGptBtn.addEventListener('click', () => {
        saveGptBtn.textContent = 'Enregistrement...';
        saveGptBtn.disabled = true;
        const newConfig = {
            ...currentConfig,
            openai: {
                ...currentConfig.openai,
                api_key: apiKeyInput.value,
                chat_model: modelSelect.value,
                custom_prompt: promptTextarea.value
            }
        };
        api.configSetUser(newConfig).then(() => {
            currentConfig = newConfig;
            if (currentStatus.is_running && currentStatus.mode === 'gpt') {
                if (confirm("Paramètres enregistrés. Le chat GPT est en cours d'exécution. Voulez-vous le redémarrer maintenant pour appliquer les nouveaux paramètres ?")) {
                    // Restart the chat
                    mainChatBtn.disabled = true;
                    mainChatBtn.innerHTML = '...';
                    api.stopChat().then(() => {
                        api.startChat('gpt').then(getStatus);
                    });
                }
            } else {
                alert('Paramètres enregistrés. Ils seront utilisés au prochain démarrage du chat GPT.');
            }
        }).catch(err => {
            alert(`Erreur lors de l'enregistrement : ${err.message}`);
        }).finally(() => {
            saveGptBtn.textContent = 'Enregistrer les paramètres';
            saveGptBtn.disabled = false;
        });
    });

    mainChatBtn.addEventListener('click', () => {
        mainChatBtn.disabled = true;
        mainChatBtn.innerHTML = '...';

        if (currentStatus.is_running) {
            api.stopChat().then(getStatus).catch(err => {
                alert(`Erreur à l'arrêt: ${err.message}`);
                getStatus(); // Refresh status anyway
            });
        } else {
            const selectedMode = document.querySelector('input[name="chat_mode"]:checked').value;
            api.startChat(selectedMode).then(getStatus).catch(err => {
                alert(`Erreur au démarrage: ${err.message}`);
                getStatus(); // Refresh status anyway
            });
        }
    });

    // Initial Load
    Promise.all([
        loadConfig(),
        getStatus()
    ]).catch(err => {
        statusEl.textContent = 'Erreur de chargement';
        console.error("Error during initial load:", err);
    });
}