import time
import threading
from extensions import socketio
from scanner import scanner_instance

class Sentry:
    def __init__(self):
        self.active = False
        self.known_hosts = set()
        self.thread = None

    def start(self, target_network):
        if self.active:
            return
        self.active = True
        self.thread = threading.Thread(target=self._monitor_loop, args=(target_network,))
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.active = False

    def _monitor_loop(self, target_network):
        print(f"[*] Sentry Mode Activated on {target_network}")
        while self.active:
            # Perform a quick ping scan
            results = scanner_instance.scan(target_network, "host")
            
            current_hosts = set()
            if isinstance(results, list):
                for host in results:
                    ip = host['ip']
                    current_hosts.add(ip)
                    
                    if ip not in self.known_hosts:
                        # New host detected!
                        self.known_hosts.add(ip)
                        socketio.emit('sentry_alert', {
                            'title': 'New Device Detected',
                            'message': f'Device {ip} has joined the network.',
                            'details': host
                        })
            
            # Wait for 5 minutes (or 30 secs for demo)
            for _ in range(30): 
                if not self.active: break
                time.sleep(1)

sentry_instance = Sentry()
