import nmap
import ipaddress
import socket
import random
from extensions import socketio

class NetworkScanner:
    def __init__(self):
        try:
            self.nm = nmap.PortScanner()
            self.available = True
        except nmap.PortScannerError:
            self.nm = None
            self.available = False
            print("[!] Nmap not found")

    def get_local_network(self):
        try:
            ip = socket.gethostbyname(socket.gethostname())
            # Basic fallback for demo purposes if gethostbyname returns localhost
            if ip.startswith("127."):
                # Try to connect to an external server to get the real interface IP
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
            
            ip_obj = ipaddress.ip_interface(f"{ip}/24")
            return str(ip_obj.network)
        except Exception:
            return "192.168.1.0/24" # Default fallback

    def scan(self, target, scan_type, extra_params=None):
        if not self.available:
            return {"error": "Nmap not available"}

        args = "-sn" # Default network scan
        
        if scan_type == "network":
            args = "-sn -T4"
        elif scan_type == "host":
            args = "-sn"
        elif scan_type == "target":
            args = "-Pn -p-"
        elif scan_type == "ports":
            port_range = extra_params or "1-1000"
            args = f"-p {port_range} -T4"
        elif scan_type == "service":
            args = "-sV -T4"
        elif scan_type == "os":
            args = "-O"
        elif scan_type == "stealth":
            # Stealth mode: slower timing, randomize hosts if possible (not applicable to single target usually but good for ranges)
            args = "-sS -T1 --randomize-hosts"
        elif scan_type == "script":
            script = extra_params or "default"
            args = f"--script {script}"

        # Emit start event
        socketio.emit('scan_status', {'status': 'running', 'message': f'Starting {scan_type} scan on {target} with args: {args}'})
        
        try:
            # Running scan
            # Note: For real-time output we might need subprocess, but nmap python lib is blocking usually.
            # We will emit "finished" when done for now.
            self.nm.scan(hosts=target, arguments=args)
            
            # Process results
            hosts = []
            for host in self.nm.all_hosts():
                host_data = self.nm[host]
                
                # Basic info
                info = {
                    'ip': host,
                    'status': host_data.state(),
                    'hostnames': host_data.hostnames(),
                    'mac': host_data['addresses'].get('mac', 'Unknown'),
                    'vendor': host_data['vendor'].get(host_data['addresses'].get('mac', ''), 'Unknown')
                }
                
                # Protocol/Port info if active
                if 'tcp' in host_data:
                    info['ports'] = host_data['tcp']
                
                # OS Match
                if 'osmatch' in host_data:
                    info['os'] = host_data['osmatch']

                hosts.append(info)
            
            socketio.emit('scan_status', {'status': 'completed', 'results': hosts})
            return hosts

        except Exception as e:
            socketio.emit('scan_status', {'status': 'error', 'message': str(e)})
            return {"error": str(e)}

scanner_instance = NetworkScanner()
