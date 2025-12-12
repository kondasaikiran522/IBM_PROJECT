from flask import Blueprint, request, jsonify, send_from_directory, send_file
import os
import sys

# Ensure we can import modules if running from backend dir
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import shared extensions
# extensions is in the root of the Flask app context (unified_dashboard)
from extensions import socketio
# Relative imports for local modules
from .scanner import scanner_instance
from .analysis import calculate_risk_score, explain_service, get_geoip_data, check_weak_credentials
from .sentry import sentry_instance
from .reporting import generate_pdf

from flask import render_template

# Define Blueprint
nmap_bp = Blueprint('nmap', __name__, 
                   url_prefix='/tools/nmap', 
                   static_folder='frontend', 
                   template_folder='frontend',
                   static_url_path='/static')

local_network = scanner_instance.get_local_network()

@nmap_bp.route("/")
def index():
    return render_template("index.html")

@nmap_bp.route("/<path:path>")
def static_files(path):
    return send_from_directory(nmap_bp.static_folder, path)

def run_async_scan(target, scan_type, extra):
    """
    Background task to run scan and emit results via WebSocket.
    """
    print(f"[*] Async Scan Started for {target} ({scan_type})")
    try:
        socketio.emit('scan_status', {'status': 'running', 'message': f'Scanning {target} ({scan_type})...'})
        results = scanner_instance.scan(target, scan_type, extra)
        
        # Enrich results with Analysis
        if isinstance(results, list):
            for host in results:
                host['risk_score'] = calculate_risk_score(host)
                # Explain ports
                if 'ports' in host:
                    for port, info in host['ports'].items():
                        info['explanation'] = explain_service(port, info['name'])

        # Emit final results
        socketio.emit('scan_status', {'status': 'completed', 'results': results})
        print(f"[*] Async Scan Finished. Emitted {len(results) if isinstance(results, list) else 0} results.")
        
    except Exception as e:
        print(f"[!] Async Scan Error: {e}")
        socketio.emit('scan_status', {'status': 'error', 'message': str(e)})

@nmap_bp.route("/scan", methods=["POST"])
def scan():
    data = request.json
    scan_type = data.get("scan_type")
    target = data.get("target") or local_network
    extra = data.get("extra", "")

    if not target:
        return jsonify({"error": "Target is required"}), 400

    # Start background task
    socketio.start_background_task(run_async_scan, target, scan_type, extra)
    
    return jsonify({"status": "started", "message": "Scan running in background. Watch the log."})

@nmap_bp.route("/sentry/start", methods=["POST"])
def start_sentry():
    target = request.json.get("target") or local_network
    sentry_instance.start(target)
    return jsonify({"status": "Sentry Mode Started", "target": target})

@nmap_bp.route("/sentry/stop", methods=["POST"])
def stop_sentry():
    sentry_instance.stop()
    return jsonify({"status": "Sentry Mode Stopped"})

@nmap_bp.route("/geoip", methods=["POST"])
def geoip_lookup():
    data = request.json
    ip = data.get("ip")
    if not ip: return jsonify({"error": "IP required"}), 400
    
    location = get_geoip_data(ip)
    return jsonify({"location": location})

@nmap_bp.route("/breach_audit", methods=["POST"])
def breach_audit():
    data = request.json
    ip = data.get("ip")
    port = data.get("port")
    service = data.get("service")
    
    if not ip or not port: return jsonify({"error": "Target required"}), 400
    
    result = check_weak_credentials(ip, int(port), service)
    return jsonify({"result": result})

@nmap_bp.route("/report/generate", methods=["POST"])
def generate_report():
    data = request.json
    results = data.get("results")
    if not results:
        return jsonify({"error": "No results to report"}), 400
    
    filename = generate_pdf(results)
    return send_file(filename, as_attachment=True)

@nmap_bp.route("/hosts", methods=["GET"])
def get_hosts():
    return jsonify({"message": "Use scan endpoint"})
