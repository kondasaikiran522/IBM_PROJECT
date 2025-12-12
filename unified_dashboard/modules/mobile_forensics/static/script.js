// Global state
let currentJob = null;
let statusCheckInterval = null;

// Utility functions
function showAlert(message, type = 'error') {
  const alertEl = document.getElementById(type === 'error' ? 'errorAlert' : 'successAlert');
  alertEl.textContent = message;
  alertEl.style.display = 'block';

  // Animation reset
  alertEl.style.animation = 'none';
  alertEl.offsetHeight; /* trigger reflow */
  alertEl.style.animation = 'fadeIn 0.3s';

  setTimeout(() => {
    alertEl.style.display = 'none';
  }, 5000);
}

function updateDeviceStatus() {
  fetch('/tools/mobile/device-status')
    .then(response => response.json())
    .then(data => {
      const adbStatus = document.getElementById('adbStatus');
      const deviceStatus = document.getElementById('deviceStatus');
      const authStatus = document.getElementById('authStatus');

      // Update Text
      adbStatus.textContent = data.adb_available ? 'ONLINE' : 'OFFLINE';
      deviceStatus.textContent = data.device_connected ? 'CONNECTED' : 'DISCONNECTED';
      authStatus.textContent = data.authorized ? 'AUTHORIZED' : 'UNAUTHORIZED';

      // Update Classes (Green/Red badges)
      adbStatus.className = `status-badge ${data.adb_available ? 'connected' : 'disconnected'}`;
      deviceStatus.className = `status-badge ${data.device_connected ? 'connected' : 'disconnected'}`;
      authStatus.className = `status-badge ${data.authorized ? 'connected' : 'disconnected'}`;
    })
    .catch(error => {
      console.error('Error checking device status:', error);
      // Don't show alert constantly for background checks
    });
}

function updateProgressBar(percent, message) {
  const progressSection = document.getElementById('progressSection');
  const progressFill = document.getElementById('progressFill');
  const progressText = document.getElementById('progressText');
  const percentText = document.getElementById('percentText');
  const statusIndicator = document.getElementById('statusIndicator');

  progressSection.style.display = 'block';
  progressFill.style.width = `${Math.max(0, Math.min(100, percent || 0))}%`;

  if (progressText) progressText.textContent = message || '';
  if (percentText) percentText.textContent = `${percent}%`;

  if (percent >= 100) {
    if (statusIndicator) statusIndicator.innerHTML = '<span style="color:var(--success)">Complete</span>';
    // Success State for Bar
    progressFill.style.background = 'var(--success)';
  } else if (percent > 0) {
    if (statusIndicator) statusIndicator.innerHTML = '<span style="color:var(--primary)">Processing...</span>';
    progressFill.style.background = 'linear-gradient(90deg, var(--primary), var(--secondary))';
  } else {
    if (statusIndicator) statusIndicator.textContent = 'Initializing...';
  }
}

function updateStatistics(result) {
  const statsGrid = document.getElementById('statsGrid');
  const callsCount = document.getElementById('callsCount');
  const smsCount = document.getElementById('smsCount');
  const contactsCount = document.getElementById('contactsCount');
  const photosCount = document.getElementById('photosCount');
  const appsCount = document.getElementById('appsCount');
  const browserCount = document.getElementById('browserCount');

  if (result && Object.keys(result).length > 0) {
    statsGrid.style.display = 'grid';

    callsCount.textContent = result.calls ? result.calls.length : 0;
    smsCount.textContent = result.sms ? result.sms.length : 0;
    contactsCount.textContent = result.contacts ? result.contacts.length : 0;
    photosCount.textContent = result.photos_list ? result.photos_list.length : 0;
    appsCount.textContent = result.apps ? result.apps.length : 0;
    browserCount.textContent = result.browser ? result.browser.length : 0;
  } else {
    statsGrid.style.display = 'none';
  }
}

// Chart Global Refs
let callsChartInstance = null;
let dataChartInstance = null;

// Common chart options for Dark Theme
const commonChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  color: '#94a3b8', // text-muted
  borderColor: 'rgba(255,255,255,0.1)',
  plugins: {
    legend: {
      labels: {
        color: '#f1f5f9', // text-main
        font: { family: 'Inter' }
      }
    },
    title: {
      display: true,
      color: '#f1f5f9',
      font: { size: 16, family: 'Inter', weight: '600' }
    }
  },
  scales: {
    x: {
      grid: { color: 'rgba(255,255,255,0.05)' },
      ticks: { color: '#94a3b8' }
    },
    y: {
      grid: { color: 'rgba(255,255,255,0.05)' },
      ticks: { color: '#94a3b8' },
      beginAtZero: true
    }
  }
};

