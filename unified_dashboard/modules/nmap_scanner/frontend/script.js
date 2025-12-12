const socket = io();
let network = null;
let networkData = { nodes: new vis.DataSet(), edges: new vis.DataSet() };
let globe = null; // Globe instance
let globeData = []; // Points for globe
let sentryActive = false;
let currentScanResults = [];

// --- SOUND FX ---
const sfx = {
  beep: new Howl({ src: ['https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3'], volume: 0.5 }), // Generic beep
  alert: new Howl({ src: ['https://assets.mixkit.co/active_storage/sfx/995/995-preview.mp3'], volume: 0.8 }), // Alarm
  scan: new Howl({ src: ['https://assets.mixkit.co/active_storage/sfx/2044/2044-preview.mp3'], volume: 0.3 }), // Scanning drone
  success: new Howl({ src: ['https://assets.mixkit.co/active_storage/sfx/1118/1118-preview.mp3'], volume: 0.6 }) // Success chime
};

// --- Socket Events ---

socket.on('connect', () => {
  document.getElementById('connection-status').innerText = 'CONNECTED [SECURE]';
  document.getElementById('connection-status').style.color = '#00ff41';
});

socket.on('disconnect', () => {
  document.getElementById('connection-status').innerText = 'OFFLINE';
  document.getElementById('connection-status').style.color = '#ff003c';
  sfx.alert.play();
});

socket.on('scan_status', (data) => {
  console.log('[DEBUG] Received scan_status:', data);
  if (data.status === 'running') {
    log(`>> ${data.message}`, 'info');
  } else if (data.status === 'completed') {
    const count = data.results ? data.results.length : 0;
    if (count === 0) {
      log('>> SCAN COMPLETED. NO HOSTS FOUND.', 'warning');
      log('>> HINT: Try scanning a subnet (e.g. 192.168.1.0/24) or check firewall.', 'info');
      sfx.alert.play();
    } else {
      log(`>> SCAN COMPLETED. Found ${count} active hosts.`, 'success');
      sfx.success.play();
    }
    updateMap(data.results || []);
  } else if (data.status === 'error') {
    log(`!! ERROR: ${data.message}`, 'error');
    sfx.alert.play();
  }
});

socket.on('sentry_alert', (data) => {
  log(`!! SENTRY ALERT: ${data.title} - ${data.message}`, 'error');
  sfx.alert.play();
  alert(`[SENTRY] ${data.title}\n${data.message}`);
});

// --- Core Functions ---

async function startScan() {
  sfx.beep.play();
  const target = document.getElementById('target').value;
  const type = document.getElementById('scan-type').value;
  const extra = document.getElementById('extra').value;

  log(`>> INITIALIZING ${type.toUpperCase()} SCAN...`, 'info');
  sfx.scan.play();

  if (type === 'network') {
    networkData.nodes.clear();
    networkData.nodes.add({ id: 'Router', label: 'GATEWAY', shape: 'hexagon', color: '#ffb300', size: 30 });
    networkData.edges.clear();
  }

  try {
    const response = await fetch('/tools/nmap/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target, scan_type: type, extra })
    });
    const data = await response.json();
    if (data.error) log(`!! ERROR: ${data.error}`, 'error');
  } catch (e) {
    log(`!! NETWORK ERROR: ${e}`, 'error');
  }
}

async function toggleSentry() {
  sfx.beep.play();
  sentryActive = !sentryActive;
  const btn = document.getElementById('btn-sentry');
  const target = document.getElementById('target').value;

  if (sentryActive) {
    btn.innerText = 'DISABLE MONITORING';
    btn.style.boxShadow = '0 0 15px #ffb300';
    log('>> MONITORING MODE ACTIVATED. Watching for new devices...', 'warning');
    await fetch('/tools/nmap/sentry/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target })
    });
  } else {
    btn.innerText = 'ENABLE MONITORING';
    btn.style.boxShadow = 'none';
    log('>> MONITORING MODE DEACTIVATED.', 'info');
    await fetch('/tools/nmap/sentry/stop', { method: 'POST' });
  }
}

async function generateReport() {
  sfx.beep.play();
  log('>> GENERATING REPORT...', 'info');
  // Using current data hack again
  if (currentScanResults.length === 0) {
    log('!! NO DATA TO REPORT', 'error');
    return;
  }

  // In real app, trigger backend to generate from memory
  const response = await fetch('/tools/nmap/report/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ results: currentScanResults })
  });

  if (response.ok) {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = "report.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    log('>> REPORT DOWNLOADED', 'success');
  }
}

async function runBreachAudit(ip, port, serviceName) {
  if (!confirm(`WARNING: You are about to run a credential audit against ${ip}:${port}.\n\nThis will check for weak passwords like 'admin/admin'.\n\nOnly do this on systems you own. Continue?`)) return;

  log(`>> STARTING PASSWORD AUDIT ON ${ip}:${port}...`, 'warning');
  sfx.scan.play();

  const response = await fetch('/tools/nmap/breach_audit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip, port, service: serviceName })
  });
  const data = await response.json();
  log(`>> AUDIT RESULT: ${data.result}`, data.result.includes('FOUND') ? 'error' : 'success');
  if (data.result.includes('FOUND')) sfx.alert.play();
}

async function checkGeoIP(ip) {
  log(`>> RESOLVING LOCATION FOR ${ip}...`, 'info');
  const response = await fetch('/tools/nmap/geoip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip })
  });
  const data = await response.json();
  if (data.location) {
    log(`>> LOCATION IDENTIFIED: ${data.location.city}, ${data.location.country}`, 'success');
    // Add to globe
    globeData.push({
      lat: data.location.lat,
      lng: data.location.lon,
      size: 0.5,
      color: 'red',
      name: ip
    });
    updateGlobe();
    switchVis('globe'); // Auto switch to show off
  } else {
    log('>> LOCATION UNKNOWN (Local IP?)', 'info');
  }
}

