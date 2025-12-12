# routes.py
import json
from flask import Blueprint, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename
from collections import Counter, defaultdict
from scapy.all import rdpcap, sniff, wrpcap, IP, TCP, UDP, ICMP, ARP, DNS, DNSQR, Raw, get_if_list
import os
import tempfile
import time
import logging
import datetime
import platform
import requests
import ipaddress

# Try importing Windows-specific helpers
try:
    from scapy.arch.windows import get_windows_if_list
except ImportError:
    get_windows_if_list = None

logging.basicConfig(level=logging.INFO)

# Define Blueprint
# static_folder='frontend' means it will serve files from ./frontend at /tools/wireshark/static/
# But the original app served from root. We need to serve index.html via route.
network_bp = Blueprint('network', __name__, url_prefix='/tools/wireshark', static_folder='frontend')

# ... (Insert Helpers Here: geo_cache, is_public_ip, get_geoip, scan_for_secrets, load_config, hexdump, get_packet_info, analyze_packets) ...
# To avoid huge diff, I will assume Helpers are present and just change the app definition and routes. 
# NOTE: The TOOL replace_file_content replaces a block. I need to be careful not to delete helpers if I don't select them.
# The user wants "edit all modules... make unified".

# --- GeoIP Cache ---
geo_cache = {}

def is_public_ip(ip):
    try:
        obj = ipaddress.ip_address(ip)
        return not obj.is_private and not obj.is_loopback and not obj.is_multicast
    except ValueError:
        return False

def get_geoip(ip):
    if ip in geo_cache:
        return geo_cache[ip]
    
    if not is_public_ip(ip):
        return None

    try:
        # Rate limit protection: simple timeout and silencing errors
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success':
                res = {"lat": data['lat'], "lon": data['lon'], "country": data['country'], "city": data['city'], "ip": ip}
                geo_cache[ip] = res
                return res
    except Exception:
        pass
    return None

def scan_for_secrets(pkt):
    """Simple heuristic to find cleartext credentials."""
    alerts = []
    if pkt.haslayer(TCP) and pkt.haslayer(Raw):
        payload = bytes(pkt[TCP].payload)
        try:
            # Decode carefully
            s = payload.decode('utf-8', errors='ignore')
            
            # HTTP Basic Auth
            if "Authorization: Basic" in s:
                alerts.append(f"Cleartext HTTP Auth found in packet to {pkt[IP].dst}")
            
            # Telnet/FTP Patterns
            lower_s = s.lower()
            if "pass " in lower_s or "password" in lower_s:
                 # Reduce noise: strict check
                 if any(k in lower_s for k in ["user ", "login"]):
                     alerts.append(f"Potential Login/Password found for {pkt[IP].dst}")
                     
            # API Keys (Generic)
            if "api-key" in lower_s or "apikey" in lower_s:
                alerts.append(f"Potential API Key header found to {pkt[IP].dst}")
                
        except:
            pass
    return alerts


# --- Configuration ---
def load_config():
    try:
        # Need absolute path or relative to this file
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning("config.json not found. Using default settings.")
        return {}
    except json.JSONDecodeError:
        logging.error("Error decoding config.json. Using default settings.")
        return {}

config = load_config()

# --------- Core analysis helpers (pure Python/Scapy) ---------
def hexdump(pkt):
    """Generates a Wireshark-like hex dump of the packet."""
    x = bytes(pkt)
    lines = []
    for i in range(0, len(x), 16):
        chunk = x[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk).ljust(48)
        ascii_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
        lines.append(f'{i:04x}  {hex_part}  {ascii_part}')
    return '\n'.join(lines)

