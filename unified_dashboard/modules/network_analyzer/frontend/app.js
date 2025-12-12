const statusEl = document.getElementById("status");
const totalPacketsEl = document.getElementById("totalPackets");
const uniquePairsEl = document.getElementById("uniquePairs");
const scansEl = document.getElementById("scans");
const dnsQueriesEl = document.getElementById("dnsQueries");
const httpRequestsEl = document.getElementById("httpRequests").getElementsByTagName('tbody')[0];
const packetListTableBody = document.getElementById("packetListTable").getElementsByTagName('tbody')[0];
const packetDetailsDiv = document.getElementById("packetDetails");
const ifaceSelect = document.getElementById("iface");
const downloadLink = document.getElementById("downloadLink");

let protoChart, talkersChart, timelineChart;
let network; // Vis.js network instance
let allPackets = []; // Store detailed packets globally

// --- Utils ---
function setStatus(text) {
  statusEl.textContent = text;
}

// --- Interfaces ---
async function loadInterfaces() {
  const commonInterfaces = ["Wi-Fi", "Ethernet", "eth0", "en0", "any"];
  try {
    const res = await fetch("/tools/wireshark/api/interfaces");
    const data = await res.json();
    ifaceSelect.innerHTML = "";

    // 1. Add detected real interfaces first (objects with name/value)
    const apiInterfaces = data.interfaces || [];
    apiInterfaces.forEach(iface => {
      const opt = document.createElement("option");
      if (typeof iface === 'object') {
        opt.textContent = iface.name;
        opt.value = iface.value; // GUID for Windows
      } else {
        opt.textContent = iface;
        opt.value = iface;
      }
      ifaceSelect.appendChild(opt);
    });

    // 2. Add separator
    if (apiInterfaces.length > 0) {
      const sep = document.createElement("option");
      sep.disabled = true;
      sep.textContent = "──────────";
      ifaceSelect.appendChild(sep);
    }

    // 3. Add common defaults (as backup)
    commonInterfaces.forEach(name => {
      // Avoid duplicates if possible, though strict dedup against detailed names is hard.
      // We just add them for manual selection if needed.
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      ifaceSelect.appendChild(opt);
    });

  } catch (e) {
    console.error("Failed to load interfaces", e);
    // Fallback
    ifaceSelect.innerHTML = "";
    commonInterfaces.forEach(iface => {
      const opt = document.createElement("option");
      opt.value = iface;
      opt.textContent = iface;
      ifaceSelect.appendChild(opt);
    });
  }
}

// --- Rendering ---
function renderPacketList(packets) {
  packetListTableBody.innerHTML = ""; // Clear previous list
  packets.forEach((pkt, index) => {
    const row = packetListTableBody.insertRow();
    row.dataset.packetIndex = index; // Store index for detail lookup
    row.insertCell().textContent = pkt.frame_number;
    row.insertCell().textContent = new Date(pkt.time * 1000).toLocaleTimeString();
    row.insertCell().textContent = pkt.source;
    row.insertCell().textContent = pkt.destination;
    row.insertCell().textContent = pkt.protocol;
    row.insertCell().textContent = pkt.length;
    row.insertCell().textContent = pkt.info;
    row.addEventListener("click", () => renderPacketDetails(index));
  });
}