function renderDashboard(result) {
  const section = document.getElementById('dashboardSection');
  if (!result || Object.keys(result).length === 0) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';

  // 1. Calls Analysis (Pie/Doughnut)
  const calls = result.calls || [];
  const callTypes = {};
  calls.forEach(c => {
    let t = c.type || 'Unknown';
    callTypes[t] = (callTypes[t] || 0) + 1;
  });

  const ctxCalls = document.getElementById('callsChart').getContext('2d');
  if (callsChartInstance) callsChartInstance.destroy();

  callsChartInstance = new Chart(ctxCalls, {
    type: 'doughnut',
    data: {
      labels: Object.keys(callTypes),
      datasets: [{
        label: 'Call Distribution',
        data: Object.values(callTypes),
        backgroundColor: [
          '#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444'
        ],
        borderWidth: 0
      }]
    },
    options: {
      ...commonChartOptions,
      scales: {}, // remove scales for doughnut
      plugins: {
        ...commonChartOptions.plugins,
        title: { text: 'Call Log Types', color: '#f1f5f9' }
      }
    }
  });

  // 2. Data Distribution (Bar)
  const labels = [];
  const counts = [];

  if (result.sms) { labels.push('SMS'); counts.push(result.sms.length); }
  if (result.contacts) { labels.push('Contacts'); counts.push(result.contacts.length); }
  if (result.photos_list) { labels.push('Photos'); counts.push(result.photos_list.length); }
  if (result.apps) { labels.push('Apps'); counts.push(result.apps.length); }
  if (result.browser) { labels.push('Browser'); counts.push(result.browser.length); }

  const ctxData = document.getElementById('dataChart').getContext('2d');
  if (dataChartInstance) dataChartInstance.destroy();

  dataChartInstance = new Chart(ctxData, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Items Extracted',
        data: counts,
        backgroundColor: '#3b82f6',
        borderRadius: 4
      }]
    },
    options: {
      ...commonChartOptions,
      plugins: {
        ...commonChartOptions.plugins,
        title: { text: 'Artifact Volume', color: '#f1f5f9' }
      }
    }
  });
}

