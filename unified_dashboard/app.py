from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from unified_dashboard.extensions import db
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta

# Initialize App
app = Flask(__name__)
app.config['SECRET_KEY'] = 'cyber-tools-secure-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)

# Import Shared Extensions
from unified_dashboard.extensions import db, socketio
db.init_app(app)
socketio.init_app(app)

# Ensure responses aren't cached
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Import Blueprints
from unified_dashboard.modules.ram_forensics.routes import ram_bp
from unified_dashboard.modules.mobile_forensics.routes import mobile_bp
from unified_dashboard.modules.nmap_scanner.routes import nmap_bp
from unified_dashboard.modules.network_analyzer.routes import network_bp

# Register Blueprints
app.register_blueprint(ram_bp)
app.register_blueprint(mobile_bp)
app.register_blueprint(nmap_bp)
app.register_blueprint(network_bp)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Models ---
from datetime import datetime

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), default='user') # 'user' or 'admin'

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('activity_logs', lazy=True))
    action = db.Column(db.String(100), nullable=False) # LOGIN, LOGOUT, TOOL_ACCESS
    details = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('public_dashboard.html')

from flask import session

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # Log the auto-logout
        log = ActivityLog(user_id=current_user.id, action='LOGOUT', details='Auto-logout via Login Page Navigation')
        db.session.add(log)
        db.session.commit()
        
        logout_user()
        flash('You have been logged out.', 'info')
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            session.permanent = True  # Enable 5-minute timeout
            
            # Log Activity
            log = ActivityLog(user_id=user.id, action='LOGIN', details='User logged in via Web UI')
            db.session.add(log)
            db.session.commit()
            
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Login Failed. Check email and password.', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Helper route to create users."""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'warning')
            return redirect(url_for('register'))
            
        # First user is admin
        role = 'admin' if User.query.count() == 0 else 'user'
            
        new_user = User(username=username, email=email, password=generate_password_hash(password), role=role)
        db.session.add(new_user)
        db.session.commit()
        flash(f'Account created as {role}! Please login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    log = ActivityLog(user_id=current_user.id, action='LOGOUT', details='User logged out')
    db.session.add(log)
    db.session.commit()
    
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access Denied. Admins only.', 'danger')
        return redirect(url_for('dashboard'))
        
    users = User.query.all()
    
    # Filter logs to last 3 months
    cutoff_date = datetime.utcnow() - timedelta(days=90)
    
    # Fetch logs sorted by user and time ASC to calculate duration
    all_logs_asc = ActivityLog.query.filter(ActivityLog.timestamp >= cutoff_date).order_by(ActivityLog.user_id, ActivityLog.timestamp.asc()).all()
    
    display_logs = []
    
    # Group logs by user to calculate durations
    from collections import defaultdict
    user_logs = defaultdict(list)
    for log in all_logs_asc:
        user_logs[log.user_id].append(log)
        
    for uid, u_logs in user_logs.items():
        for i in range(len(u_logs)):
            current_log = u_logs[i]
            ist_time = current_log.timestamp + timedelta(hours=5, minutes=30)
            
            duration = "Active"
            if i < len(u_logs) - 1:
                next_log = u_logs[i+1]
                diff = next_log.timestamp - current_log.timestamp
                
                # Format duration
                total_seconds = int(diff.total_seconds())
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                duration = f"{minutes}m {seconds}s"
            
            if current_log.action == 'LOGOUT':
                duration = "Session Ended"
                
            display_logs.append({
                'timestamp': ist_time,
                'user': current_log.user,
                'action': current_log.action,
                'details': current_log.details,
                'duration': duration
            })
            
    # Sort for final display (Newest First)
    display_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return render_template('admin_dashboard.html', user=current_user, users=users, logs=display_logs)

import csv
from flask import Response
from io import StringIO

@app.route('/admin/download_logs')
@login_required
def download_logs():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
        
    # Filter logs to last 3 months
    cutoff_date = datetime.utcnow() - timedelta(days=90)
    logs = ActivityLog.query.filter(ActivityLog.timestamp >= cutoff_date).order_by(ActivityLog.timestamp.desc()).all()
    
    # Generate CSV
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Timestamp (IST)', 'User', 'Action', 'Details'])
    
    for log in logs:
        ist_time = log.timestamp + timedelta(hours=5, minutes=30)
        cw.writerow([log.id, ist_time.strftime('%Y-%m-%d %H:%M:%S'), log.user.username, log.action, log.details])
        
    output = si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=activity_logs_3months.csv"})

@app.route('/tools')
@login_required
def tools_overview():
    return render_template('tools_overview.html', user=current_user)

@app.route('/tools/<category>')
@login_required
def tools_category(category):
    if category == 'pentesting':
        return render_template('tools_pentesting.html', user=current_user)
    elif category == 'forensics':
        return render_template('tools_forensics.html', user=current_user)
    else:
        return redirect(url_for('tools_overview'))

@app.route('/tools/nmap')
@login_required
def tool_nmap():
    # Log Access
    log = ActivityLog(user_id=current_user.id, action='TOOL_ACCESS', details='Accessed Nmap Scanner')
    db.session.add(log)
    db.session.commit()
    return render_template('tool_nmap.html', user=current_user)

@app.route('/tools/wireshark')
@login_required
def tool_wireshark():
    log = ActivityLog(user_id=current_user.id, action='TOOL_ACCESS', details='Accessed Wireshark Analyzer')
    db.session.add(log)
    db.session.commit()
    return render_template('tool_wireshark.html', user=current_user)

@app.route('/tools/mobile')
@login_required
def tool_mobile():
    log = ActivityLog(user_id=current_user.id, action='TOOL_ACCESS', details='Accessed Mobile Forensics')
    db.session.add(log)
    db.session.commit()
    return render_template('tool_mobile.html', user=current_user)

@app.route('/tools/ram')
@login_required
def tool_ram():
    log = ActivityLog(user_id=current_user.id, action='TOOL_ACCESS', details='Accessed RAM Forensics')
    db.session.add(log)
    db.session.commit()
    return render_template('tool_ram.html', user=current_user)

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)