function renderPacketDetails(packetIndex) {
  const packet = allPackets[packetIndex];
  packetDetailsDiv.innerHTML = ""; // Clear previous details

  // Basic Packet Info
  const infoHtml = `
    <h4>Frame ${packet.frame_number}: ${packet.info}</h4>
    <p><strong>Time:</strong> ${new Date(packet.time * 1000).toLocaleString()}</p>
    <p><strong>Source:</strong> ${packet.source}</p>
    <p><strong>Destination:</strong> ${packet.destination}</p>
    <p><strong>Protocol:</strong> ${packet.protocol}</p>
    <p><strong>Length:</strong> ${packet.length} bytes</p>
  `;
  packetDetailsDiv.insertAdjacentHTML('beforeend', infoHtml);

  // Packet Bytes (Hex Dump)
  packetDetailsDiv.insertAdjacentHTML('beforeend', '<h4>Packet Bytes</h4><pre class="mono">' + packet.hex_dump + '</pre>');

  // Packet Layers
  const layersHtml = document.createElement('div');
  layersHtml.innerHTML = '<h4>Packet Layers</h4>';
  packet.layers.forEach(layer => {
    const layerHeader = document.createElement('div');
    layerHeader.className = 'layer-header';
    layerHeader.textContent = layer.name;
    const layerContent = document.createElement('div');
    layerContent.className = 'layer-content';
    layerContent.style.display = 'block';

    // Toggle functionality
    layerHeader.addEventListener('click', () => {
      layerContent.style.display = layerContent.style.display === 'none' ? 'block' : 'none';
    });

    const fieldsList = document.createElement('ul');
    for (const fieldName in layer.fields) {
      const fieldLi = document.createElement('li');
      fieldLi.textContent = `${fieldName}: ${layer.fields[fieldName]}`;
      fieldsList.appendChild(fieldLi);
    }
    layerContent.appendChild(fieldsList);
    layersHtml.appendChild(layerHeader);
    layersHtml.appendChild(layerContent);
  });
  packetDetailsDiv.appendChild(layersHtml);

  // Scroll to details
  packetDetailsDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderNetworkMap(conversations) {
  const container = document.getElementById('networkGraph');
  const nodes = new vis.DataSet();
  const edges = new vis.DataSet();
  const addedNodes = new Set();

  // Process conversations to build graph
  conversations.forEach(conv => {
    if (!addedNodes.has(conv.source)) {
      nodes.add({ id: conv.source, label: conv.source, shape: 'dot', size: 10, color: '#6ea8fe' });
      addedNodes.add(conv.source);
    }
    if (!addedNodes.has(conv.target)) {
      nodes.add({ id: conv.target, label: conv.target, shape: 'dot', size: 10, color: '#ffd166' });
      addedNodes.add(conv.target);
    }
    // Normalize weight for width
    const width = Math.min(10, Math.max(1, Math.log10(conv.value) + 1));
    edges.add({ from: conv.source, to: conv.target, width: width, color: { inherit: 'from', opacity: 0.6 } });
  });

  const data = { nodes: nodes, edges: edges };
  const options = {
    nodes: { font: { color: '#e8f0ff' } },
    physics: {
      stabilization: false,
      barnesHut: { gravitationalConstant: -8000, springConstant: 0.04, springLength: 95 }
    },
    interaction: { hover: true }
  };

  if (network) network.destroy();
  network = new vis.Network(container, data, options);
}

const securityFeedEl = document.getElementById("securityFeed");
// map instance
let mapInstance;
let markers = [];

// ... (existing Utils and Interfaces) ...

function renderMap(geoData) {
  if (!geoData || geoData.length === 0) return;

  // Init map if needed
  if (!mapInstance) {
    mapInstance = L.map('map').setView([20, 0], 2);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19
    }).addTo(mapInstance);
  }

  // Clear old markers
  markers.forEach(m => mapInstance.removeLayer(m));
  markers = [];

  // Add new markers
  geoData.forEach(item => {
    const marker = L.marker([item.lat, item.lon]).addTo(mapInstance);
    marker.bindPopup(`<b>${item.ip}</b><br>${item.city}, ${item.country}`);
    markers.push(marker);
  });
}

function renderAlerts(alerts) {
  securityFeedEl.innerHTML = "";
  if (!alerts || alerts.length === 0) {
    securityFeedEl.innerHTML = '<div class="muted">No active threats detected.</div>';
    return;
  }

  alerts.forEach(alert => {
    const div = document.createElement("div");
    div.className = "alert-item";

    const typeBadge = alert.type.includes("Scan") ? "med" : "high";

    div.innerHTML = `
            <div>
                <span class="badge ${typeBadge}">${alert.type}</span>
                <span style="margin-left:8px">${alert.msg}</span>
            </div>
            <span class="muted" style="font-size:11px">Frame: ${alert.frame}</span>
        `;
    securityFeedEl.appendChild(div);
  });
}