function renderResults(data) {
  const container = document.getElementById('tablesContainer');
  const emptyState = document.getElementById('emptyState');
  container.innerHTML = '';

  if (!data || Object.keys(data).length === 0) {
    emptyState.style.display = 'block';
    return;
  }

  emptyState.style.display = 'none';

  for (const [key, items] of Object.entries(data)) {
    // Skip internal keys or empty
    if (!items || items.length === 0 || key === 'photos_pull_log') continue;

    // Create Section Divider
    const section = document.createElement('div');
    section.className = 'section-divider';
    section.innerHTML = `<i class="fas fa-folder"></i> ${key.toUpperCase()} <span style="font-size:0.8em; opacity:0.6; margin-left:5px;">(${items.length})</span>`;

    // Create Table Wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'table-container';

    const table = document.createElement('table');
    table.className = 'modern-table';

    // Headers
    const firstItem = items[0];
    const headers = Object.keys(firstItem || {});

    const thead = document.createElement('thead');
    const trHead = document.createElement('tr');
    headers.forEach(h => {
      const th = document.createElement('th');
      th.textContent = h.replace(/_/g, ' ');
      trHead.appendChild(th);
    });
    thead.appendChild(trHead);
    table.appendChild(thead);

    // Body
    const tbody = document.createElement('tbody');
    items.slice(0, 100).forEach(item => { // Limit render to 100 for performance in DOM
      const tr = document.createElement('tr');
      headers.forEach(h => {
        const td = document.createElement('td');
        let val = item[h];
        if (typeof val === 'object') val = JSON.stringify(val);
        // Truncate long text
        if (val && val.length > 50 && !h.includes("link") && !h.includes("url")) {
          val = val.substring(0, 50) + "...";
        }
        td.textContent = val || '-';
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    wrapper.appendChild(table);
    container.appendChild(section);
    container.appendChild(wrapper);
  }
}

function setupSearch() {
  const input = document.getElementById('globalSearch');
  input.addEventListener('keyup', function () {
    const filter = this.value.toLowerCase();
    const rows = document.querySelectorAll('.modern-table tbody tr');
    let hasVisible = false;

    rows.forEach(row => {
      const text = row.textContent.toLowerCase();
      if (text.includes(filter)) {
        row.style.display = '';
        hasVisible = true;
      } else {
        row.style.display = 'none';
      }
    });

    const empty = document.getElementById('emptyState');
    if (!hasVisible && filter.length > 0) {
      // We could show a custom "no results" msg here or just rely on the table being empty
    }
  });
}

// API functions
async function postStart(form) {
  const fd = new FormData(form);
  const res = await fetch("/tools/mobile/start", { method: "POST", body: fd });
  return res;
}

async function pollProgress(onUpdate) {
  while (true) {
    try {
      const r = await fetch("/tools/mobile/progress");
      const j = await r.json();
      onUpdate(j);

      if (j.error) {
        throw new Error(j.error);
      }

      if (!j.running) {
        return j;
      }

      await new Promise(resolve => setTimeout(resolve, 600));
    } catch (error) {
      console.error('Progress polling error:', error);
      throw error;
    }
  }
}

// Event handlers
document.addEventListener('DOMContentLoaded', function () {
  // Initial device status check
  updateDeviceStatus();
  setupSearch();

  // Set up periodic status checks
  statusCheckInterval = setInterval(updateDeviceStatus, 5000); // Check every 5 seconds for snappier feeling

  // Form submission
  document.getElementById("form").addEventListener("submit", async function (e) {
    e.preventDefault();

    const startBtn = document.getElementById('startBtn');
    const output = document.getElementById('output');
    const exportBtn = document.getElementById('exportBtn');
    const downloadSection = document.getElementById('downloadSection');

    // Reset UI
    output.value = "";
    exportBtn.style.display = 'none';
    downloadSection.style.display = 'none';
    startBtn.disabled = true;
    startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> INITIALIZING...';

    // Clear previous results
    document.getElementById('statsGrid').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'none';
    document.getElementById('tablesContainer').innerHTML = '';

    try {
      const res = await postStart(e.target);
      if (!res.ok) {
        const j = await res.json().catch(() => ({ message: "Unknown error" }));
        throw new Error(j.message || `HTTP ${res.status}`);
      }

      updateProgressBar(0, "Establishing connection...");

      // Poll for progress
      const finalResult = await pollProgress((j) => {
        updateProgressBar(j.percent, j.message);
      });

      // Fetch final result
      const r = await fetch("/tools/mobile/result");
      const jr = await r.json();

      if (jr.error) {
        throw new Error(jr.error);
      }

      // Store raw JSON in hidden textarea
      const formattedOutput = JSON.stringify(jr.result, null, 2);
      document.getElementById('output').value = formattedOutput;

      // Render Dashboard & Tables
      updateStatistics(jr.result);
      renderDashboard(jr.result);
      renderResults(jr.result);

      // Show export button
      exportBtn.style.display = 'inline-flex';

      // Show download if available
      if (finalResult.excel_file) {
        downloadSection.style.display = 'block';
        const downloadLink = document.getElementById('downloadLink');
        const downloadText = document.getElementById('downloadText');

        downloadLink.href = "/tools/mobile/download/" + encodeURIComponent(finalResult.excel_file);
        // downloadText.textContent = `Excel Report`; // Keep icon+text
      }

      if (finalResult.pdf_file) {
        const pdfLink = document.getElementById('downloadPdfLink');
        pdfLink.style.display = 'inline-flex';
        pdfLink.href = "/tools/mobile/download/" + encodeURIComponent(finalResult.pdf_file);
      }

      showAlert('Extraction completed successfully.', 'success');

    } catch (error) {
      console.error('Extraction error:', error);
      showAlert(`Extraction failed: ${error.message}`);
      updateProgressBar(0, `Error: ${error.message}`);
      // Show check mark as error x maybe? 
      // For now just leave it.
    } finally {
      startBtn.disabled = false;
      startBtn.innerHTML = '<i class="fas fa-bolt"></i> INITIATE EXTRACTION';
    }
  });

  // Refresh status button
  document.getElementById('refreshStatusBtn').addEventListener('click', function () {
    this.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    this.disabled = true;

    updateDeviceStatus();

    setTimeout(() => {
      this.innerHTML = '<i class="fas fa-sync"></i> REFRESH LINK';
      this.disabled = false;
    }, 1500);
  });

  // Clear button
  document.getElementById('clearBtn').addEventListener('click', function () {
    document.getElementById('output').value = '';
    document.getElementById('tablesContainer').innerHTML = '';
    document.getElementById('globalSearch').value = '';
    document.getElementById('statsGrid').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'none';
    document.getElementById('exportBtn').style.display = 'none';
    document.getElementById('downloadSection').style.display = 'none';
    document.getElementById('progressSection').style.display = 'none';
    document.getElementById('emptyState').style.display = 'block';
  });

  // Export JSON button
  document.getElementById('exportBtn').addEventListener('click', function () {
    const output = document.getElementById('output').value;
    if (output) {
      const blob = new Blob([output], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `CASE_EXPORT_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  });
});