def get_packet_info(pkt, frame_num):
    info = {"frame_number": frame_num, "time": pkt.time}
    
    # Source and Destination
    if pkt.haslayer(IP):
        info["source"] = pkt[IP].src
        info["destination"] = pkt[IP].dst
    elif pkt.haslayer(ARP):
        info["source"] = pkt[ARP].psrc if pkt[ARP].op == 1 else pkt[ARP].hwsrc # ARP request/reply
        info["destination"] = pkt[ARP].pdst if pkt[ARP].op == 1 else pkt[ARP].hwdst
    else:
        info["source"] = pkt.src if hasattr(pkt, 'src') else "N/A"
        info["destination"] = pkt.dst if hasattr(pkt, 'dst') else "N/A"

    # Protocol and Info
    info["protocol"] = "Other"
    info_summary = ""

    if pkt.haslayer(IP):
        info["length"] = pkt[IP].len
        if pkt.haslayer(TCP):
            info["protocol"] = "TCP"
            info_summary = f"TCP {pkt[IP].src}:{pkt[TCP].sport} -> {pkt[IP].dst}:{pkt[TCP].dport} Flags={pkt[TCP].flags}"
        elif pkt.haslayer(UDP):
            info["protocol"] = "UDP"
            info_summary = f"UDP {pkt[IP].src}:{pkt[UDP].sport} -> {pkt[IP].dst}:{pkt[UDP].dport}"
        elif pkt.haslayer(ICMP):
            info["protocol"] = "ICMP"
            info_summary = f"ICMP {pkt[IP].src} -> {pkt[IP].dst} Type={pkt[ICMP].type} Code={pkt[ICMP].code}"
        elif pkt.haslayer(DNS):
            info["protocol"] = "DNS"
            if pkt.qd:
                info_summary = f"DNS Query {pkt[DNSQR].qname.decode()}"
            elif pkt.an:
                info_summary = f"DNS Response for {pkt[DNSQR].qname.decode()}"
    elif pkt.haslayer(ARP):
        info["protocol"] = "ARP"
        info_summary = f"ARP {'Request' if pkt[ARP].op == 1 else 'Reply'} {pkt[ARP].psrc} is-at {pkt[ARP].hwsrc}"
    
    # Basic HTTP detection (can be expanded)
    if pkt.haslayer(TCP) and pkt.haslayer(Raw):
        payload = bytes(pkt[TCP].payload)
        try:
            payload_str = payload.decode('utf-8', errors='ignore')
            if payload_str.startswith(('GET ', 'POST ', 'PUT ', 'DELETE ', 'HEAD ')):
                info["protocol"] = "HTTP"
                info_summary = payload_str.split('\r\n')[0]
        except:
            pass

    info["info"] = info_summary if info_summary else pkt.summary()
    info["length"] = len(pkt)
    info["hex_dump"] = hexdump(pkt) # Add hex dump

    # Detailed layers (basic representation)
    layers = []
    layer_index = 0
    while True:
        layer = pkt.getlayer(layer_index)
        if not layer:
            break
        layer_dict = {"name": layer.name, "fields": {}}
        for field_name in layer.fields:
            field_value = getattr(layer, field_name)
            # Convert bytes to string for display
            if isinstance(field_value, bytes):
                try:
                    field_value = field_value.decode('utf-8', errors='ignore')
                except:
                    pass
            layer_dict["fields"][field_name] = str(field_value)
        layers.append(layer_dict)
        layer_index += 1
    info["layers"] = layers

    return info

def analyze_packets(packets):
    total_packets = len(packets)
    detailed_packets = [] # New list for detailed packet info
    
    # Timeline buckets (per second)
    timeline = defaultdict(int)
    # Conversation pairs (Source -> Dest) -> Bytes
    conversations = defaultdict(int)
    
    # Security Alerts
    alerts_list = []
    
    # Set of IPs to Geotag (from top talkers later, or just all unique external)
    external_ips = set()

    for i, pkt in enumerate(packets):
        detailed_packets.append(get_packet_info(pkt, i + 1)) # Frame numbers start from 1
        
        # Timeline
        ts = int(pkt.time)
        timeline[ts] += 1
        
        # Conversations & Secrets
        if pkt.haslayer(IP):
             src = pkt[IP].src
             dst = pkt[IP].dst
             conversations[(src, dst)] += len(pkt)
             
             if is_public_ip(src): external_ips.add(src)
             if is_public_ip(dst): external_ips.add(dst)
             
             # Secret Scan
             secrets = scan_for_secrets(pkt)
             for s in secrets:
                 alerts_list.append({"type": "Credential exposure", "msg": s, "frame": i+1})

    ip_pairs = [(pkt[IP].src, pkt[IP].dst) for pkt in packets if pkt.haslayer(IP)]
    unique_pairs = len(set(ip_pairs))

    proto_counter = Counter()
    for pkt in packets:
        if pkt.haslayer(ARP):
            proto_counter["ARP"] += 1
        elif pkt.haslayer(ICMP):
            proto_counter["ICMP"] += 1
        elif pkt.haslayer(TCP):
            proto_counter["TCP"] += 1
        elif pkt.haslayer(UDP):
            proto_counter["UDP"] += 1
        else:
            proto_counter["Others"] += 1

    usage = Counter()
    for pkt in packets:
        if pkt.haslayer(IP):
            usage[pkt[IP].src] += len(pkt)
    top_talkers = usage.most_common(10)

    # Look for Port Scans
    scan_counter = Counter()
    for pkt in packets:
        if pkt.haslayer(TCP) and pkt.haslayer(IP):
            scan_counter[(pkt[IP].src, pkt[TCP].dport)] += 1
    THRESHOLD = 5
    for (ip, port), count in scan_counter.items():
        if count > THRESHOLD:
             alerts_list.append({"type": "Port Scan", "msg": f"{ip} scanning port {port} ({count} hits)", "frame": "-"})

    dns_queries = []
    # ... (existing DNS logic) ...
    for pkt in packets:
        if pkt.haslayer(DNS) and pkt.getlayer(DNS).qr == 0: # DNS Query
            try:
                query = pkt.getlayer(DNS).qd.qname.decode("utf-8")
                dns_queries.append(query)
            except (IndexError, AttributeError):
                continue
    
    # GeoIP resolution (Limit to top 20 to avoid API bans)
    geoip_results = []
    for ip in list(external_ips)[:20]:
        g = get_geoip(ip)
        if g: geoip_results.append(g)

    # ... (Rest of function) ...
    http_requests = []
    for pkt in packets:
        if pkt.haslayer(TCP) and pkt.haslayer(IP) and len(pkt[TCP].payload) > 0:
            try:
                payload = bytes(pkt[TCP].payload).decode("utf-8", errors="ignore")
                if payload.startswith(("GET ", "POST ", "PUT ", "DELETE ", "HEAD ")):
                    lines = payload.split("\r\n")
                    request_line = lines[0]
                    method, uri, _ = request_line.split(" ")
                    host = ""
                    for line in lines[1:]:
                        if line.lower().startswith("host:"):
                            host = line.split(":", 1)[1].strip()
                            break
                    http_requests.append({"method": method, "host": host, "uri": uri})
            except Exception:
                continue

    # Format timeline and conversations for JSON
    timeline_data = [{"time": ts, "count": count} for ts, count in sorted(timeline.items())]
    conversation_data = [{"source": src, "target": dst, "value": count} for (src, dst), count in conversations.items()]

    return {
        "total_packets": total_packets,
        "unique_ip_pairs": unique_pairs,
        "protocol_stats": dict(proto_counter),
        "top_talkers": [{"ip": ip, "bytes": int(b)} for ip, b in top_talkers],
        "alerts": alerts_list, # Unified alerts
        "dns_queries": list(set(dns_queries)),
        "http_requests": http_requests,
        "detailed_packets": detailed_packets,
        "timeline": timeline_data,
        "conversations": conversation_data,
        "geoip": geoip_results
    }

