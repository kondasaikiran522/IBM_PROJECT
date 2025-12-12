from flask import Blueprint, render_template, Response, request, jsonify, send_file
import os
from . import utils

# Define Blueprint
ram_bp = Blueprint('ram', __name__, url_prefix='/tools/ram', template_folder='templates', static_folder='static')

@ram_bp.route('/')
def index():
    return render_template('ram_index.html') # Renamed template to avoid conflict

@ram_bp.route('/api/status')
def status():
    return jsonify({
        "winpmem": bool(utils.WINPMEM_PATH),
        "volatility": bool(utils.VOL_PATH),
        "adb": utils.check_adb_connection(),
        "admin": utils.is_admin()
    })

@ram_bp.route('/api/files')
def list_files():
    files = []
    # Use current directory of this module
    cwd = os.path.dirname(os.path.abspath(__file__))
    for f in os.listdir(cwd):
        if f.endswith(".raw") or f.endswith(".txt"):
            files.append({
                "name": f,
                "size": os.path.getsize(os.path.join(cwd, f)),
                "type": "dump" if f.endswith(".raw") else "report"
            })
    return jsonify(files)

@ram_bp.route('/api/download/<filename>')
def download_file(filename):
    cwd = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(cwd, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found", 404

@ram_bp.route('/api/stop', methods=['POST'])
def stop_process():
    if utils.kill_process():
        return jsonify({"status": "terminated"})
    return jsonify({"status": "no_process"})

# Streaming Functions
def generate_output(generator_func, *args):
    for line in generator_func(*args):
        yield f"data: {line}\n\n"
    yield "data: [DONE]\n\n"

@ram_bp.route('/stream/capture/windows')
def stream_capture_windows():
    return Response(generate_output(utils.stream_extract_windows), mimetype='text/event-stream')

@ram_bp.route('/stream/capture/android')
def stream_capture_android():
    return Response(generate_output(utils.stream_extract_android), mimetype='text/event-stream')

@ram_bp.route('/stream/analyze')
def stream_analyze():
    filename = request.args.get('filename')
    if not filename:
        return "Filename required", 400
    return Response(generate_output(utils.stream_analyze, filename), mimetype='text/event-stream')