// --- Visualizers ---

function updateMap(hosts) {
  currentScanResults = hosts;
  const updates = [];
  const edges = [];

  if (!networkData.nodes.get('Router')) {
    updates.push({ id: 'Router', label: 'GATEWAY', shape: 'hexagon', color: '#ffb300', size: 30 });
  }

  hosts.forEach(host => {
    let color = '#00d2ff';
    if (host.risk_score > 50) color = '#ff003c';
    else if (host.risk_score > 20) color = '#ffb300';

    updates.push({
      id: host.ip,
      label: `${host.ip}\n${host.vendor || 'Unknown'}`,
      color: color,
      shape: 'dot',
      title: JSON.stringify(host, null, 2)
    });

    edges.push({ from: 'Router', to: host.ip });

    // Auto-check GeoIP if external (hacky heuristic)
    if (!host.ip.startsWith('192') && !host.ip.startsWith('127') && !host.ip.startsWith('10')) {
      checkGeoIP(host.ip);
    }
  });

  networkData.nodes.update(updates);
  networkData.edges.update(edges);
}

function updateGlobe() {
  if (!globe) initGlobe();
  globe.pointsData(globeData);
}

function initMap() {
  const container = document.getElementById('mynetwork');
  const options = {
    nodes: { font: { color: '#00ff41', face: 'Share Tech Mono' }, borderWidth: 2, shadow: true },
    edges: { color: '#008F11', smooth: true },
    physics: { stabilization: false, barnesHut: { gravitationalConstant: -8000 } }
  };
  network = new vis.Network(container, networkData, options);

  // Add Gateway immediately so map isn't empty on load
  if (!networkData.nodes.get('Router')) {
    networkData.nodes.add({ id: 'Router', label: 'GATEWAY', shape: 'hexagon', color: '#ffb300', size: 30 });
  }

  network.on('click', function (params) {
    if (params.nodes.length > 0 && params.nodes[0] !== 'Router') showDetails(params.nodes[0]);
  });
}

function initGlobe() {
  const elem = document.getElementById('globe-container');
  globe = Globe()
    .globeImageUrl('//unpkg.com/three-globe/example/img/earth-dark.jpg')
    .bumpImageUrl('//unpkg.com/three-globe/example/img/earth-topology.png')
    .backgroundImageUrl('//unpkg.com/three-globe/example/img/night-sky.png')
    .pointAltitude(0.1)
    .pointColor('color')
    .pointRadius(0.5)
    .pointsData(globeData)
    (elem);

  // Fix resize issue by forcing layout logic if needed? 
  // Usually Globe works fine if container has size.
}

function switchVis(tab) {
  document.querySelectorAll('.vis-tabs button').forEach(b => b.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');

  if (tab === 'map') {
    document.getElementById('mynetwork').classList.remove('hidden');
    document.getElementById('globe-container').classList.add('hidden');
  } else {
    document.getElementById('mynetwork').classList.add('hidden');
    document.getElementById('globe-container').classList.remove('hidden');
    if (!globe) initGlobe();
  }
  sfx.beep.play();
}

function log(msg, type = 'info') {
  const div = document.getElementById('output');
  const line = document.createElement('div');
  line.className = `log-line ${type}`;
  line.innerText = `[${new Date().toLocaleTimeString()}] ${msg}`;
  div.appendChild(line);
  div.scrollTop = div.scrollHeight;
}

function showDetails(ip) {
  const host = currentScanResults.find(h => h.ip === ip);
  if (!host) return;

  const modal = document.getElementById('details-modal');
  const body = document.getElementById('modal-body');

  document.getElementById('modal-title').innerText = `HOST_INTEL: ${ip}`;

  // Parse OS if available
  let osInfo = 'Unknown';
  if (host.os && host.os.length > 0) {
    // Get best match
    const match = host.os[0];
    osInfo = `${match.name} (${match.accuracy}% Accuracy)`;
  }

  let html = `
        <p><strong>VENDOR:</strong> ${host.vendor || 'Unknown'}</p>
        <p><strong>OS:</strong> ${osInfo}</p>
        <p><strong>MAC:</strong> ${host.mac || 'Unknown'}</p>
        <p><strong>RISK SCORE:</strong> <span style="color:${host.risk_score > 50 ? 'red' : 'lightgreen'}">${host.risk_score || 0}</span>/100</p>
        <button onclick="checkGeoIP('${ip}')" class="btn-secondary" style="width:50%">LOCATE ON GLOBE</button>
        <hr style="border-color: #008F11">
        <h4>OPEN_PORTS:</h4>
        <ul>
    `;

  if (host.ports) {
    for (const [port, info] of Object.entries(host.ports)) {
      html += `
                <li>
                    <strong>${port} (${info.name}):</strong> ${info.state} 
                    <button class="btn-warning" style="font-size:0.7em; width:auto; padding:2px 5px;" onclick="runBreachAudit('${ip}', ${port}, '${info.name}')">AUDIT_BREACH</button>
                    <br><small style="color:#aaa"><i>${info.explanation || ''}</i></small>
                </li>`;
    }
  } else {
    html += "<li>No open ports detected.</li>";
  }
  html += "</ul>";
  body.innerHTML = html;
  modal.classList.remove('hidden');
  sfx.beep.play();
}

function closeModal() {
  document.getElementById('details-modal').classList.add('hidden');
}

window.onload = initMap;
