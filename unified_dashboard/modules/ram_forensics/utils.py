import os
import subprocess
import shutil
import datetime
import time
import ctypes

# ================= CONFIG =================
def find_tool(tool_name, local_fallback=None):
    """Find a tool in PATH or local directory."""
    path = shutil.which(tool_name)
    if path:
        return path
    if local_fallback:
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), local_fallback)
        if os.path.exists(local_path):
            return local_path
    return None

WINPMEM_PATH = find_tool("winpmem.exe", "winpmem.exe")
VOL_PATH = find_tool("vol.exe", "vol.exe") or find_tool("vol.py", "vol.py")
ADB_PATH = find_tool("adb", "adb.exe")

if not ADB_PATH:
    ADB_PATH = "adb"

VOL_PLUGINS = [
    ["windows.pslist"],
    ["windows.pstree"],
    ["windows.netscan"],
    ["windows.dlllist"],
    ["windows.malfind"],
    ["windows.cmdline"],
    ["windows.registry.printkey", "--key", "ControlSet001\\Services\\Tcpip\\Parameters"]
]

def get_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# ================= LOGIC GENERATORS =================
CURRENT_PROCESS = None

def kill_process():
    """Kill the currently running background process."""
    global CURRENT_PROCESS
    if CURRENT_PROCESS and CURRENT_PROCESS.poll() is None:
        try:
            CURRENT_PROCESS.terminate()
            time.sleep(0.5)
            if CURRENT_PROCESS.poll() is None:
                CURRENT_PROCESS.kill()
            return True
        except Exception:
            return False
    return False

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def check_adb_connection():
    """Check if an Android device is actually connected and authorized."""
    if not ADB_PATH:
        return False
    try:
        # Run 'adb devices'
        result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True)
        # Output format:
        # List of devices attached
        # <serial>    device
        #
        # We look for "device" or "recovery" or "sideload" state, but specifically excluding empty list.
        lines = result.stdout.strip().split('\n')[1:] # Skip header
        for line in lines:
            if "\tdevice" in line or "\trecovery" in line:
                return True
        return False
    except:
        return False

# ================= LOGIC GENERATORS =================
# These functions yield output lines so they can be streamed to the web UI

def stream_extract_windows():
    if not WINPMEM_PATH:
        yield "[-] Error: winpmem.exe not found.\n"
        return

    if not is_admin():
        yield "[!] PERMISSION ERROR: Administrator privileges required.\n"
        yield "    Please run the application as Administrator.\n"
        return

    yield "[*] Starting RAM acquisition on Windows...\n"
    timestamp = get_timestamp()
    dump_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"memory_dump_windows_{timestamp}.raw")

    try:
        cmd = [WINPMEM_PATH, "acquire", dump_file]
        yield f"[*] Executing: {' '.join(cmd)}\n"
        
        # Run subprocess and capture output real-time
        CURRENT_PROCESS = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        for line in CURRENT_PROCESS.stdout:
            yield line
        
        CURRENT_PROCESS.wait()
        
        if CURRENT_PROCESS.returncode == 0:
            yield f"\n[+] RAM dump saved as {dump_file}\n"
            yield f"[+] Filename: {os.path.basename(dump_file)}\n"
        elif CURRENT_PROCESS.returncode is not None:
             if CURRENT_PROCESS.returncode < 0:
                  yield "\n[!] Process Terminated by User.\n"
             else:
                  yield f"\n[-] Process exited with code {CURRENT_PROCESS.returncode}\n"
        
        CURRENT_PROCESS = None
            
    except Exception as e:
        yield f"[-] Error: {e}\n"
        CURRENT_PROCESS = None

