export function render(root, api){
  const el = document.createElement('section');
  el.className = 'card span-12';
  el.innerHTML = `
    <style>
      .camera-controls { display: flex; align-items: flex-end; gap: 1rem; flex-wrap: wrap; }
      .camera-controls .btn-group { display: flex; gap: 0.5rem; }
      .camera-controls .control-group { padding-bottom: 0; }
      .camera-controls .control-group label { margin-bottom: 0.25rem; font-size: 0.9em; }
      .camera-controls .filler { flex-grow: 1; }
      #toggle-stream-btn i { font-size: 1.2em; vertical-align: -0.15em; margin-right: 0.25em; }
    </style>
    <div class="title">Caméra</div>
    <div class="camera-controls">
        <div class="btn-group">
            <button class="btn" id="toggle-stream-btn">
                <i class="bi bi-play-circle-fill"></i>
                <span>Démarrer le flux</span>
            </button>
        </div>
        <div class="control-group">
            <label for="camera-select">Source</label>
            <select id="camera-select">
                <option value="top">Haute (tête)</option>
                <option value="bottom">Basse (torse)</option>
            </select>
        </div>
        <div class="filler"></div>
        <a class="btn" href="/last_capture.png" target="_blank">Dernière capture vision</a>
    </div>
    <div class="row">
        <div class="imgbox" style="min-height: 240px; display: flex; align-items: center; justify-content: center; background: #eee; border-radius: 4px; margin-top: 1rem;">
            <img id="cam" alt="Le flux de la caméra apparaîtra ici" style="max-width: 100%; height: auto; display: none;"/>
            <span id="cam-alt-text" style="color: #666;">Le flux de la caméra apparaîtra ici</span>
            <span id="cam-error" style="color: red; display: none;"></span>
        </div>
    </div>
  `;
  root.appendChild(el);

  const toggleBtn = el.querySelector('#toggle-stream-btn');
  const toggleIcon = toggleBtn.querySelector('i');
  const toggleText = toggleBtn.querySelector('span');
  const img = el.querySelector('#cam');
  const errorSpan = el.querySelector('#cam-error');
  const altText = el.querySelector('#cam-alt-text');
  const cameraSelect = el.querySelector('#camera-select');

  let timer = null;
  let isStreaming = false;
  let errorCount = 0;
  const MAX_ERRORS = 8; // Allow for up to 2 seconds of errors (8 * 250ms)

  function updateToggleButton(streaming, loading = false) {
    isStreaming = streaming;
    toggleBtn.disabled = loading;
    if (loading) {
        toggleText.textContent = '...';
        return;
    }
    if (streaming) {
        toggleIcon.className = 'bi bi-stop-circle-fill';
        toggleText.textContent = 'Arrêter le flux';
        toggleBtn.classList.add('secondary');
    } else {
        toggleIcon.className = 'bi bi-play-circle-fill';
        toggleText.textContent = 'Démarrer le flux';
        toggleBtn.classList.remove('secondary');
    }
  }

  function stopPolling() {
      if (timer) clearTimeout(timer);
      timer = null;
      isStreaming = false; // Explicitly set streaming to false
      updateToggleButton(false);
  }

  function step() {
    if (!isStreaming || !el.isConnected) {
      return; // Stop the loop if not streaming or element is gone
    }
    img.src = '/cam.png?t=' + Date.now();
  }

  img.onload = () => {
    errorCount = 0; // Reset error count on success
    img.style.display = 'block';
    altText.style.display = 'none';
    errorSpan.style.display = 'none';

    // Schedule the next frame request
    if (isStreaming) {
        timer = setTimeout(step, 100); // 10fps
    }
  };

  img.onerror = () => {
    errorCount++;
    if (errorCount > MAX_ERRORS) {
        img.style.display = 'none';
        altText.style.display = 'none';
        errorSpan.style.display = 'inline';
        errorSpan.textContent = 'Erreur de chargement du flux. Le service caméra est-il démarré ?';
        stopPolling();
    } else {
        // Retry after a short delay
        if (isStreaming) {
            timer = setTimeout(step, 250);
        }
    }
  };

  toggleBtn.addEventListener('click', () => {
    updateToggleButton(isStreaming, true); // Set loading state

    if (isStreaming) {
        // --- STOP ---
        api.cameraStopStream().then(() => {
            stopPolling();
        }).catch(err => {
            alert('Erreur à l\'arrêt du flux: ' + err.message);
            updateToggleButton(true); // Restore button to streaming state
        });
    } else {
        // --- START ---
        api.cameraStartStream().then(() => {
            isStreaming = true;
            errorCount = 0;
            updateToggleButton(true);
            step(); // Start the chained polling
        }).catch(err => {
            errorSpan.textContent = `Erreur : ${err.message}`;
            errorSpan.style.display = 'inline';
            altText.style.display = 'none';
            updateToggleButton(false);
        });
    }
  });

  cameraSelect.addEventListener('change', () => {
    const selectedCamera = cameraSelect.value;
    stopPolling();
    img.style.display = 'none';
    altText.textContent = `Changement vers la caméra ${selectedCamera}...`;
    altText.style.display = 'inline';
    errorSpan.style.display = 'none';

    api.cameraSwitch({ camera: selectedCamera })
      .then(() => {
          altText.textContent = 'Caméra changée. Vous pouvez démarrer le flux.';
      })
      .catch(err => {
          errorSpan.textContent = 'Erreur changement de caméra: ' + err.message;
          errorSpan.style.display = 'inline';
          altText.style.display = 'none';
      });
  });

  function init() {
      api.cameraStatus().then(status => {
          cameraSelect.value = status.current_camera;
          updateToggleButton(status.is_streaming);
          if (status.is_streaming) {
              errorCount = 0;
              step();
          }
      }).catch(err => {
          errorSpan.textContent = "Impossible de récupérer l'état de la caméra.";
          errorSpan.style.display = 'inline';
          altText.style.display = 'none';
      });
  }

  init();

  // Cleanup
  const observer = new MutationObserver(() => {
    if (!document.body.contains(el)) {
      stopPolling();
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}