# --------- Routes ---------
@network_bp.route("/")
def index():
    # Serve index.html from the Blueprints' static folder
    return send_from_directory(network_bp.static_folder, "wireshark_index.html")

@network_bp.route("/<path:path>")
def static_proxy(path):
    # Serve other static files (js, css)
    return send_from_directory(network_bp.static_folder, path)

@network_bp.route("/api/interfaces", methods=["GET"])
def get_interfaces():
    try:
        detailed_interfaces = []
        if get_windows_if_list:
            # Windows: use get_windows_if_list for friendly names + GUIDs
            win_ifaces = get_windows_if_list()
            for i in win_ifaces:
                guid = i.get('guid')
                name = i.get('name')
                desc = i.get('description')
                
                # Construct safe device path for Scapy on Windows
                val = f"\\Device\\NPF_{guid}"
                # Display friendly name + desc
                detailed_interfaces.append({"name": f"{name} ({desc})", "value": val})
                
        else:
            # Unix-like fallback
            ifaces = get_if_list()
            for i in ifaces:
                detailed_interfaces.append({"name": i, "value": i})
                
        return jsonify({"interfaces": detailed_interfaces}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@network_bp.route("/api/download/<filename>", methods=["GET"])
def download_pcap(filename):
    try:
        filename = secure_filename(filename)
        filepath = os.path.join(tempfile.gettempdir(), filename)
        if os.path.exists(filepath):
             return send_file(filepath, as_attachment=True)
        else:
             return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@network_bp.route("/api/analyze", methods=["POST"])
def api_analyze():
    if "pcap" not in request.files:
        return jsonify({"error": "No file part named 'pcap'"}), 400
    f = request.files["pcap"]
    if f.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(f.filename)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, filename)
        f.save(path)
        try:
            packets = rdpcap(path)
        except Exception as e:
            return jsonify({"error": f"Failed to read pcap: {e}"}), 400

        result = analyze_packets(packets)
        return jsonify(result), 200

@network_bp.route("/api/live-capture", methods=["POST"])
def api_live_capture():
    data = request.get_json(silent=True) or {}
    interface = data.get("interface") or config.get("default_interface")
    packet_count = int(data.get("packet_count", 30))
    action = data.get("action", "analyze")

    if not interface:
        return jsonify({"error": "No interface specified. Please select one in the UI or set a default in config.json."}), 400

    logging.info(f"Starting live capture on interface '{interface}'...")

    try:
        scapy_pkts = sniff(iface=interface, count=packet_count, timeout=15)
        logging.info(f"Captured {len(scapy_pkts)} packets.")
    except Exception as e:
        logging.error(f"Live capture failed: {e}", exc_info=True)
        return jsonify({"error": f"Capture failed: {e}. If on Windows, ensure you selected a valid interface from the list."}), 400

    if action == "analyze":
        result = analyze_packets(scapy_pkts)
        return jsonify(result), 200
    elif action == "save":
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"capture-{timestamp}.pcap"
        filepath = os.path.join(tempfile.gettempdir(), filename) # Save to temp directory
        try:
            wrpcap(filepath, scapy_pkts)
            return jsonify({"message": "Capture saved successfully.", "filename": filename, "count": len(scapy_pkts)}), 200
        except Exception as e:
            logging.error(f"Failed to save capture: {e}", exc_info=True)
            return jsonify({"error": f"Failed to save capture: {e}"}), 500
    
    return jsonify({"error": "Invalid action specified."}), 400