def stream_extract_android():
    yield "[*] Checking ADB connection...\n"
    try:
        subprocess.run([ADB_PATH, "devices"], check=True, capture_output=True)
    except Exception:
        yield "[-] ADB not found or device not connected.\n"
        return

    yield "[*] Checking for root access (su)...\n"
    try:
        # Try to invoke root logic. This might trigger a popup on the phone.
        res = subprocess.run([ADB_PATH, "shell", "su", "-c", "id"], capture_output=True, text=True)
        
        # Check if we got root
        if "uid=0(root)" not in res.stdout:
            yield "[-] ERROR: Root access denied.\n"
            yield "    1. Check your Phone screen NOW for a SuperUser/Magisk popup.\n"
            yield "    2. Grant 'Always/Forever' to ADB Shell.\n"
            yield "    3. If no popup appeared, your device might not be rooted.\n"
            yield "    (RAM acquisition requires a rooted device to read /dev/mem)\n"
            return
    except Exception as e:
        yield f"[-] Error running root check: {e}\n"
        return

    yield "[+] Root access confirmed. Starting extraction...\n"
    timestamp = get_timestamp()
    dump_filename = f"memory_dump_android_{timestamp}.raw"
    local_dump_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), dump_filename)
    remote_path = "/sdcard/memory_dump.raw"

    try:
        cmd = [ADB_PATH, "shell", f"su -c 'dd if=/dev/mem of={remote_path}'"] 
        yield "[*] Dumping memory to internal storage (processing)...\n"
        
        # DD output is usually silent or on stderr, we just wait here
        subprocess.run(" ".join(cmd), shell=True, check=True)
        yield "[+] Dump created on device.\n"

        yield f"[*] Pulling {remote_path} to PC...\n"
        subprocess.run([ADB_PATH, "pull", remote_path, local_dump_file], check=True)
        
        yield "[*] Cleaning up temporary files...\n"
        subprocess.run([ADB_PATH, "shell", f"rm {remote_path}"], check=True)

        yield f"[+] Android RAM dump saved as {local_dump_file}\n"
    except Exception as e:
        yield f"[-] Error: {e}\n"

def stream_analyze(filename, platform="windows"):
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(file_path):
        yield f"[-] Error: File {filename} not found.\n"
        return

    if not VOL_PATH:
        yield "[-] Error: Volatility not found.\n"
        return

    # Location args
    abs_path = os.path.abspath(file_path)
    file_uri = f"file://{abs_path}"
    base_vol_args = [VOL_PATH, "-f", abs_path, "--single-location", file_uri]

    yield f"[*] Analyzing {platform} dump: {filename}\n"
    yield "[*] Running Pre-check (windows.info)...\n"

    # Pre-check
    try:
        check_proc = subprocess.Popen(base_vol_args + ["windows.info"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in check_proc.stdout:
            yield line
        check_proc.wait()
        
        if check_proc.returncode != 0:
             yield "\n[!] Pre-check failed. Volatility may need Internet access for symbols.\n"
    except Exception as e:
        yield f"[-] Pre-check error: {e}\n"

    # Plugins
    timestamp = get_timestamp()
    report_filename = f"report_{platform}_{timestamp}.txt"
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), report_filename)
    
    with open(report_path, "w", encoding="utf-8") as report:
        report.write(f"Analysis Report {timestamp}\nTarget: {filename}\n\n")

        for plugin in VOL_PLUGINS:
            yield f"\n=== Running Plugin: {plugin[0]} ===\n"
            report.write(f"\n=== Plugin: {plugin[0]} ===\n")
            
            cmd = base_vol_args + plugin
            try:
                CURRENT_PROCESS = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in CURRENT_PROCESS.stdout:
                    yield line
                    report.write(line)
                CURRENT_PROCESS.wait()
                
                if CURRENT_PROCESS.returncode != 0:
                    if CURRENT_PROCESS.returncode < 0:
                         yield "\n[!] Analysis Terminated by User.\n"
                         break
                    yield f"\n[!] Plugin exited with code {CURRENT_PROCESS.returncode}\n"
            except Exception as e:
                yield f"[-] Plugin Error: {e}\n"
                report.write(f"Error: {e}\n")
    
    CURRENT_PROCESS = None

    yield f"\n[+] Analysis Complete. Report saved to {report_filename}\n"