function render(result) {
  // Summary
  totalPacketsEl.textContent = result.total_packets ?? "0";
  uniquePairsEl.textContent = result.unique_ip_pairs ?? "0";

  // Render Alerts
  renderAlerts(result.alerts);

  // Render Map
  // We need to delay map rendering slightly to ensure container is visible/sized
  setTimeout(() => renderMap(result.geoip), 100);

  // DNS Queries
  dnsQueriesEl.innerHTML = "";
  const queries = result.dns_queries || [];
  if (queries.length === 0) {
    const li = document.createElement("li");
    li.textContent = "None detected";
    dnsQueriesEl.appendChild(li);
  } else {
    queries.forEach(q => {
      const li = document.createElement("li");
      li.textContent = q;
      dnsQueriesEl.appendChild(li);
    });
  }

  // HTTP Requests
  httpRequestsEl.innerHTML = "";
  const requests = result.http_requests || [];
  if (requests.length === 0) {
    const row = httpRequestsEl.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 3;
    cell.textContent = "None detected";
    cell.style.textAlign = "center";
  } else {
    requests.forEach(r => {
      const row = httpRequestsEl.insertRow();
      row.insertCell().textContent = r.method;
      row.insertCell().textContent = r.host;
      row.insertCell().textContent = r.uri;
    });
  }

  // Protocol chart
  const protoStats = result.protocol_stats || {};
  const pLabels = Object.keys(protoStats);
  const pValues = Object.values(protoStats);

  if (protoChart) protoChart.destroy();
  protoChart = new Chart(document.getElementById("protoChart").getContext("2d"), {
    type: "doughnut",
    data: {
      labels: pLabels,
      datasets: [{
        data: pValues,
        backgroundColor: ['#6ea8fe', '#ffd166', '#ff6b6b', '#51cf66', '#cc5de8', '#845ef7']
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'right', labels: { color: '#8aa0bf' } } }
    }
  });

  // Top talkers chart
  const talkers = result.top_talkers || [];
  const tLabels = talkers.map(t => t.ip);
  const tValues = talkers.map(t => t.bytes);

  if (talkersChart) talkersChart.destroy();
  talkersChart = new Chart(document.getElementById("talkersChart").getContext("2d"), {
    type: "bar",
    data: {
      labels: tLabels,
      datasets: [{
        label: "Bytes",
        data: tValues,
        backgroundColor: '#6ea8fe'
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      scales: {
        x: { ticks: { color: '#8aa0bf' }, grid: { color: '#1f2a44' } },
        y: { ticks: { color: '#8aa0bf' }, grid: { display: false } }
      },
      plugins: { legend: { display: false } }
    }
  });

  // Timeline Chart
  const timelineData = result.timeline || [];
  const timeLabels = timelineData.map(d => new Date(d.time * 1000).toLocaleTimeString());
  const timeCounts = timelineData.map(d => d.count);

  if (timelineChart) timelineChart.destroy();
  timelineChart = new Chart(document.getElementById("timelineChart").getContext("2d"), {
    type: "line",
    data: {
      labels: timeLabels,
      datasets: [{
        label: "Packets/sec",
        data: timeCounts,
        borderColor: '#51cf66',
        backgroundColor: 'rgba(81, 207, 102, 0.1)',
        fill: true,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { display: false },
        y: { ticks: { color: '#8aa0bf' }, grid: { color: '#1f2a44' } }
      },
      plugins: { legend: { display: false } }
    }
  });

  // Network Graph
  renderNetworkMap(result.conversations || []);

  // Render detailed packets
  allPackets = result.detailed_packets || [];
  renderPacketList(allPackets);
  packetDetailsDiv.innerHTML = '<p class="muted">Select a packet from the list above to view its details.</p>';
}

// --- API Calls ---
async function analyzePCAP(file) {
  const form = new FormData();
  form.append("pcap", file);
  setStatus("Uploading & analyzing…");
  downloadLink.style.display = "none"; // Hide download link for uploads
  try {
    const res = await fetch("/tools/wireshark/api/analyze", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Analysis failed");
    setStatus("Done");
    render(data);
  } catch (e) {
    setStatus("Error: " + e.message);
  }
}

async function liveCapture(interfaceName, count) {
  setStatus("Capturing…");
  downloadLink.style.display = "none";
  try {
    const res = await fetch("/tools/wireshark/api/live-capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interface: interfaceName, packet_count: count, action: "analyze" })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Capture failed");
    setStatus("Done");
    render(data);
  } catch (e) {
    setStatus("Error: " + e.message);
  }
}

async function saveCapture(interfaceName, count) {
  setStatus("Capturing and saving…");
  downloadLink.style.display = "none";
  try {
    const res = await fetch("/tools/wireshark/api/live-capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interface: interfaceName, packet_count: count, action: "save" })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Save failed");
    setStatus(data.message);

    // Show download link
    if (data.filename) {
      downloadLink.href = `/tools/wireshark/api/download/${data.filename}`;
      downloadLink.download = data.filename;
      downloadLink.style.display = "inline-flex";
    }
  } catch (e) {
    setStatus("Error: " + e.message);
  }
}

// --- Event Listeners ---
document.getElementById("analyzeBtn").addEventListener("click", () => {
  const file = document.getElementById("pcap").files[0];
  if (!file) { alert("Choose a .pcap or .pcapng file first."); return; }
  analyzePCAP(file);
});

document.getElementById("liveBtn").addEventListener("click", () => {
  const iface = document.getElementById("iface").value;
  const count = parseInt(document.getElementById("count").value || "30", 10);
  liveCapture(iface, count);
});

document.getElementById("saveBtn").addEventListener("click", () => {
  const iface = document.getElementById("iface").value;
  const count = parseInt(document.getElementById("count").value || "30", 10);
  saveCapture(iface, count);
});

// Init
loadInterfaces();