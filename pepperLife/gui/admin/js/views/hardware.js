import {api} from '../api.js';

// Helper to render the top-level summary
function renderKVs(data) {
    const items = [];
    if (data.system) {
        items.push(['Version système', data.system.version]);
        items.push(['Nom du robot', data.system.robot]);
    }
    if (data.battery) {
        items.push(['Charge batterie', `${data.battery.charge}%`]);
    }
    if (data.motion) {
        items.push(['Posture', data.motion.awake ? 'Debout' : 'En veille']);
    }
    if (data.audio) {
        items.push(['Langue (TTS)', data.audio.language]);
    }
    return items.map(([k,v]) => `<div class="kv"><div class="k">${k}</div><div class="v">${v !== null && v !== undefined ? v : 'N/A'}</div></div>`).join('');
}

// Main render function for the hardware view
export function render(root){
  const box = document.createElement('section');
  box.className='card span-12';
  box.innerHTML = `
    <div class="title">Hardware Summary</div>
    <div class="kvs" id="kvs-hardware">Chargement...</div>

    <!-- Devices Table -->
    <div class="title" style="margin-top: 20px;">Devices</div>
    <div style="overflow-x: auto;"><table class="table">
        <thead><tr>
            <th>Device</th><th>BoardId</th><th>Version</th><th>Bootloader</th><th>Bus</th><th>Type</th><th>Error</th><th>Ack</th><th>Nack</th><th>Address</th><th>Available</th>
        </tr></thead>
        <tbody id="devices-tbody"><tr><td colspan="11">Chargement...</td></tr></tbody>
    </table></div>

    <!-- Joints Table -->
    <div class="title" style="margin-top: 20px;">Joints</div>
    <div style="overflow-x: auto;"><table class="table">
        <thead><tr>
            <th>Joint</th><th>Temp (°C)</th><th>Position (rad)</th><th>Actuator (rad)</th><th>Stiffness</th><th>Current (A)</th>
        </tr></thead>
        <tbody id="joints-tbody"><tr><td colspan="6">Chargement...</td></tr></tbody>
    </table></div>

    <!-- Config Table -->
    <div class="title" style="margin-top: 20px;">Robot Configuration</div>
    <div style="overflow-x: auto;"><table class="table">
        <thead><tr><th>Key</th><th>Value</th></tr></thead>
        <tbody id="config-tbody"><tr><td colspan="2">Chargement...</td></tr></tbody>
    </table></div>

    <!-- Head Temp Table -->
    <div class="title" style="margin-top: 20px;">Head CPU Temperature</div>
    <div style="overflow-x: auto;"><table class="table">
        <thead><tr><th>Sensor</th><th>Temperature (°C)</th></tr></thead>
        <tbody id="head-temp-tbody"><tr><td colspan="2">Chargement...</td></tr></tbody>
    </table></div>
  `;
  root.appendChild(box);

  const kvs = box.querySelector('#kvs-hardware');
  const jointsTbody = box.querySelector('#joints-tbody');
  const devicesTbody = box.querySelector('#devices-tbody');
  const configTbody = box.querySelector('#config-tbody');
  const headTempTbody = box.querySelector('#head-temp-tbody');

  async function refresh() {
      try {
        // High-level info first
        const d_info = await api.hardwareInfo();
        kvs.innerHTML = renderKVs(d_info);

        // Then detailed info
        const d_details = await api.hardwareDetails();
        
        // Render Devices
        if (d_details.devices && !d_details.devices.error) {
            devicesTbody.innerHTML = Object.entries(d_details.devices).map(([name, data]) => `
                <tr>
                    <td>${name}</td>
                    <td>${data.BoardId || 'N/A'}</td>
                    <td>${data.Version || 'N/A'}</td>
                    <td>${data.Bootloader || 'N/A'}</td>
                    <td>${data.Bus || 'N/A'}</td>
                    <td>${data.Type || 'N/A'}</td>
                    <td>${data.Error || 'N/A'}</td>
                    <td>${data.Ack || 'N/A'}</td>
                    <td>${data.Nack || 'N/A'}</td>
                    <td>${data.Address || 'N/A'}</td>
                    <td>${data.Available?.toFixed(2) || 'N/A'}</td>
                </tr>
            `).join('');
        } else {
            devicesTbody.innerHTML = `<tr><td colspan="11">${d_details.devices?.error || 'Données non disponibles'}</td></tr>`;
        }

        // Render Joints
        if (d_details.joints && !d_details.joints.error) {
            jointsTbody.innerHTML = Object.entries(d_details.joints).map(([name, data]) => `
                <tr>
                    <td>${name}</td>
                    <td>${data.Temperature?.toFixed(1) || 'N/A'}</td>
                    <td>${data.PositionSensor?.toFixed(3) || 'N/A'}</td>
                    <td>${data.PositionActuator?.toFixed(3) || 'N/A'}</td>
                    <td>${data.Stiffness?.toFixed(2) || 'N/A'}</td>
                    <td>${data.ElectricCurrent?.toFixed(3) || 'N/A'}</td>
                </tr>
            `).join('');
        } else {
            jointsTbody.innerHTML = `<tr><td colspan="6">${d_details.joints?.error || 'Données non disponibles'}</td></tr>`;
        }

        // Render Config
        if (d_details.config && !d_details.config.error) {
            configTbody.innerHTML = Object.entries(d_details.config).map(([key, value]) => `
                <tr><td>${key}</td><td>${value}</td></tr>
            `).join('');
        } else {
            configTbody.innerHTML = `<tr><td colspan="2">${d_details.config?.error || 'Données non disponibles'}</td></tr>`;
        }

        // Render Head Temp
        if (d_details.head_temp && !d_details.head_temp.error) {
            headTempTbody.innerHTML = Object.entries(d_details.head_temp).map(([key, value]) => `
                <tr><td>${key}</td><td>${value?.toFixed(1) || 'N/A'}</td></tr>
            `).join('');
        } else {
            headTempTbody.innerHTML = `<tr><td colspan="2">${d_details.head_temp?.error || 'Données non disponibles'}</td></tr>`;
        }

      } catch(e) {
        kvs.innerHTML = `<div class="kv"><div class="k">Erreur</div><div class="v">${e.message || e}</div></div>`;
        const errorRow = `<td colspan="11">Erreur: ${e.message || e}</td>`;
        devicesTbody.innerHTML = `<tr>${errorRow}</tr>`;
        jointsTbody.innerHTML = `<tr>${errorRow}</tr>`;
        configTbody.innerHTML = `<tr>${errorRow}</tr>`;
        headTempTbody.innerHTML = `<tr>${errorRow}</tr>`;
      }
  }
  
  refresh();
}