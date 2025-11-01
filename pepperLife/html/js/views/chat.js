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
      .debug-output { background: #0f0f0f; color: #d0ffd0; padding: 0.75rem; border-radius: 6px; max-height: 220px; overflow: auto; font-size: 0.85em; max-width: 700px; margin: 0 auto 1rem; white-space: pre-wrap; word-break: break-word; }
      .status-inline { margin-left: 0.75rem; font-size: 0.9em; color: #555; }
      .form-subgroup { border-left: 3px solid #ccc; padding-left: 1rem; margin-top: 0.75rem; }
      .mini-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
      .checkbox-inline { display: flex; align-items: center; gap: 0.5rem; }
      #stt-card { margin-top: 1.5rem; }
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
                                <div class="checkbox-inline">
                                    <input type="checkbox" id="gpt-stream">
                                    <label for="gpt-stream">Activer le streaming (expérimental)</label>
                                </div>
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

            <div class="card chat-option">
                <div class="title"><input type="radio" name="chat_mode" value="ollama" id="mode-ollama"> <label for="mode-ollama">Ollama Distant</label></div>
                <p class="description">Utilise un serveur Ollama sur le réseau pour un chat local sans dépendre d'OpenAI.</p>
                <div id="ollama-settings" class="settings hidden">
                    <div class="settings-grid">
                        <div>
                            <div class="form-group">
                                <label for="ollama-server">Serveur Ollama</label>
                                <input type="text" id="ollama-server" list="ollama-server-options" placeholder="http://192.168.1.20:11434">
                                <datalist id="ollama-server-options"></datalist>
                            </div>
                            <div class="form-group">
                                <label for="ollama-model">Modèle disponible</label>
                                <select id="ollama-model">
                                    <option value="">-- Cliquez sur « Tester » pour charger --</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <button id="ollama-test" class="btn btn-secondary" type="button"><i class="bi bi-arrow-repeat"></i> Tester la connexion</button>
                                <span id="ollama-status" class="status-inline"></span>
                            </div>
                        </div>
                        <div>
                            <div class="form-group">
                                <label for="ollama-temperature">Temperature</label>
                                <input type="number" step="0.1" min="0" max="2" id="ollama-temperature">
                            </div>
                            <div class="form-group">
                                <label for="ollama-history">Historique conservé</label>
                                <input type="number" min="1" max="10" id="ollama-history">
                            </div>
                            <div class="form-group checkbox-inline">
                                <input type="checkbox" id="ollama-stream">
                                <label for="ollama-stream">Activer le streaming (recommandé)</label>
                            </div>
                            <div class="form-group">
                                <label for="ollama-system-prompt">Prompt système Ollama</label>
                                <textarea id="ollama-system-prompt" placeholder="Remplace ou complète le prompt système global pour Ollama..."></textarea>
                            </div>
                            <div class="form-group checkbox-inline">
                                <input type="checkbox" id="ollama-add-wait-tag">
                                <label for="ollama-add-wait-tag">Ajouter le tag ^wait automatique</label>
                            </div>
                            <div class="form-group checkbox-inline">
                                <input type="checkbox" id="ollama-enable-startup-animation">
                                <label for="ollama-enable-startup-animation">Animer le démarrage</label>
                            </div>
                            <div class="form-group checkbox-inline">
                                <input type="checkbox" id="ollama-enable-thinking-gesture">
                                <label for="ollama-enable-thinking-gesture">Gestes de réflexion</label>
                            </div>
                            <div class="form-group">
                                <label for="ollama-prompt">Prompt personnalisé</label>
                                <textarea id="ollama-prompt" placeholder="Ajoute des instructions spécifiques pour le modèle Ollama..."></textarea>
                            </div>
                        </div>
                    </div>
                    <div class="form-group">
                        <button id="save-ollama-settings" class="btn btn-primary" type="button"><i class="bi bi-save"></i> Enregistrer</button>
                    </div>
                </div>
            </div>

            <div class="card chat-option">
                <div class="title">Console de Test</div>
                <p class="description">Envoyez un message directement au chatbot actif pour vérifier rapidement les prompts et paramètres.</p>
                <div class="form-group">
                    <label for="debug-chat-input">Message</label>
                    <textarea id="debug-chat-input" placeholder="Bonjour Pepper, que peux-tu faire ?"></textarea>
                </div>
                <div class="form-group">
                    <button id="debug-chat-send" class="btn btn-secondary" type="button"><i class="bi bi-send"></i> Envoyer</button>
                    <span id="debug-chat-status" class="status-inline"></span>
                </div>
                <pre id="debug-chat-stream" class="debug-output hidden"></pre>
                <pre id="debug-chat-response" class="debug-output hidden"></pre>
            </div>
        </div>
        <div class="card" id="stt-card">
            <div class="title"><i class="bi bi-mic"></i> Reconnaissance vocale</div>
            <p class="description">Configure le moteur de transcription utilisé par Pepper pour comprendre la parole.</p>
            <div id="stt-settings" class="settings">
                <div class="form-group">
                    <label for="stt-engine">Moteur</label>
                <select id="stt-engine">
                    <option value="openai">OpenAI</option>
                    <option value="local">Whisper local</option>
                </select>
            </div>
            <div id="stt-openai-settings" class="form-subgroup">
                <div class="form-group">
                    <label for="stt-openai-model">Modèle OpenAI</label>
                    <input type="text" id="stt-openai-model" placeholder="gpt-4o-transcribe">
                </div>
            </div>
            <div id="stt-local-settings" class="form-subgroup hidden">
                <div class="form-group">
                    <label for="stt-server">Serveur Whisper</label>
                    <input type="text" id="stt-server" placeholder="http://192.168.1.20:8001">
                </div>
                <div class="form-group mini-grid">
                    <div>
                        <label for="stt-health-endpoint">Endpoint santé</label>
                        <input type="text" id="stt-health-endpoint" placeholder="/health">
                    </div>
                    <div>
                        <label for="stt-transcribe-endpoint">Endpoint transcription</label>
                        <input type="text" id="stt-transcribe-endpoint" placeholder="/transcribe">
                    </div>
                </div>
                <div class="form-group">
                    <button id="stt-test" class="btn btn-secondary" type="button"><i class="bi bi-arrow-repeat"></i> Tester</button>
                    <span id="stt-status" class="status-inline"></span>
                </div>
            </div>
            <div class="form-group">
                <label for="stt-language">Langue</label>
                <input type="text" id="stt-language" placeholder="fr">
            </div>
            <div class="form-group">
                <button id="save-stt-settings" class="btn btn-primary" type="button"><i class="bi bi-save"></i> Enregistrer</button>
            </div>
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
    const ollamaSettings = document.getElementById('ollama-settings');
    const saveOllamaBtn = document.getElementById('save-ollama-settings');
    const ollamaServerInput = document.getElementById('ollama-server');
    const ollamaServerOptions = document.getElementById('ollama-server-options');
    const ollamaModelSelect = document.getElementById('ollama-model');
    const ollamaTestBtn = document.getElementById('ollama-test');
    const ollamaStatus = document.getElementById('ollama-status');
    const ollamaTemperatureInput = document.getElementById('ollama-temperature');
    const ollamaHistoryInput = document.getElementById('ollama-history');
    const ollamaStreamCheckbox = document.getElementById('ollama-stream');
    const ollamaSystemPromptTextarea = document.getElementById('ollama-system-prompt');
    const ollamaAddWaitCheckbox = document.getElementById('ollama-add-wait-tag');
    const ollamaStartupAnimCheckbox = document.getElementById('ollama-enable-startup-animation');
    const ollamaThinkingCheckbox = document.getElementById('ollama-enable-thinking-gesture');
    const ollamaPromptTextarea = document.getElementById('ollama-prompt');
    const debugChatInput = document.getElementById('debug-chat-input');
    const debugChatSendBtn = document.getElementById('debug-chat-send');
    const debugChatStatus = document.getElementById('debug-chat-status');
    const debugChatStream = document.getElementById('debug-chat-stream');
    const debugChatResponse = document.getElementById('debug-chat-response');
    const defaultOllamaBtnLabel = saveOllamaBtn ? saveOllamaBtn.innerHTML : '';
    const saveSttBtn = document.getElementById('save-stt-settings');
    const defaultSttBtnLabel = saveSttBtn ? saveSttBtn.innerHTML : '';

    const apiKeyInput = document.getElementById('gpt-api-key');
    const modelSelect = document.getElementById('gpt-model');
    const promptTextarea = document.getElementById('gpt-prompt');
    const tempInput = document.getElementById('gpt-temperature');
    const reasoningSelect = document.getElementById('gpt-reasoning');
    const gptStreamCheckbox = document.getElementById('gpt-stream');
    const historyInput = document.getElementById('gpt-history');
    const maxTokensInput = document.getElementById('gpt-max-tokens');
    const verbositySelect = document.getElementById('gpt-verbosity');
    const systemPromptTextarea = document.getElementById('system-prompt');
    const addWaitTagCheckbox = document.getElementById('add-wait-tag');
    const startupAnimCheckbox = document.getElementById('enable-startup-animation');
    const thinkingGestureCheckbox = document.getElementById('enable-thinking-gesture');
    const sttEngineSelect = document.getElementById('stt-engine');
    const sttOpenaiModelInput = document.getElementById('stt-openai-model');
    const sttLocalSettings = document.getElementById('stt-local-settings');
    const sttOpenaiSettings = document.getElementById('stt-openai-settings');
    const sttServerInput = document.getElementById('stt-server');
    const sttHealthInput = document.getElementById('stt-health-endpoint');
    const sttTranscribeInput = document.getElementById('stt-transcribe-endpoint');
    const sttTestBtn = document.getElementById('stt-test');
    const sttStatus = document.getElementById('stt-status');
    const sttLanguageInput = document.getElementById('stt-language');

    let currentConfig = {};
    let currentStatus = {};
    let currentSystemPrompt = '';
    let currentOllamaSystemPrompt = '';
    let lastOllamaModels = [];

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

    function updateSttVisibility() {
        const engine = (sttEngineSelect?.value || 'openai').toLowerCase();
        if (sttLocalSettings) {
            if (engine === 'local') {
                sttLocalSettings.classList.remove('hidden');
            } else {
                sttLocalSettings.classList.add('hidden');
            }
        }
        if (sttOpenaiSettings) {
            const showOpenai = engine === 'openai';
            if (showOpenai) {
                sttOpenaiSettings.classList.remove('hidden');
            } else {
                sttOpenaiSettings.classList.add('hidden');
            }
        }
        if (sttTestBtn) {
            sttTestBtn.disabled = engine !== 'local';
        }
        if (sttStatus) {
            sttStatus.textContent = '';
        }
    }

    function normalizeServerUrl(value) {
        if (!value) return '';
        const trimmed = value.trim();
        if (!trimmed) return '';
        return /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
    }

    function ensureLeadingSlash(value, fallback = '/') {
        const trimmed = (value || '').trim();
        if (!trimmed) return fallback;
        return trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
    }

    function updateOllamaServerOptions(servers) {
        if (!ollamaServerOptions) return;
        ollamaServerOptions.innerHTML = '';
        (servers || []).filter(Boolean).forEach(server => {
            const option = document.createElement('option');
            option.value = server;
            ollamaServerOptions.appendChild(option);
        });
    }

    function populateOllamaModels(models, selectedModel) {
        if (!ollamaModelSelect) return;
        lastOllamaModels = models || [];
        while (ollamaModelSelect.firstChild) {
            ollamaModelSelect.removeChild(ollamaModelSelect.firstChild);
        }
        const placeholder = document.createElement('option');
        if (lastOllamaModels.length) {
            placeholder.textContent = '-- Sélectionner un modèle --';
        } else {
            placeholder.textContent = '-- Aucun modèle détecté --';
        }
        placeholder.value = '';
        ollamaModelSelect.appendChild(placeholder);

        const seen = new Set();

        (models || []).forEach(model => {
            let value = '';
            if (typeof model === 'string') {
                value = model.trim();
            } else if (model && typeof model === 'object') {
                value = (model.name || model.alias || model.model || '').trim();
            }
            if (!value) {
                return;
            }
            const key = value.toLowerCase();
            if (seen.has(key)) {
                return;
            }
            seen.add(key);
            const option = document.createElement('option');
            option.value = value;
            option.textContent = value;
            if (selectedModel && option.value === selectedModel) {
                option.selected = true;
            }
            ollamaModelSelect.appendChild(option);
        });

        if (selectedModel && !Array.from(ollamaModelSelect.options).some(opt => opt.value === selectedModel)) {
            const option = document.createElement('option');
            option.value = selectedModel;
            option.textContent = `${selectedModel} (configuré)`;
            option.selected = true;
            ollamaModelSelect.appendChild(option);
        }
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
            ollamaSettings.classList.add('hidden');
        } else if (status.mode === 'ollama') {
            gptSettings.classList.add('hidden');
            ollamaSettings.classList.remove('hidden');
        } else {
            gptSettings.classList.add('hidden');
            ollamaSettings.classList.add('hidden');
        }
        updateMainButton(status, btn);
    }

    function loadConfig() {
        if (ollamaServerInput && ollamaServerInput.value) {
            const normalizedProbeServer = normalizeServerUrl(ollamaServerInput.value);
            if (normalizedProbeServer) {
                api.probeOllama(normalizedProbeServer).then(probe => {
                    const modelsData = probe.models && probe.models.length ? probe.models : (probe.model_names || []);
                    const preferredModel = ollamaModelSelect.value || currentConfig?.ollama?.chat_model || "";
                    populateOllamaModels(modelsData || [], preferredModel);
                }).catch(err => {
                    console.warn("Automatic Ollama probe failed:", err);
                });
            }
        }
        return Promise.all([
            api.configGetUser(),
            api.getSystemPrompt('gpt'),
            api.getSystemPrompt('ollama')
        ]).then(([config, gptPromptData, ollamaPromptData]) => {
            currentConfig = config;
            currentSystemPrompt = (gptPromptData && gptPromptData.content) || '';
            currentOllamaSystemPrompt = (ollamaPromptData && ollamaPromptData.content) || '';

            apiKeyInput.value = config.openai?.api_key || '';
            modelSelect.value = config.openai?.chat_model || 'gpt-4o-mini';
            promptTextarea.value = config.openai?.custom_prompt || '';
            tempInput.value = config.openai?.temperature ?? 0.2;
            reasoningSelect.value = config.openai?.reasoning_effort || 'low';
            if (gptStreamCheckbox) {
                gptStreamCheckbox.checked = config.openai?.stream !== false;
            }
            historyInput.value = config.openai?.history_length ?? 4;
            maxTokensInput.value = config.openai?.max_output_tokens ?? 4096;
            verbositySelect.value = config.openai?.text_verbosity || 'low';
            addWaitTagCheckbox.checked = config.audio?.add_wait_tag || false;
            startupAnimCheckbox.checked = config.animations?.enable_startup_animation ?? true;
            thinkingGestureCheckbox.checked = config.animations?.enable_thinking_gesture ?? true;
            if (systemPromptTextarea) {
                systemPromptTextarea.value = currentSystemPrompt;
            }

            const sttCfg = config.stt || {};
            if (sttEngineSelect) sttEngineSelect.value = (sttCfg.engine || 'openai');
            if (sttOpenaiModelInput) sttOpenaiModelInput.value = sttCfg.model || config.openai?.stt_model || 'gpt-4o-transcribe';
            if (sttServerInput) sttServerInput.value = sttCfg.local_server_url || 'http://127.0.0.1:8001';
            if (sttHealthInput) sttHealthInput.value = sttCfg.health_endpoint || '/health';
            if (sttTranscribeInput) sttTranscribeInput.value = sttCfg.transcribe_endpoint || '/transcribe';
            if (sttLanguageInput) sttLanguageInput.value = sttCfg.language || 'fr';
            if (sttStatus) sttStatus.textContent = '';
            updateSttVisibility();

            const ollamaCfg = config.ollama || {};
            updateOllamaServerOptions(ollamaCfg.preferred_servers || []);
            if (ollamaCfg.active_server) {
                ollamaServerInput.value = ollamaCfg.active_server;
            } else {
                ollamaServerInput.value = '';
            }
            populateOllamaModels(lastOllamaModels, ollamaCfg.chat_model || '');
            ollamaTemperatureInput.value = ollamaCfg.temperature ?? 0.7;
            ollamaHistoryInput.value = ollamaCfg.history_length ?? 4;
            ollamaPromptTextarea.value = ollamaCfg.custom_prompt || '';
            if (ollamaStreamCheckbox) {
                ollamaStreamCheckbox.checked = ollamaCfg.stream !== false;
            }
            if (ollamaSystemPromptTextarea) {
                ollamaSystemPromptTextarea.value = currentOllamaSystemPrompt;
            }
            if (ollamaAddWaitCheckbox) {
                ollamaAddWaitCheckbox.checked = ollamaCfg.add_wait_tag ?? (config.audio?.add_wait_tag ?? false);
            }
            if (ollamaStartupAnimCheckbox) {
                ollamaStartupAnimCheckbox.checked = ollamaCfg.enable_startup_animation ?? (config.animations?.enable_startup_animation ?? true);
            }
            if (ollamaThinkingCheckbox) {
                ollamaThinkingCheckbox.checked = ollamaCfg.enable_thinking_gesture ?? (config.animations?.enable_thinking_gesture ?? true);
            }
            if (ollamaStatus) {
                ollamaStatus.textContent = '';
            }

            if (ollamaServerInput && ollamaServerInput.value) {
                const normalizedProbeServer = normalizeServerUrl(ollamaServerInput.value);
                if (normalizedProbeServer) {
                    api.probeOllama(normalizedProbeServer).then(probe => {
                        const modelsData = probe.models && probe.models.length ? probe.models : (probe.model_names || []);
                        const preferredModel = ollamaModelSelect.value || currentConfig?.ollama?.chat_model || '';
                        populateOllamaModels(modelsData || [], preferredModel);
                    }).catch(err => {
                        console.warn("Automatic Ollama probe failed:", err);
                    });
                }
            }

            updateModelOptionsVisibility(); // Set initial visibility
        });
    }

    function getStatus() {
        return api.getChatStatus().then(status => updateStatus(status, statusEl, mainChatBtn));
    }

    // Event Listeners
    modelSelect.addEventListener('input', updateModelOptionsVisibility);

    if (ollamaModelSelect) {
        ollamaModelSelect.addEventListener('change', () => {
            const newModel = (ollamaModelSelect.value || '').trim();
            if (!currentConfig) return;
            const updatedConfig = Object.assign({}, currentConfig, {
                ollama: Object.assign({}, currentConfig.ollama || {}, {
                    chat_model: newModel || ''
                })
            });
            api.configSetUser(updatedConfig).then(() => {
                currentConfig = updatedConfig;
                if (ollamaStatus) {
                    ollamaStatus.textContent = newModel ? `Modèle actif: ${newModel}` : 'Modèle Ollama par défaut';
                }
            }).catch(err => {
                console.warn("Impossible de sauvegarder le modèle Ollama", err);
                if (ollamaStatus) {
                    ollamaStatus.textContent = `Erreur enregistrement: ${err.message}`;
                }
            });
        });
    }

    document.querySelectorAll('input[name="chat_mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.value === 'gpt') {
                gptSettings.classList.remove('hidden');
                ollamaSettings.classList.add('hidden');
            } else if (e.target.value === 'ollama') {
                gptSettings.classList.add('hidden');
                ollamaSettings.classList.remove('hidden');
            } else {
                gptSettings.classList.add('hidden');
                ollamaSettings.classList.add('hidden');
            }
        });
    });

    if (sttEngineSelect) {
        sttEngineSelect.addEventListener('change', updateSttVisibility);
    }

    if (sttTestBtn) {
        sttTestBtn.addEventListener('click', async () => {
            if (sttEngineSelect && sttEngineSelect.value !== 'local') {
                if (sttStatus) {
                    sttStatus.textContent = 'Sélectionne "Whisper local" avant de tester.';
                }
                return;
            }
            const normalized = normalizeServerUrl(sttServerInput.value);
            if (!normalized) {
                if (sttStatus) {
                    sttStatus.textContent = 'Renseigne une adresse valide.';
                }
                return;
            }
            const healthPath = ensureLeadingSlash(sttHealthInput ? sttHealthInput.value : '/health', '/health');
            if (sttStatus) {
                sttStatus.textContent = 'Test en cours...';
            }
            sttTestBtn.disabled = true;
            try {
                const probe = await api.probeStt(normalized, healthPath);
                const targetServer = probe.normalized_url || normalized;
                sttServerInput.value = targetServer;
                const statusText = probe.status ? `HTTP ${probe.status}` : 'OK';
                if (sttStatus) {
                    sttStatus.textContent = `Connecté (${statusText})`;
                }
            } catch (err) {
                const msg = (err && err.message) ? err.message.split('\n')[0] : String(err);
                if (sttStatus) {
                    sttStatus.textContent = `Erreur: ${msg}`;
                }
            } finally {
                sttTestBtn.disabled = false;
            }
        });
    }

    if (ollamaTestBtn) {
        ollamaTestBtn.addEventListener('click', async () => {
            const normalized = normalizeServerUrl(ollamaServerInput.value);
            if (!normalized) {
                if (ollamaStatus) {
                    ollamaStatus.textContent = 'Renseigne d’abord une adresse valide.';
                }
                populateOllamaModels([], currentConfig?.ollama?.chat_model || '');
                return;
            }
            if (ollamaStatus) {
                ollamaStatus.textContent = 'Test en cours...';
            }
            ollamaTestBtn.disabled = true;
            try {
                const probe = await api.probeOllama(normalized);
                const targetServer = probe.normalized_url || normalized;
                ollamaServerInput.value = targetServer;
                const existingServers = (currentConfig?.ollama?.preferred_servers || []).slice();
                if (targetServer && !existingServers.includes(targetServer)) {
                    existingServers.push(targetServer);
                }
                updateOllamaServerOptions(existingServers);
                const modelsData = probe.models && probe.models.length ? probe.models : (probe.model_names || []);
                const defaultModel = Array.isArray(modelsData) && modelsData.length ? (typeof modelsData[0] === 'string' ? modelsData[0] : (modelsData[0].name || modelsData[0].alias || modelsData[0].model || '')) : '';
                const preferredModel = ollamaModelSelect.value || currentConfig?.ollama?.chat_model || defaultModel;
                populateOllamaModels(modelsData || [], preferredModel);
                const versionLabel = probe.version ? `v${probe.version}` : 'OK';
                if (ollamaStatus) {
                    ollamaStatus.textContent = `Connecté (${versionLabel})`;
                }
            } catch (err) {
                const msg = (err && err.message) ? err.message.split('\n')[0] : String(err);
                populateOllamaModels([], currentConfig?.ollama?.chat_model || '');
                if (ollamaStatus) {
                    ollamaStatus.textContent = `Erreur: ${msg}`;
                }
            } finally {
                ollamaTestBtn.disabled = false;
            }
        });
    }

    if (debugChatInput && debugChatSendBtn) {
        debugChatSendBtn.addEventListener('click', async () => {
            const message = (debugChatInput.value || '').trim();
            if (!message) {
                if (debugChatStatus) {
                    debugChatStatus.textContent = 'Message vide.';
                }
                return;
            }

            const mode = (currentStatus.mode || 'basic').toLowerCase();
            if (!['gpt', 'ollama'].includes(mode)) {
                if (debugChatStatus) {
                    debugChatStatus.textContent = 'Démarre d\'abord le mode GPT ou Ollama.';
                }
                return;
            }

            const payload = {
                message: message,
                mode: mode,
                history: []
            };

            if (mode === 'gpt') {
                if (systemPromptTextarea) payload.system_prompt = systemPromptTextarea.value;
                if (promptTextarea) payload.custom_prompt = promptTextarea.value;
                if (modelSelect) payload.model = modelSelect.value;
                if (tempInput && tempInput.value !== '') {
                    const parsedTemp = parseFloat(tempInput.value);
                    if (!Number.isNaN(parsedTemp)) {
                        payload.temperature = parsedTemp;
                    }
                }
                if (maxTokensInput && maxTokensInput.value !== '') {
                    const parsedMax = parseInt(maxTokensInput.value, 10);
                    if (!Number.isNaN(parsedMax)) {
                        payload.max_output_tokens = parsedMax;
                    }
                }
                if (gptStreamCheckbox) {
                    payload.stream = !!gptStreamCheckbox.checked;
                } else {
                    payload.stream = true;
                }
            } else if (mode === 'ollama') {
                if (ollamaSystemPromptTextarea) payload.system_prompt = ollamaSystemPromptTextarea.value;
                if (ollamaPromptTextarea) payload.custom_prompt = ollamaPromptTextarea.value;
                if (ollamaModelSelect) payload.model = ollamaModelSelect.value;
                if (ollamaServerInput && ollamaServerInput.value) {
                    const normalizedServer = normalizeServerUrl(ollamaServerInput.value);
                    if (normalizedServer) {
                        payload.server = normalizedServer;
                    }
                }
                if (ollamaTemperatureInput && ollamaTemperatureInput.value !== '') {
                    const parsedTemp = parseFloat(ollamaTemperatureInput.value);
                    if (!Number.isNaN(parsedTemp)) {
                        payload.temperature = parsedTemp;
                    }
                }
                if (ollamaHistoryInput && ollamaHistoryInput.value !== '') {
                    const parsedHistory = parseInt(ollamaHistoryInput.value, 10);
                    if (!Number.isNaN(parsedHistory)) {
                        payload.history_length = parsedHistory;
                    }
                }
                if (ollamaStreamCheckbox) {
                    payload.stream = !!ollamaStreamCheckbox.checked;
                }
            }

            let useStreaming = false;
            if (mode === 'ollama') {
                useStreaming = payload.stream !== false;
                if (useStreaming && payload.stream == null) {
                    payload.stream = true;
                }
            } else if (mode === 'gpt') {
                useStreaming = payload.stream === true;
            }

            debugChatSendBtn.disabled = true;
            if (debugChatStatus) {
                debugChatStatus.textContent = useStreaming ? 'Streaming...' : 'Envoi...';
            }
            if (debugChatStream) {
                debugChatStream.textContent = '';
                if (useStreaming) {
                    debugChatStream.classList.remove('hidden');
                } else {
                    debugChatStream.classList.add('hidden');
                }
            }
            if (debugChatResponse) {
                debugChatResponse.textContent = '';
                debugChatResponse.classList.add('hidden');
            }

            try {
                if (useStreaming) {
                    let streamedText = '';
                    const streamResult = await api.chatSendStream(payload, {
                        onChunk: (event) => {
                            if (!event || typeof event !== 'object') {
                                return;
                            }
                            if (event.type === 'chunk' && typeof event.delta === 'string' && event.delta) {
                                streamedText += event.delta;
                                if (debugChatStream) {
                                    debugChatStream.textContent = streamedText;
                                }
                            } else if (event.type === 'status' && event.message && debugChatStatus) {
                                debugChatStatus.textContent = event.message;
                            }
                        }
                    });
                    const finalResult = streamResult?.result || {};
                    if (finalResult.error) {
                        if (debugChatStatus) {
                            debugChatStatus.textContent = finalResult.error;
                        }
                        if (debugChatResponse) {
                            debugChatResponse.classList.add('hidden');
                        }
                    } else {
                        if (debugChatStatus) {
                            debugChatStatus.textContent = 'Stream terminé.';
                        }
                        if (debugChatResponse) {
                            debugChatResponse.textContent = JSON.stringify(finalResult, null, 2);
                            debugChatResponse.classList.remove('hidden');
                        }
                    }
                } else {
                    const response = await api.chatSend(payload);
                    if (response.error) {
                        if (debugChatStatus) {
                            debugChatStatus.textContent = response.error;
                        }
                        if (debugChatResponse) {
                            debugChatResponse.classList.add('hidden');
                        }
                        if (debugChatStream) {
                            debugChatStream.classList.add('hidden');
                        }
                    } else {
                        if (debugChatStatus) {
                            debugChatStatus.textContent = 'Réponse reçue.';
                        }
                        if (debugChatResponse) {
                            debugChatResponse.textContent = JSON.stringify(response, null, 2);
                            debugChatResponse.classList.remove('hidden');
                        }
                    }
                }
            } catch (err) {
                if (debugChatStatus) {
                    debugChatStatus.textContent = `Erreur: ${err.message}`;
                }
                if (debugChatResponse) {
                    debugChatResponse.classList.add('hidden');
                }
                if (debugChatStream) {
                    debugChatStream.classList.add('hidden');
                }
            } finally {
                debugChatSendBtn.disabled = false;
            }
        });

        debugChatInput.addEventListener('keydown', (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                event.preventDefault();
                debugChatSendBtn.click();
            }
        });
    }

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
                stream: gptStreamCheckbox ? !!gptStreamCheckbox.checked : (currentConfig.openai?.stream ?? true),
                history_length: parseInt(historyInput.value, 10),
                max_output_tokens: parseInt(maxTokensInput.value, 10),
                text_verbosity: verbositySelect.value,
                stt_model: sttOpenaiModelInput ? sttOpenaiModelInput.value : (currentConfig.openai?.stt_model || 'gpt-4o-transcribe')
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
            api.setSystemPrompt(newSystemPrompt, 'gpt')
        ]).then(() => {
            currentConfig = newConfig;
            currentSystemPrompt = newSystemPrompt;
            updateSttVisibility();

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

    if (saveSttBtn) {
        saveSttBtn.addEventListener('click', () => {
            saveSttBtn.disabled = true;
            saveSttBtn.innerHTML = '<span class="inline-spinner"></span> Enregistrement...';

            const normalizedServer = normalizeServerUrl(sttServerInput ? sttServerInput.value : '');
            const sttConfig = Object.assign({}, currentConfig.stt, {
                engine: sttEngineSelect ? sttEngineSelect.value : 'openai',
                model: sttOpenaiModelInput ? sttOpenaiModelInput.value : (currentConfig.openai?.stt_model || 'gpt-4o-transcribe'),
                language: sttLanguageInput ? (sttLanguageInput.value || 'fr') : 'fr',
                local_server_url: normalizedServer,
                health_endpoint: ensureLeadingSlash(sttHealthInput ? sttHealthInput.value : '/health', '/health'),
                transcribe_endpoint: ensureLeadingSlash(sttTranscribeInput ? sttTranscribeInput.value : '/transcribe', '/transcribe')
            });

            const newConfig = Object.assign({}, currentConfig, {
                stt: sttConfig,
                openai: Object.assign({}, currentConfig.openai, {
                    stt_model: sttOpenaiModelInput ? sttOpenaiModelInput.value : (currentConfig.openai?.stt_model || 'gpt-4o-transcribe')
                })
            });

            api.configSetUser(newConfig).then(() => {
                currentConfig = newConfig;
                updateSttVisibility();

                if (currentStatus.is_running) {
                    if (confirm("Paramètres STT enregistrés. Le chatbot est actif. Voulez-vous le redémarrer maintenant pour appliquer les nouveaux paramètres ?")) {
                        const modeToRestart = currentStatus.mode || 'gpt';
                        mainChatBtn.disabled = true;
                        mainChatBtn.innerHTML = '<span class="inline-spinner"></span>';
                        api.stopChat()
                            .then(() => api.startChat(modeToRestart))
                            .then(() => pollUntilChatReady(api, statusEl, mainChatBtn, updateStatus))
                            .catch(err => {
                                alert(`Erreur lors du redémarrage: ${err.message}`);
                                getStatus();
                            });
                    }
                } else {
                    alert('Paramètres STT enregistrés. Ils seront utilisés au prochain démarrage du chat.');
                }
            }).catch(err => {
                alert(`Erreur lors de l'enregistrement STT : ${err.message}`);
            }).finally(() => {
                saveSttBtn.innerHTML = defaultSttBtnLabel || 'Enregistrer';
                saveSttBtn.disabled = false;
            });
        });
    }

    if (saveOllamaBtn) {
        saveOllamaBtn.addEventListener('click', () => {
            saveOllamaBtn.disabled = true;
            saveOllamaBtn.innerHTML = '<span class="inline-spinner"></span> Enregistrement...';

            const normalizedServer = normalizeServerUrl(ollamaServerInput.value);
            const existingServers = (currentConfig?.ollama?.preferred_servers || []).slice();
            if (normalizedServer && !existingServers.includes(normalizedServer)) {
                existingServers.push(normalizedServer);
            }

            const parsedTemperature = parseFloat(ollamaTemperatureInput.value);
            const parsedHistory = parseInt(ollamaHistoryInput.value, 10);

            const newOllamaPrompt = ollamaSystemPromptTextarea ? ollamaSystemPromptTextarea.value : currentOllamaSystemPrompt;

            const newOllamaConfig = Object.assign({}, currentConfig.ollama, {
                active_server: normalizedServer || '',
                preferred_servers: existingServers,
                chat_model: ollamaModelSelect.value,
                temperature: Number.isFinite(parsedTemperature) ? parsedTemperature : (currentConfig?.ollama?.temperature ?? 0.7),
                history_length: Number.isFinite(parsedHistory) ? Math.max(1, parsedHistory) : (currentConfig?.ollama?.history_length ?? 4),
                stream: ollamaStreamCheckbox ? !!ollamaStreamCheckbox.checked : (currentConfig?.ollama?.stream !== false),
                add_wait_tag: ollamaAddWaitCheckbox ? !!ollamaAddWaitCheckbox.checked : (currentConfig?.ollama?.add_wait_tag ?? false),
                enable_startup_animation: ollamaStartupAnimCheckbox ? !!ollamaStartupAnimCheckbox.checked : (currentConfig?.ollama?.enable_startup_animation ?? true),
                enable_thinking_gesture: ollamaThinkingCheckbox ? !!ollamaThinkingCheckbox.checked : (currentConfig?.ollama?.enable_thinking_gesture ?? true),
                custom_prompt: ollamaPromptTextarea.value
            });
            delete newOllamaConfig.system_prompt;

            const newConfig = Object.assign({}, currentConfig, { ollama: newOllamaConfig });

            Promise.all([
                api.configSetUser(newConfig),
                api.setSystemPrompt(newOllamaPrompt, 'ollama')
            ]).then(() => {
                currentConfig = newConfig;
                currentOllamaSystemPrompt = newOllamaPrompt;
                updateOllamaServerOptions(newOllamaConfig.preferred_servers);

                if (currentStatus.is_running && currentStatus.mode === 'ollama') {
                    if (confirm("Paramètres Ollama enregistrés. Le chat Ollama est actif. Voulez-vous le redémarrer maintenant pour appliquer les nouveaux paramètres ?")) {
                        mainChatBtn.disabled = true;
                        mainChatBtn.innerHTML = '<span class="inline-spinner"></span>';
                        api.stopChat()
                            .then(() => api.startChat('ollama'))
                            .then(() => pollUntilChatReady(api, statusEl, mainChatBtn, updateStatus))
                            .catch(err => {
                                alert(`Erreur lors du redémarrage: ${err.message}`);
                                getStatus();
                            });
                    }
                } else {
                    alert('Paramètres Ollama enregistrés. Ils seront utilisés au prochain démarrage du chat Ollama.');
                }
            }).catch(err => {
                alert(`Erreur lors de l'enregistrement Ollama : ${err.message}`);
            }).finally(() => {
                saveOllamaBtn.innerHTML = defaultOllamaBtnLabel;
                saveOllamaBtn.disabled = false;
            });
        });
    }

    mainChatBtn.addEventListener('click', () => {
        mainChatBtn.disabled = true;
        mainChatBtn.innerHTML = '<span class="inline-spinner"></span>';

        if (currentStatus.is_running) {
            api.stopChat().then(getStatus).catch(err => {
                alert(`Erreur à l'arrêt: ${err.message}`);
                getStatus(); // Refresh status anyway
            });
        } else {
            const selectedRadio = document.querySelector('input[name="chat_mode"]:checked');
            const selectedMode = selectedRadio ? selectedRadio.value : 'basic';
            api.startChat(selectedMode).then(() => {
                if (selectedMode === 'gpt' || selectedMode === 'ollama') {
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
