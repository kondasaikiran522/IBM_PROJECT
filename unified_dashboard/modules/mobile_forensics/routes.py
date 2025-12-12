from flask import Blueprint, render_template, request, jsonify, send_file
import threading, time, os, subprocess, re
from datetime import datetime
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# Define Blueprint
mobile_bp = Blueprint('mobile', __name__, url_prefix='/tools/mobile', template_folder='templates', static_folder='static')

# Shared job state (single active job)
progress = {
    "running": False,
    "percent": 0,
    "message": "",
    "result": None,
    "error": None,
    "excel_file": None
}
progress_lock = threading.Lock()


# -------------------------
# Helper utilities (ADB)
# -------------------------
def adb_check():
    try:
        subprocess.run(["adb", "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except Exception:
        return False

def adb_devices():
    try:
        proc = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = proc.stdout.decode("utf-8", errors="replace")
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if len(lines) <= 1:
            return False, "No device attached."
        # look for any line ending with <tab>device
        for ln in lines[1:]:
            if ln.endswith("\tdevice"):
                return True, "Device connected."
            if "unauthorized" in ln:
                return False, "Device unauthorized. Accept USB debugging on phone."
        return False, "No authorized device found."
    except Exception as e:
        return False, f"ADB error: {e}"

def run_adb(args):
    """
    Run adb command (list form) and return stdout string decoded as utf-8 (replace errors).
    Raises RuntimeError on non-zero return code.
    """
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"ADB returned code {proc.returncode}. stderr: {err.strip()}")
    return out


# -------------------------
# Parsing content query output
# -------------------------
def parse_content_line_to_dict(line):
    """
    Parse a single 'content query' line into a dict.
    Logic:
      - Split line into tokens by whitespace.
      - Token containing '=' begins a new key; token without '=' is continuation of previous value.
      This preserves values that contain spaces (e.g. SMS body).
    """
    data = {}
    tokens = line.strip().split()
    current_key = None
    for tok in tokens:
        if '=' in tok:
            k, v = tok.split('=', 1)
            current_key = k
            # Strip trailing commas and whitespace from value
            data[k] = v.rstrip(',').strip()
        else:
            # continuation of previous value
            if current_key:
                data[current_key] = data[current_key] + ' ' + tok.rstrip(',').strip()
            else:
                # no key yet; store under raw_accum (unlikely)
                data.setdefault("_raw", "")
                data["_raw"] += " " + tok.rstrip(',').strip()
    return data

def parse_content_query_output(raw):
    """
    Convert content query raw output into list of dicts.
    Each non-empty line becomes one dict (tolerant).
    """
    rows = []
    if not raw:
        return rows
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # skip 'Rows:' or similar header lines if present
        if line.lower().startswith("row") or "=" in line:
            d = parse_content_line_to_dict(line)
            rows.append(d)
        else:
            rows.append({"raw": line})
    return rows


# -------------------------
# Extraction functions (structured)
# -------------------------
CALL_TYPE_MAP = {
    '1': 'Incoming',
    '2': 'Outgoing',
    '3': 'Missed',
    '4': 'Voicemail',
    '5': 'Rejected',
    '6': 'Blocked',
    '7': 'Answered Externally',
}

def extract_call_logs_structured(days):
    # run adb and parse
    out = run_adb(["adb", "shell", "content", "query", "--uri", "content://call_log/calls/"])
    parsed = parse_content_query_output(out)

    # try to filter by date field (ms)
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    threshold = now_ms - int(days) * 24 * 3600 * 1000
    result = []
    for row in parsed:
        date_raw = row.get("date") or row.get("_id")
        try:
            ts = int(row.get("date"))
            if ts < threshold:
                continue
            date_str = datetime.utcfromtimestamp(ts/1000).strftime("%d-%m-%Y %H:%M:%S")
        except Exception:
            date_str = row.get("date", "")
        type_code = str(row.get("type", "")).strip()
        type_str = CALL_TYPE_MAP.get(type_code, type_code)
        result.append({
            "number": row.get("number", row.get("formatted_number", "")),
            "name": row.get("name", ""),
            "date": date_str,
            "duration": row.get("duration", ""),
            "type": type_str
        })
    return result

def extract_sms_structured(days):
    out = run_adb(["adb", "shell", "content", "query", "--uri", "content://sms/"])
    parsed = parse_content_query_output(out)
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    threshold = now_ms - int(days) * 24 * 3600 * 1000
    result = []
    for row in parsed:
        # some rows may be metadata-only; try to obtain address/body/date
        date_str = ""
        try:
            ts = int(row.get("date"))
            if ts < threshold:
                continue
            date_str = datetime.utcfromtimestamp(ts/1000).strftime("%d-%m-%Y %H:%M:%S")
        except Exception:
            date_str = row.get("date", "")
        result.append({
            "address": row.get("address", ""),
            "date": date_str,
            "body": row.get("body", row.get("snippet", row.get("raw", ""))),
            "type": row.get("type", "")
        })
    return result

def extract_contacts_structured():
    out = run_adb(["adb", "shell", "content", "query", "--uri", "content://contacts/phones/"])
    parsed = parse_content_query_output(out)
    result = []
    for row in parsed:
        result.append({
            "name": row.get("display_name", row.get("name", "")),
            "number": row.get("number", row.get("data1", "")),
            "type": row.get("data2", ""),  # phone type (mobile, home, work, etc.)
            "label": row.get("data3", "")  # custom label
        })
    return result

def extract_apps_structured():
    """Extract installed applications information"""
    apps = []
    try:
        # primary method: list with paths
        out = run_adb(["adb", "shell", "pm", "list", "packages", "-f", "-3"])
        for line in out.splitlines():
            line = line.strip()
            if not line: continue
            # format: package:/data/app/.../base.apk=com.example.app
            if line.startswith("package:"):
                # robust parsing using partition
                _, _, remainder = line.partition("package:")
                path_part, sep, pkg_part = remainder.rpartition("=")
                if sep:
                    apps.append({"package": pkg_part, "path": path_part, "type": "user"})
                else:
                    # fallback if = is missing (rare for -f, but possible if fallback used)
                    apps.append({"package": remainder, "path": "", "type": "user"})
        
        # fallback: if no apps found, try without -f (some devices restrict path visibility)
        if not apps:
            out = run_adb(["adb", "shell", "pm", "list", "packages", "-3"])
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("package:"):
                    pkg = line.replace("package:", "")
                    apps.append({"package": pkg, "path": "hidden", "type": "user"})

        return apps
    except Exception as e:
        return [{"error": f"Failed to extract apps: {str(e)}"}]

def extract_browser_history():
    """Extract browser history (Chrome/Default) - Best Effort"""
    try:
        # Method 1: Try legacy browser content provider (older Android)
        out = run_adb(["adb", "shell", "content", "query", "--uri", "content://browser/bookmarks"])
        parsed = parse_content_query_output(out)
        
        valid_results = []
        if parsed:
             for row in parsed:
                 # Strict validation: A history item MUST have a URL or Title.
                 # ADB sometimes returns weird status lines that parse into empty dicts/garbage.
                 url = row.get("url", "").strip()
                 title = row.get("title", "").strip()
                 
                 if url or title:
                     valid_results.append({
                         "title": title,
                         "url": url,
                         "date": row.get("date", ""),
                         "source": "Stock Browser Provider"
                     })
        
        # Only return if we actually found VALID data
        if valid_results:
            return valid_results

    except Exception:
        pass

    try:
        # Method 2: Try accessing Chrome db directly (requires root/debuggable)
        proc = subprocess.run(["adb", "shell", "run-as", "com.android.chrome", "ls", "/data/data/com.android.chrome/databases/"], 
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode == 0 and b"History" in proc.stdout:
             return [{"note": "Chrome database found. Full extraction requires pulling the 'History' DB file via 'adb pull' which needs root access."}]
    except Exception:
        pass

    try:
        # Method 3: Live/Recent Activity Inspection (dumpsys)
        # Slower but works on non-rooted devices to get OPEN tabs/intents
        out = run_adb(["adb", "shell", "dumpsys", "activity", "activities"])
        # look for http/https links in Intent data
        import re
        # Regex to find URLs in the dumpsys output (often in Intent { data=... })
        urls = re.findall(r'(https?://[a-zA-Z0-9.-]+(?:/[^\s"\']*)?)', out)
        
        unique_urls = set()
        for u in urls:
            # simple filter to avoid junk
            if "." in u and len(u) > 10:
                unique_urls.add(u)
        
        if unique_urls:
            live_results = []
            for u in unique_urls:
                live_results.append({
                    "title": "Active/Recent Tab",
                    "url": u,
                    "date": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                    "source": "Live Memory (dumpsys)"
                })
            return live_results

    except Exception:
        pass

    # If all failed, return explanatory message
    return [{
        "note": "Browser history is protected on modern Android.", 
        "detail": "Extraction requires Root access or a debuggable browser app."
    }]



def extract_photos_metadata(days):
    """Extract photo metadata using MediaStore"""
    try:
        # Query MediaStore for images
        # using datetaken (EXIF time in ms) and date_modified (file time in s)
        out = run_adb(["adb", "shell", "content", "query", "--uri", "content://media/external/images/media", "--projection", "_display_name:_data:_size:datetaken:date_modified:mime_type"])
        parsed = parse_content_query_output(out)
        photos = []
        
        now_ts = int(datetime.utcnow().timestamp())
        threshold = now_ts - (int(days) * 24 * 3600)
        
        # Handle "All time" selection
        if int(days) == 0:
            threshold = 0

        for row in parsed:
            try:
                # 1. Try DATE TAKEN (EXIF) - usually in Milliseconds
                ts_ms = row.get("datetaken")
                if ts_ms and str(ts_ms).isdigit():
                    ts = int(ts_ms) / 1000.0  # convert to seconds
                else:
                    # 2. Fallback to DATE MODIFIED - usually in Seconds
                    ts_mod = row.get("date_modified")
                    if ts_mod and str(ts_mod).isdigit():
                         ts = int(ts_mod)
                    else:
                        ts = 0

                # Filter by date
                if ts < threshold:
                    continue

                date_str = datetime.fromtimestamp(ts).strftime("%d-%m-%Y %H:%M:%S") if ts > 0 else "Unknown"
                
                # Convert size to MB
                size_bytes = int(row.get("_size", 0))
                size_str = f"{size_bytes / (1024*1024):.2f} MB"
                
                photos.append({
                    "filename": row.get("_display_name", ""),
                    "path": row.get("_data", ""),
                    "size": size_str,
                    "date": date_str,
                    "type": row.get("mime_type", "")
                })
            except:
                continue
        return photos
    except Exception as e:
        return [{"error": f"Failed to extract photo metadata: {str(e)}"}]


# -------------------------
# Background job runner (with progress updates)
# -------------------------
def run_job(case_name, case_number, time_range, selections):
    with progress_lock:
        progress.update({"running": True, "percent": 0, "message": "Starting extraction...", "result": None, "error": None, "excel_file": None})

    try:
        if not adb_check():
            raise RuntimeError("ADB not found. Install Android Platform Tools and ensure 'adb' is in PATH.")
        connected, msg = adb_devices()
        if not connected:
            raise RuntimeError(msg)

        # Pre-parse counts to allow per-item progress
        counts = {}
        total_items = 0

        # For each selection, get raw count quickly by running command and counting lines
        if "calls" in selections:
            raw = run_adb(["adb", "shell", "content", "query", "--uri", "content://call_log/calls/"])
            parsed = parse_content_query_output(raw)
            counts["calls"] = len(parsed)
            total_items += counts["calls"]
        if "sms" in selections:
            raw = run_adb(["adb", "shell", "content", "query", "--uri", "content://sms/"])
            parsed = parse_content_query_output(raw)
            counts["sms"] = len(parsed)
            total_items += counts["sms"]
        if "contacts" in selections:
            raw = run_adb(["adb", "shell", "content", "query", "--uri", "content://contacts/phones/"])
            parsed = parse_content_query_output(raw)
            counts["contacts"] = len(parsed)
            total_items += counts["contacts"]
        if "apps" in selections:
            counts["apps"] = 1  # Apps extraction is counted as one step
            total_items += counts["apps"]
        if "browser" in selections:
            counts["browser"] = 1  # Browser extraction is counted as one step
            total_items += counts["browser"]
        if "photos" in selections:
            # Photos = 1 for indexing + 3 for folders (DCIM, Pictures, Download)
            counts["photos"] = 4
            total_items += counts["photos"]

        # if nothing to count, set total_items = number of categories to still show progress
        if total_items == 0:
            total_items = max(1, len(selections))

        processed = 0
        result = {}

        # Extract and update progress per-row
        if "calls" in selections:
            with progress_lock:
                progress["message"] = "Extracting call logs..."
            rows = extract_call_logs_structured(int(time_range))
            processed += len(rows)
            for i in range(len(rows)):
                with progress_lock:
                    progress["percent"] = int((processed / total_items) * 100)
                time.sleep(0.001)
            result["calls"] = rows

        if "sms" in selections:
            with progress_lock:
                progress["message"] = "Extracting SMS..."
            rows = extract_sms_structured(int(time_range))
            processed += len(rows)
            for i in range(len(rows)):
                with progress_lock:
                    progress["percent"] = int((processed / total_items) * 100)
                time.sleep(0.001)
            result["sms"] = rows

        if "contacts" in selections:
            with progress_lock:
                progress["message"] = "Extracting contacts..."
            rows = []
            raw = run_adb(["adb", "shell", "content", "query", "--uri", "content://contacts/phones/"])
            parsed = parse_content_query_output(raw)
            for r in parsed:
                rows.append({
                    "name": r.get("display_name", r.get("name", "")),
                    "number": r.get("number", r.get("data1", "")),
                    "type": r.get("data2", ""),
                    "label": r.get("data3", "")
                })
                processed += 1
                with progress_lock:
                    progress["percent"] = int((processed / total_items) * 100)
                time.sleep(0.005)
            result["contacts"] = rows

        if "apps" in selections:
            with progress_lock:
                progress["message"] = "Extracting installed applications..."
            result["apps"] = extract_apps_structured()
            processed += 1
            with progress_lock:
                progress["percent"] = int((processed / total_items) * 100)

        if "browser" in selections:
            with progress_lock:
                progress["message"] = "Extracting browser history..."
            result["browser"] = extract_browser_history()
            processed += 1
            with progress_lock:
                progress["percent"] = int((processed / total_items) * 100)

        # photos: do at the end (coarse-grained)
        if "photos" in selections:
            with progress_lock:
                progress["message"] = "Indexing photo metadata..."
            
            # 1. Get Metadata List (Professional Index)
            photo_metadata = extract_photos_metadata(int(time_range))
            result["photos_list"] = photo_metadata
            
            processed += 1
            with progress_lock:
                progress["percent"] = int((processed / total_items) * 100)
            
            # 2. Physical Pull (Granular Updates)
            case_dir = os.path.join("extracted_data", f"{case_name}_{case_number}")
            os.makedirs(case_dir, exist_ok=True)
            
            pull_log = []
            # Expanded targets
            targets = ["/sdcard/DCIM", "/sdcard/Pictures", "/sdcard/Download"]
            
            for tgt in targets:
                folder_name = os.path.basename(tgt)
                with progress_lock:
                    progress["message"] = f"Pulling {folder_name} (Large transfer, please wait)..."
                
                local_dest = os.path.join(case_dir, folder_name)
                try:
                    # check if source exists first to avoid noisy error
                    check = subprocess.run(["adb", "shell", "ls", "-d", tgt], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if check.returncode != 0:
                        pull_log.append({"source": tgt, "status": "Skipped (Not found)"})
                    else:
                        proc = subprocess.run(["adb", "pull", tgt, local_dest], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        if proc.returncode == 0:
                            pull_log.append({"source": tgt, "destination": local_dest, "status": "Success"})
                        else:
                            output = proc.stdout.decode("utf-8") + proc.stderr.decode("utf-8")
                            pull_log.append({"source": tgt, "status": "Partial/Fail", "details": output[:200]})
                except Exception as e:
                    pull_log.append({"source": tgt, "status": "Error", "details": str(e)})
                
                # Update progress after EACH folder
                processed += 1
                with progress_lock:
                    progress["percent"] = int((processed / total_items) * 100)
            
            result["photos_pull_log"] = pull_log

        # finalize and save excel
        with progress_lock:
            progress["message"] = "Saving reports (Excel + PDF)..."

        # Excel
        excel_filename = f"{case_name}_{case_number}.xlsx"
        excel_path = os.path.join("extracted_data", excel_filename)
        
        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                if result.get("calls"):
                    pd.DataFrame(result["calls"]).to_excel(writer, sheet_name="Calls", index=False)
                if result.get("sms"):
                    pd.DataFrame(result["sms"]).to_excel(writer, sheet_name="SMS", index=False)
                if result.get("contacts"):
                    pd.DataFrame(result["contacts"]).to_excel(writer, sheet_name="Contacts", index=False)
                if result.get("apps"):
                    pd.DataFrame(result["apps"]).to_excel(writer, sheet_name="Apps", index=False)
                if result.get("browser"):
                    pd.DataFrame(result["browser"]).to_excel(writer, sheet_name="Browser", index=False)
                if result.get("photos_list"):
                    pd.DataFrame(result["photos_list"]).to_excel(writer, sheet_name="Photos Index", index=False)
                if result.get("photos_pull_log"):
                    pd.DataFrame(result["photos_pull_log"]).to_excel(writer, sheet_name="Photos Log", index=False)
        except Exception as e:
            print(f"Error saving Excel: {e}")

        # PDF Report
        pdf_filename = f"{case_name}_{case_number}_Report.pdf"
        pdf_path = os.path.join("extracted_data", pdf_filename)
        try:
            generate_pdf_case_report(result, case_name, case_number, pdf_path)
            progress["pdf_file"] = pdf_filename
        except Exception as e:
            print(f"Error saving PDF: {e}")

        with progress_lock:
            progress["running"] = False
            progress["percent"] = 100
            progress["message"] = "Extraction Complete."
            progress["result"] = result
            progress["excel_file"] = excel_filename
            progress["pdf_file"] = pdf_filename
    
    except Exception as e:
        with progress_lock:
            progress["running"] = False
            progress["error"] = str(e)
            progress["result"] = None


def generate_pdf_case_report(result_data, case_name, case_number, filename):
    """
    Generate a professional PDF report using ReportLab.
    """
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title = Paragraph(f"Forensic Extraction Report", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 12))
    
    # Case Details
    story.append(Paragraph(f"<b>Case Name:</b> {case_name}", styles['Normal']))
    story.append(Paragraph(f"<b>Case Number:</b> {case_number}", styles['Normal']))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 24))
    
    # Summary Table
    story.append(Paragraph("<b>Extraction Summary</b>", styles['Heading2']))
    story.append(Spacer(1, 12))
    
    summary_data = [["Category", "Items Extracted"]]
    for key in ["calls", "sms", "contacts", "apps", "browser", "photos_list"]:
        items = result_data.get(key, [])
        label = "Photos" if key == "photos_list" else key.capitalize()
        summary_data.append([label, str(len(items))])
        
    t_summary = Table(summary_data, colWidths=[200, 100])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 24))
    
    # Detailed Sections (Preview)
    for key, label in [("calls", "Call Logs"), ("sms", "SMS Messages"), ("contacts", "Contacts")]:
        items = result_data.get(key, [])
        if not items:
            continue
            
        story.append(Paragraph(f"<b>{label} (First 50 items)</b>", styles['Heading2']))
        story.append(Spacer(1, 12))
        
        # Create table data
        if items:
            headers = list(items[0].keys())
            # wrap in list of lists
            table_data = [headers]
            for item in items[:50]: # limit to 50 for PDF
                row = [str(item.get(h, ""))[:50] for h in headers] # truncate long text
                table_data.append(row)
                
            t = Table(table_data, colWidths=[450/len(headers)]*len(headers))
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 0), (-1, -1), 8)
            ]))
            story.append(t)
            story.append(Spacer(1, 24))

    doc.build(story)


