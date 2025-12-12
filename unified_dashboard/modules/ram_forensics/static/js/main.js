document.addEventListener('DOMContentLoaded', () => {
    checkStatus();
    loadFiles();
    setInterval(checkStatus, 10000); // Poll status every 10s
});

// === NAVIGATION ===
function showSection(sectionId) {
    // Hide all
    document.querySelectorAll('.content-section').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    // Show target
    document.getElementById(sectionId).classList.add('active');

    // Highlight sidebar
    // Indicies: 0=Dashboard, 1=Capture(Acquisition & Analysis), 2=Files(History)
    const navMap = { 'dashboard': 0, 'capture': 1, 'files': 2 };
    if (navMap[sectionId] !== undefined) {
        document.querySelectorAll('.nav-item')[navMap[sectionId]].classList.add('active');
    }

    if (sectionId === 'files' || sectionId === 'capture' || sectionId === 'dashboard') {
        loadFiles();
    }
}

// === API CALLS ===
async function checkStatus() {
    try {
        const res = await fetch('/tools/ram/api/status');
        const data = await res.json();

        updateBadge('status-winpmem', data.winpmem);
        updateBadge('status-vol', data.volatility);
        updateBadge('status-adb', data.adb);
        updateBadge('status-admin', data.admin);

        if (!data.admin) logToTerminal("WARNING: Not running as Administrator. WinPMEM will fail.", "error");

    } catch (e) {
        console.error("Status check failed", e);
    }
}

function updateBadge(id, isOk) {
    const el = document.getElementById(id);
    if (isOk) {
        el.textContent = "ONLINE";
        el.className = "badge ok";
    } else {
        el.textContent = "OFFLINE";
        el.className = "badge err";
    }
}

async function loadFiles() {
    try {
        const res = await fetch('/tools/ram/api/files');
        const files = await res.json();

        // --- Populate Analysis Dropdown (Capture Tab) ---
        const select = document.getElementById('analysis-file-select');
        if (select) {
            const currentVal = select.value;
            select.innerHTML = '<option value="">-- Select .raw Image --</option>';
            files.forEach(f => {
                if (f.type === 'dump') {
                    const opt = document.createElement('option');
                    opt.value = f.name;
                    opt.textContent = `${f.name} (${formatBytes(f.size)})`;
                    select.appendChild(opt);
                }
            });
            select.value = currentVal; // Restore selection if possible
        }

        // --- Populate History Table (Files Tab) ---
        const historyTbody = document.querySelector('#file-table tbody');
        if (historyTbody) {
            historyTbody.innerHTML = '';
            files.forEach(f => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${f.name}</td>
                    <td><span class="tag">${f.type.toUpperCase()}</span></td>
                    <td>${formatBytes(f.size)}</td>
                    <td><a href="/tools/ram/api/download/${f.name}" class="btn-download">DOWNLOAD</a></td>
                `;
                historyTbody.appendChild(tr);
            });
        }

        // --- Populate Dashboard Stats & Table ---
        const dashTbody = document.querySelector('#dashboard-table tbody');
        if (dashTbody) {
            dashTbody.innerHTML = '';

            // Filter separately if needed, currently showing all
            // Extract Date/Time from filename pattern: *_YYYY-MM-DD_HH-MM-SS.*
            let validCases = 0;
            let lastActive = "None";

            // Sort by name (roughly simplified timestamp sort) descending
            files.sort((a, b) => b.name.localeCompare(a.name));

            files.forEach(f => {
                // Try regex extraction
                const match = f.name.match(/(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})/);
                let dateStr = "--";
                let timeStr = "--";

                if (match) {
                    dateStr = match[1];
                    timeStr = match[2].replace(/-/g, ':');
                    validCases++;
                    if (validCases === 1) lastActive = `${dateStr} ${timeStr}`;
                }

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${f.name}</td>
                    <td>${dateStr}</td>
                    <td>${timeStr}</td>
                    <td><span class="tag">${f.type.toUpperCase()}</span></td>
                `;
                dashTbody.appendChild(tr);
            });

            document.getElementById('stat-total-cases').textContent = validCases;
            document.getElementById('stat-last-active').textContent = lastActive;
        }

    } catch (e) {
        console.error("File load failed", e);
    }
}

// === STREAMING LOGIC ===
let eventSource = null;

function startCapture(platform) {
    if (eventSource) eventSource.close();
    showSection('dashboard');
    clearTerminal();
    logToTerminal(`[INIT] Starting ${platform.toUpperCase()} Capture stream...`, "system");

    const endpoint = `/tools/ram/stream/capture/${platform}`;
    connectStream(endpoint);
}

function startAnalysis() {
    const filename = document.getElementById('analysis-file-select').value;
    if (!filename) {
        alert("Please select a memory dump first.");
        return;
    }

    if (eventSource) eventSource.close();
    showSection('dashboard');
    clearTerminal();
    logToTerminal(`[INIT] Starting Volatility Analysis on ${filename}...`, "system");

    const endpoint = `/tools/ram/stream/analyze?filename=${encodeURIComponent(filename)}`;
    connectStream(endpoint);
}

function connectStream(url) {
    eventSource = new EventSource(url);

    eventSource.onmessage = function (e) {
        if (e.data === "[DONE]") {
            logToTerminal(">>> PROCESS COMPLETE <<<", "success");
            eventSource.close();
            eventSource = null;
            loadFiles(); // Refresh file lists
            return;
        }
        logToTerminal(e.data);
    };

    eventSource.onerror = function (e) {
        logToTerminal(">>> CONNECTION CLOSED / ERROR <<<", "error");
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    };
}

async function stopProcess() {
    if (!eventSource) return;

    logToTerminal("[!] Sending termination signal...", "error");
    try {
        await fetch('/tools/ram/api/stop', { method: 'POST' });
    } catch (e) {
        console.error(e);
    }

    if (eventSource) {
        eventSource.close();
        eventSource = null;
        logToTerminal(">>> CONNECTION TERMINATED BY USER <<<", "error");
    }
}

// === UTILS ===
function logToTerminal(text, type = "normal") {
    const term = document.getElementById('live-terminal');
    const div = document.createElement('div');
    div.textContent = text;
    div.className = `log-line ${type}`;
    term.appendChild(div);
    term.scrollTop = term.scrollHeight;
}

function clearTerminal() {
    document.getElementById('live-terminal').innerHTML = '';
}

function formatBytes(bytes, decimals = 2) {
    if (!+bytes) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}
