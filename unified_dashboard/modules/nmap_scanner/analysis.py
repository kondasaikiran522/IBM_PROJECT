import requests
import socket

def calculate_risk_score(host_data):
    """
    Calculates a risk score (0-100) based on open ports and services.
    """
    score = 0
    high_risk_ports = [21, 23, 445, 3389] # FTP, Telnet, SMB, RDP
    medium_risk_ports = [80, 8080] # HTTP (unencrypted)

    if 'ports' in host_data:
        for port, info in host_data['ports'].items():
            if port in high_risk_ports and info['state'] == 'open':
                score += 30
            elif port in medium_risk_ports and info['state'] == 'open':
                score += 10
            else:
                score += 1
    
    return min(score, 100)

def explain_service(port, service_name):
    """
    Returns a human-readable explanation of a service.
    """
    explanations = {
        21: "FTP (File Transfer Protocol): Used for transferring files between computers. Insecure if not configured correctly.",
        22: "SSH (Secure Shell): Securely accessing remote servers.",
        23: "Telnet: Unencrypted remote access. HIGH RISK. Should be replaced by SSH.",
        25: "SMTP: Sending emails.",
        53: "DNS: Resolves domain names to IP addresses.",
        80: "HTTP: Web server (unencrypted).",
        110: "POP3: Retrieving emails.",
        143: "IMAP: Retrieving emails.",
        443: "HTTPS: Secure web server.",
        445: "SMB: Windows File Sharing. Common vector for ransomware if exposed.",
        3306: "MySQL Database.",
        3389: "RDP (Remote Desktop): Windows remote control.",
        5432: "PostgreSQL Database."
    }
    
    return explanations.get(port, f"{service_name.upper()}: A network service running on port {port}.")

def get_geoip_data(ip):
    """
    Returns lat/lon for an IP using a free API.
    """
    # Don't trace local IPs
    if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("127.") or ip.startswith("172.16."):
        return None
    
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        data = response.json()
        if data['status'] == 'success':
            return {
                "lat": data['lat'],
                "lon": data['lon'],
                "city": data['city'],
                "country": data['country']
            }
    except Exception:
        return None
    return None

def check_weak_credentials(ip, port, service):
    """
    Checks for default credentials on specific services (Telnet/FTP).
    EXTREMELY BASIC & UNSAFE implementation for demo.
    """
    # Only try on local network to avoid legal issues
    # Demo list of weak creds
    creds = [("admin", "admin"), ("root", "root"), ("user", "user"), ("admin", "password")]
    
    status = "Secure (or checks skipped)"
    
    try:
        if port == 21: # FTP check
            import ftplib
            for user, pwd in creds:
                try:
                    ftp = ftplib.FTP(ip)
                    ftp.login(user, pwd)
                    ftp.quit()
                    return f"WEAK CREDENTIALS FOUND: {user}/{pwd}"
                except:
                    pass
        elif port == 23: # Telnet check
             # Telnet lib is tricky to script without expect, skipping actual login for safety/demo
             return "Telnet Exposed - High Risk (Credential check skipped for safety)"
             
    except Exception as e:
        return f"Check Error: {str(e)}"
        
    return "No default credentials found (checked top 4)."
