export function render(root, api) {
    const template = `
    <style>
      .chat-container { max-width: 1000px; margin: auto; }
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
      .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
      .form-group textarea { min-height: 120px; font-family: monospace; }
      .settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
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
                    <div class="settings-grid">
                        <div id="gpt-settings-moteurs">
                            <h4>Moteurs</h4>
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
                                    <option value="gpt-5-nano">gpt-5-nano</option>
                                    <option value="gpt-5">gpt-5</option>
                                </select>
                            </div>
                            <div class="form-group" id="form-group-temperature">
                                <label for="gpt-temperature">Temperature</label>
                                <input type="number" step="0.1" min="0" max="2" id="gpt-temperature">
                            </div>
                            <div class="form-group" id="form-group-reasoning">
                                <label for="gpt-reasoning">Effort de raisonnement</label>
                                <select id="gpt-reasoning">
                                    <option value="minimal">minimal</option>
                                    <option value="low">low</option>
                                    <option value="medium">medium</option>
                                    <option value="high">high</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="gpt-verbosity">Verbosity</label>
                                <select id="gpt-verbosity">
                                    <option value="low">low</option>
                                    <option value="medium">medium</option>
                                    <option value="high">high</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="gpt-max-tokens">Max Tokens</label>
                                <input type="number" step="16" min="16" max="4096" id="gpt-max-tokens">
                            </div>
                            <div class="form-group">
                                <label for="gpt-history">Longueur de l'historique</label>
                                <input type="number" step="2" min="0" max="20" id="gpt-history">
                            </div>
                        </div>
                        <div id="gpt-settings-prompts">
                            <h4>Prompts</h4>
                            <div class="form-group">
                                <label for="gpt-prompt">Custom Prompt</label>
                                <textarea id="gpt-prompt"></textarea>
                            </div>
                            <div class="form-group">
                                <label for="system-prompt">System Prompt</label>
                                <textarea id="system-prompt"></textarea>
                            </div>
                            <div class="form-group">
                                <label for="add-wait-tag">Ajouter \wait\ à la fin de la parole</label>
                                <input type="checkbox" id="add-wait-tag">
                            </div>
                            <div class="form-group">
                                <label for="enable-startup-animation">Animation de démarrage</label>
                                <input type="checkbox" id="enable-startup-animation">
                            </div>
                            <div class="form-group">
                                <label for="enable-thinking-gesture">Gestes de réflexion</label>
                                <input type="checkbox" id="enable-thinking-gesture">
                            </div>
                        </div>
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

function pollUntilChatReady(api, statusEl, mainChatBtn, updateStatusCallback) {
    const poller = setInterval(async () => {
        try {
            const status = await api.getDetailedChatStatus();
            if (status.status === 'running') {
                clearInterval(poller);
                await api.getChatStatus().then(newStatus => updateStatusCallback(newStatus, statusEl, mainChatBtn));
            }
        } catch (e) {
            console.warn("Polling for chat ready status failed, will retry...");
        }
    }, 1000);

    // Timeout to prevent infinite polling
    setTimeout(() => {
        clearInterval(poller);
        if (mainChatBtn.disabled) {
            api.getChatStatus().then(newStatus => updateStatusCallback(newStatus, statusEl, mainChatBtn));
        }
    }, 30000); // 30 seconds timeout
}

function init(api) {
    const mainChatBtn = document.getElementById('main-chat-btn');
    const statusEl = document.getElementById('current-chat-status');
    const gptSettings = document.getElementById('gpt-settings');
    const saveGptBtn = document.getElementById('save-gpt-settings');

    const apiKeyInput = document.getElementById('gpt-api-key');
    const modelSelect = document.getElementById('gpt-model');
    const promptTextarea = document.getElementById('gpt-prompt');
    const tempInput = document.getElementById('gpt-temperature');
    const reasoningSelect = document.getElementById('gpt-reasoning');
    const historyInput = document.getElementById('gpt-history');
    const maxTokensInput = document.getElementById('gpt-max-tokens');
    const verbositySelect = document.getElementById('gpt-verbosity');
    const systemPromptTextarea = document.getElementById('system-prompt');
    const addWaitTagCheckbox = document.getElementById('add-wait-tag');
    const startupAnimCheckbox = document.getElementById('enable-startup-animation');
    const thinkingGestureCheckbox = document.getElementById('enable-thinking-gesture');

    let currentConfig = {};
    let currentStatus = {};
    let currentSystemPrompt = '';

    function updateMainButton(status, btn) {
        btn.disabled = false;
        if (status.is_running) {
            btn.innerHTML = `<i class="bi bi-stop-circle-fill"></i> Arrêter le Chat`;
            btn.classList.add('btn-danger');
            btn.classList.remove('btn-success');
        } else {
            btn.innerHTML = `<i class="bi bi-play-circle-fill"></i> Activer le Chat`;
            btn.classList.add('btn-success');
            btn.classList.remove('btn-danger');
        }
    }

    function updateModelOptionsVisibility() {
        const modelName = modelSelect.value.toLowerCase();
        const isGpt5 = modelName.startsWith('gpt-5');
        const tempDisplay = isGpt5 ? 'none' : 'block';
        const reasonDisplay = isGpt5 ? 'block' : 'none';

        document.getElementById('form-group-temperature').style.display = tempDisplay;
        document.getElementById('form-group-reasoning').style.display = reasonDisplay;
    }

    function updateStatus(status, el, btn) {
        currentStatus = status;
        el.textContent = status.is_running ? `Actif (${status.mode})` : 'Arrêté';
        const modeRadio = document.getElementById(`mode-${status.mode || 'basic'}`);
        if (modeRadio) {
            modeRadio.checked = true;
        }
        if (status.mode === 'gpt') {
            gptSettings.classList.remove('hidden');
        } else {
            gptSettings.classList.add('hidden');
        }
        updateMainButton(status, btn);
    }

    function loadConfig() {
        return Promise.all([
            api.configGetUser(),
            api.getSystemPrompt()
        ]).then(([config, systemPromptData]) => {
            currentConfig = config;
            currentSystemPrompt = systemPromptData.content;

            apiKeyInput.value = config.openai?.api_key || '';
            modelSelect.value = config.openai?.chat_model || 'gpt-4o-mini';
            promptTextarea.value = config.openai?.custom_prompt || '';
            tempInput.value = config.openai?.temperature ?? 0.2;
            reasoningSelect.value = config.openai?.reasoning_effort || 'low';
            historyInput.value = config.openai?.history_length ?? 4;
            maxTokensInput.value = config.openai?.max_output_tokens ?? 4096;
            verbositySelect.value = config.openai?.text_verbosity || 'low';
            addWaitTagCheckbox.checked = config.audio?.add_wait_tag || false;
            startupAnimCheckbox.checked = config.animations?.enable_startup_animation ?? true;
            thinkingGestureCheckbox.checked = config.animations?.enable_thinking_gesture ?? true;
            systemPromptTextarea.value = currentSystemPrompt;

            updateModelOptionsVisibility(); // Set initial visibility
        });
    }

    function getStatus() {
        return api.getChatStatus().then(status => updateStatus(status, statusEl, mainChatBtn));
    }

    // Event Listeners
    modelSelect.addEventListener('input', updateModelOptionsVisibility);

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
        
        const newConfig = Object.assign({}, currentConfig, {
            openai: Object.assign({}, currentConfig.openai, {
                api_key: apiKeyInput.value,
                chat_model: modelSelect.value,
                custom_prompt: promptTextarea.value,
                temperature: parseFloat(tempInput.value),
                reasoning_effort: reasoningSelect.value,
                history_length: parseInt(historyInput.value, 10),
                max_output_tokens: parseInt(maxTokensInput.value, 10),
                text_verbosity: verbositySelect.value
            }),
            audio: Object.assign({}, currentConfig.audio, {
                add_wait_tag: addWaitTagCheckbox.checked
            }),
            animations: Object.assign({}, currentConfig.animations, {
                enable_startup_animation: startupAnimCheckbox.checked,
                enable_thinking_gesture: thinkingGestureCheckbox.checked
            })
        });

        const newSystemPrompt = systemPromptTextarea.value;

        Promise.all([
            api.configSetUser(newConfig),
            api.setSystemPrompt({content: newSystemPrompt})
        ]).then(() => {
            currentConfig = newConfig;
            currentSystemPrompt = newSystemPrompt;

            if (currentStatus.is_running && currentStatus.mode === 'gpt') {
                if (confirm("Paramètres enregistrés. Le chat GPT est en cours d'exécution. Voulez-vous le redémarrer maintenant pour appliquer les nouveaux paramètres ?")) {
                    // Restart the chat
                    mainChatBtn.disabled = true;
                    mainChatBtn.innerHTML = '...';
                    api.stopChat().then(() => {
                        api.startChat('gpt').then(() => pollUntilChatReady(api, statusEl, mainChatBtn, updateStatus));
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
        mainChatBtn.innerHTML = '<span class="inline-spinner"></span>';

        if (currentStatus.is_running) {
            api.stopChat().then(getStatus).catch(err => {
                alert(`Erreur à l'arrêt: ${err.message}`);
                getStatus(); // Refresh status anyway
            });
        } else {
            const selectedMode = document.querySelector('input[name="chat_mode"]:checked').value;
            api.startChat(selectedMode).then(() => {
                if (selectedMode === 'gpt') {
                    pollUntilChatReady(api, statusEl, mainChatBtn, updateStatus);
                } else {
                    getStatus(); // For basic mode, update immediately
                }
            }).catch(err => {
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