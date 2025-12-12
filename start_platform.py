import subprocess
import sys
import time
import os

def main():
    print("="*60)
    print("CYBER TOOLS PLATFORM (MONOLITHIC) LAUNCHER")
    print("="*60)

    # Path to the main Flask app
    app_path = os.path.join("unified_dashboard", "app.py")
    
    print(f"[*] Starting Unified Platform on http://localhost:5000...")
    
    try:
        # Launch the Flask app
        # Using sys.executable to ensure the same python interpreter is used
        process = subprocess.Popen([sys.executable, app_path], cwd=os.getcwd())
        
        print(f"[+] Platform Running! Access at: http://localhost:5000 or http://<YOUR_IP>:5000")
        print(f"[!] Press Ctrl+C to stop.")
        
        process.wait()
        
    except KeyboardInterrupt:
        print("\n[*] Stopping Platform...")
        process.terminate()
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    main()