# -------------------------
# Flask routes
# -------------------------
@mobile_bp.route("/")
def index_route():
    return render_template("mobile_index.html")

@mobile_bp.route("/start", methods=["POST"])
def start_route():
    with progress_lock:
        if progress["running"]:
            return jsonify({"status": "busy", "message": "Extraction already running"}), 409

    form = request.form
    case_name = form.get("case_name", "case")
    case_number = form.get("case_number", "001")
    time_range = form.get("time_range", "10")
    selections = request.form.getlist("data_types")

    # start background thread
    t = threading.Thread(target=run_job, args=(case_name, case_number, time_range, selections), daemon=True)
    t.start()
    return jsonify({"status": "started", "message": "Job started"})

@mobile_bp.route("/progress")
def progress_route():
    with progress_lock:
        return jsonify({
            "running": progress["running"],
            "percent": progress["percent"],
            "message": progress["message"],
            "error": progress.get("error"),
            "excel_file": progress.get("excel_file")
        })

@mobile_bp.route("/result")
def result_route():
    with progress_lock:
        return jsonify({
            "result": progress.get("result"),
            "error": progress.get("error")
        })

@mobile_bp.route("/download/<path:filename>")
def download_file(filename):
    # Security check: ensure no path traversal
    safe_name = os.path.basename(filename)
    return send_file(os.path.join("extracted_data", safe_name), as_attachment=True)



@mobile_bp.route("/device-status")
def device_status_route():
    """Return current device connection status"""
    adb_available = adb_check()
    device_connected = False
    authorized = False
    
    if adb_available:
        connected, msg = adb_devices()
        device_connected = connected
        authorized = "unauthorized" not in msg.lower()
    
    return jsonify({
        "adb_available": adb_available,
        "device_connected": device_connected,
        "authorized": authorized,
        "message": msg if not adb_available else ("Device connected and authorized" if authorized else "Device not properly connected")
    })

# Blueprint does not have main block
