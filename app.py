from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import pytz
import os
import random
import json
import numpy as np
from geopy.geocoders import Nominatim
import time

try:
    import openpyxl
    from io import BytesIO
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    print("⚠️ openpyxl not installed. Excel export will not work.")

app = Flask(__name__)
app.secret_key = 'change-this-to-a-random-secret-key-123!@#'

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ==================== DATABASE MODELS ====================
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reg_no = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    mobile = db.Column(db.String(15), nullable=False)
    course = db.Column(db.String(50), nullable=False, default="BCA")
    year = db.Column(db.String(10), nullable=False, default="1st")
    password_hash = db.Column(db.String(200), nullable=False)
    face_descriptor = db.Column(db.Text, nullable=True)
    photo = db.Column(db.Text, nullable=True)
    security_question = db.Column(db.String(200), nullable=False, default="What is your pet's name?")
    security_answer = db.Column(db.String(100), nullable=False, default="")
    attendances = db.relationship('Attendance', backref='student', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    location_name = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default='Present')

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(50), nullable=False, default='ALL')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Holiday(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)

class AppSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_working_days = db.Column(db.Integer, default=90)
    minimum_percent = db.Column(db.Integer, default=75)

ADMIN_SECRET_ANSWER = 'visionlog'

SECURITY_QUESTIONS = [
    "What is your pet's name?",
    "What is your mother's maiden name?",
    "What was your first school?",
    "What is your favorite book?",
    "What city were you born in?"
]

COURSES = ["BCA", "BCOM", "BBA", "BSC", "BA", "MCA", "MBA", "MTECH", "BTECH"]
YEARS = ["1st", "2nd", "3rd"]

DEFAULT_ADMINS = [
    {'username': 'admin', 'password': 'admin123', 'department': 'ALL'},
    {'username': 'bca_admin', 'password': 'bca123', 'department': 'BCA'},
    {'username': 'bcom_admin', 'password': 'bcom123', 'department': 'BCOM'},
    {'username': 'bba_admin', 'password': 'bba123', 'department': 'BBA'},
    {'username': 'bsc_admin', 'password': 'bsc123', 'department': 'BSC'},
    {'username': 'ba_admin', 'password': 'ba123', 'department': 'BA'},
    {'username': 'mca_admin', 'password': 'mca123', 'department': 'MCA'},
    {'username': 'mba_admin', 'password': 'mba123', 'department': 'MBA'},
    {'username': 'mtech_admin', 'password': 'mtech123', 'department': 'MTECH'},
    {'username': 'btech_admin', 'password': 'btech123', 'department': 'BTECH'},
]

# ==================== HELPER FUNCTIONS ====================
def init_admins():
    for admin_data in DEFAULT_ADMINS:
        existing = Admin.query.filter_by(username=admin_data['username']).first()
        if not existing:
            new_admin = Admin(username=admin_data['username'], department=admin_data['department'])
            new_admin.set_password(admin_data['password'])
            db.session.add(new_admin)
    db.session.commit()

def generate_captcha():
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    op = random.choice(['+', '-'])
    if op == '+': ans = num1 + num2
    else:
        if num1 < num2: num1, num2 = num2, num1
        ans = num1 - num2
    return f"{num1} {op} {num2} = ?", ans

def get_location_name(lat, lon):
    if not lat or not lon: return "Location not available"
    try:
        geolocator = Nominatim(user_agent="visionlog_app_v1")
        location = geolocator.reverse(f"{lat}, {lon}", exactly_one=True, language='en')
        time.sleep(1)
        if location and location.raw.get('address'):
            addr = location.raw['address']
            parts = []
            if addr.get('suburb'): parts.append(addr['suburb'])
            elif addr.get('neighbourhood'): parts.append(addr['neighbourhood'])
            elif addr.get('road'): parts.append(addr['road'])
            if addr.get('city'): parts.append(addr['city'])
            elif addr.get('town'): parts.append(addr['town'])
            elif addr.get('village'): parts.append(addr['village'])
            if not parts: return location.address.split(',')[0]
            return ', '.join(parts[:2])
        return "Unknown area"
    except Exception as e:
        print(f"Geocoding error: {e}")
        return "Location lookup failed"

def get_next_regno(course):
    last_student = Student.query.filter(Student.reg_no.like(f"{course}%")).order_by(Student.id.desc()).first()
    if last_student:
        try:
            num_part = last_student.reg_no[len(course):]
            next_num = int(num_part) + 1
            return f"{course}{next_num:03d}"
        except ValueError: return f"{course}001"
    return f"{course}001"

def get_app_settings():
    settings = AppSettings.query.first()
    if not settings:
        settings = AppSettings()
        db.session.add(settings)
        db.session.commit()
    return {'total_working_days': settings.total_working_days, 'minimum_percent': settings.minimum_percent}

def get_attendance_with_working_days(student_id):
    settings = get_app_settings()
    total_working = settings['total_working_days']
    present = Attendance.query.filter_by(student_id=student_id, status='Present').count()
    percentage = round((present / total_working * 100), 2) if total_working > 0 else 0
    if percentage >= settings['minimum_percent']: zone = 'green'; status_text = 'SAFE'
    elif percentage >= 60: zone = 'yellow'; status_text = 'WARNING'
    else: zone = 'red'; status_text = 'CRITICAL'
    shortage = max(0, int(total_working * settings['minimum_percent'] / 100) - present)
    return {'present': present, 'total_working': total_working, 'percentage': percentage,
            'zone': zone, 'status_text': status_text, 'shortage': shortage}

def get_admin_department():
    if 'admin_id' in session:
        admin = Admin.query.get(session['admin_id'])
        if admin: return admin.department
    return None

def get_ist_time():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

# ==================== PUBLIC TUNNEL ROUTE (NEW - Added without changing existing code) ====================
@app.route('/tunnel')
def public_tunnel():
    """Public tunnel endpoint - confirms the app is running and accessible"""
    return jsonify({
        'status': 'running',
        'app': 'VisionLog - AI Facial Recognition Attendance System',
        'version': '1.0',
        'endpoints': {
            'home': url_for('home', _external=True),
            'admin_login': url_for('admin_login', _external=True),
            'student_login': url_for('student_login', _external=True),
            'student_register': url_for('student_register', _external=True),
            'qr_scanner': url_for('qr_scanner', _external=True) if 'qr_scanner' in [r.rule for r in app.url_map.iter_rules()] else None,
            'api_counts': url_for('api_counts', _external=True)
        },
        'timestamp': get_ist_time().strftime('%Y-%m-%d %I:%M:%S %p'),
        'message': 'VisionLog is running successfully!'
    })

# ==================== QR CODE ROUTES (NEW - Added for QR attendance feature) ====================
@app.route('/qr-attend/<reg_no>')
def qr_attend(reg_no):
    """Secure QR attendance - still requires blink + face verification"""
    student = Student.query.filter_by(reg_no=reg_no).first()
    if not student:
        flash('Invalid QR code! Student not found.', 'error')
        return redirect(url_for('student_login'))
    
    # Auto-login the student for camera access
    session['student_id'] = student.id
    session['student_name'] = student.name
    
    flash(f'Welcome {student.name}! Please look at the camera and blink to verify.', 'info')
    return redirect(url_for('mark_attendance_page'))

@app.route('/qr-scanner')
def qr_scanner():
    """QR Code attendance page - webcam scans student QR codes"""
    return render_template('qr_scanner.html')

@app.route('/api/qr-attendance', methods=['POST'])
def qr_attendance():
    """API endpoint for QR code attendance"""
    reg_no = request.json.get('reg_no')
    if not reg_no:
        return jsonify({'success': False, 'message': 'No registration number found'})
    
    student = Student.query.filter_by(reg_no=reg_no).first()
    if not student:
        return jsonify({'success': False, 'message': 'Student not found'})
    
    # Check if already marked today
    today = get_ist_time().date()
    already_marked = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.timestamp >= datetime.combine(today, datetime.min.time()),
        Attendance.timestamp <= datetime.combine(today, datetime.max.time())
    ).first()
    
    if already_marked:
        time_str = already_marked.timestamp.strftime('%I:%M %p')
        return jsonify({
            'success': False, 
            'message': f'{student.name} already marked {already_marked.status} today at {time_str}'
        })
    
    # Mark attendance
    att = Attendance(
        student_id=student.id,
        latitude=None,
        longitude=None,
        location_name='QR Code Scan',
        status='Present'
    )
    db.session.add(att)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'✅ Attendance marked for {student.name} ({student.reg_no}) - {student.course} {student.year} Year',
        'student': {
            'name': student.name,
            'reg_no': student.reg_no,
            'course': student.course,
            'year': student.year
        }
    })

@app.route('/admin/student-qr-codes')
def student_qr_codes():
    """Generate printable QR codes for each student"""
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    students = Student.query.order_by(Student.course, Student.year, Student.reg_no).all()
    return render_template('student_qr.html', students=students)

# ==================== HOME ROUTE ====================
@app.route('/')
def home():
    return render_template('index.html')

# ==================== ADMIN ROUTES ====================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session.pop('student_id', None)
            session['admin_logged_in'] = True
            session['admin_id'] = admin.id
            session['admin_department'] = admin.department
            session['admin_username'] = admin.username
            flash(f'Welcome {admin.username}!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid username or password!', 'error')
    return render_template('admin_login.html')

@app.route('/admin/forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():
    if request.method == 'POST':
        answer = request.form.get('answer')
        if answer.lower() == ADMIN_SECRET_ANSWER.lower():
            flash('Password reset is handled by super admin.', 'info')
            return redirect(url_for('admin_login'))
        else: flash('Incorrect answer.', 'error')
    return render_template('admin_forgot_password.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    session.pop('student_id', None)
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    dept = get_admin_department()
    course_filter = request.args.get('course', '')
    year_filter = request.args.get('year', '')
    if dept != 'ALL' and not course_filter: course_filter = dept
    query = Student.query
    if course_filter: query = query.filter_by(course=course_filter)
    if year_filter: query = query.filter_by(year=year_filter)
    students = query.order_by(Student.course, Student.year, Student.reg_no).all()
    student_data = []; green_count = yellow_count = red_count = 0
    for s in students:
        stats = get_attendance_with_working_days(s.id)
        student_data.append({'student': s, 'stats': stats})
        if stats['zone'] == 'green': green_count += 1
        elif stats['zone'] == 'yellow': yellow_count += 1
        else: red_count += 1
    course_stats = []
    for course in (COURSES if dept == 'ALL' else [dept]):
        count = Student.query.filter_by(course=course).count()
        if count > 0: course_stats.append({'course': course, 'count': count})
    return render_template('admin_dashboard.html', student_data=student_data,
                         courses=COURSES if dept == 'ALL' else [dept],
                         years=YEARS, selected_course=course_filter, selected_year=year_filter,
                         course_stats=course_stats, green_count=green_count,
                         yellow_count=yellow_count, red_count=red_count,
                         admin_username=session.get('admin_username'))

@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    settings = AppSettings.query.first()
    if not settings: settings = AppSettings(); db.session.add(settings); db.session.commit()
    if request.method == 'POST':
        settings.total_working_days = int(request.form.get('total_working_days', 90))
        settings.minimum_percent = int(request.form.get('minimum_percent', 75))
        db.session.commit()
        flash('Settings updated!', 'success')
        return redirect(url_for('admin_settings'))
    return render_template('admin_settings.html', settings=settings,
                         student_count=Student.query.count(), attendance_count=Attendance.query.count())

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/admin/student/add', methods=['GET', 'POST'])
def add_student():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    dept = get_admin_department()
    courses = COURSES if dept == 'ALL' else [dept]
    if request.method == 'POST':
        reg_no = request.form.get('reg_no'); course = request.form.get('course')
        if dept != 'ALL': course = dept
        if not reg_no: reg_no = get_next_regno(course)
        if Student.query.filter((Student.reg_no == reg_no) | (Student.email == request.form['email'])).first():
            flash('Reg no or email exists!', 'error')
            return redirect(url_for('add_student'))
        student = Student(reg_no=reg_no, email=request.form['email'], name=request.form['name'],
                         mobile=request.form['mobile'], course=course,
                         year=request.form.get('year', '1st'))
        student.set_password(request.form['password'])
        db.session.add(student); db.session.commit()
        flash(f'Student added! Reg No: {reg_no}', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('add_student.html', courses=courses, years=YEARS)

@app.route('/admin/student/edit/<int:id>', methods=['GET', 'POST'])
def edit_student(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    dept = get_admin_department()
    courses = COURSES if dept == 'ALL' else [dept]
    student = Student.query.get_or_404(id)
    if request.method == 'POST':
        if Student.query.filter(Student.reg_no == request.form['reg_no'], Student.id != id).first():
            flash('Reg no exists!', 'error')
            return render_template('edit_student.html', student=student, courses=courses, years=YEARS)
        student.reg_no = request.form['reg_no']
        student.name = request.form['name']
        student.email = request.form['email']
        student.mobile = request.form['mobile']
        student.year = request.form.get('year', student.year)
        if dept == 'ALL': student.course = request.form['course']
        if request.form.get('password'): student.set_password(request.form['password'])
        db.session.commit()
        flash('Student updated!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('edit_student.html', student=student, courses=courses, years=YEARS)

@app.route('/admin/student/delete/<int:id>')
def delete_student(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    db.session.delete(Student.query.get_or_404(id))
    db.session.commit()
    flash('Student deleted!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export-attendance')
def export_attendance():
    if not session.get('admin_logged_in') or not OPENPYXL_AVAILABLE: return redirect(url_for('admin_dashboard'))
    dept = get_admin_department()
    course_filter = request.args.get('course', '')
    year_filter = request.args.get('year', '')
    if dept != 'ALL': course_filter = dept
    export_type = request.args.get('type', 'summary')
    wb = openpyxl.Workbook()
    query = Student.query
    if course_filter: query = query.filter_by(course=course_filter)
    if year_filter: query = query.filter_by(year=year_filter)
    if export_type == 'summary':
        ws = wb.active; ws.title = "Summary"
        ws.append(['ID','Name','Reg No','Course','Year','Present','Days','%','Status','Shortage','Location'])
        for s in query.all():
            st = get_attendance_with_working_days(s.id)
            loc = Attendance.query.filter_by(student_id=s.id).order_by(Attendance.timestamp.desc()).first()
            ws.append([s.id, s.name, s.reg_no, s.course, s.year, st['present'], st['total_working'],
                      f"{st['percentage']}%", st['status_text'], st['shortage'],
                      loc.location_name if loc else 'N/A'])
    else:
        ws = wb.active; ws.title = "Detailed"
        q = db.session.query(Attendance, Student).join(Student)
        if course_filter: q = q.filter(Student.course == course_filter)
        if year_filter: q = q.filter(Student.year == year_filter)
        ws.append(['ID','Name','Reg No','Course','Year','Date','Time','Status','Location'])
        for a, s in q.order_by(Attendance.timestamp.desc()).all():
            ws.append([s.id, s.name, s.reg_no, s.course, s.year, a.timestamp.strftime('%Y-%m-%d'),
                      a.timestamp.strftime('%H:%M:%S'), a.status, a.location_name or 'N/A'])
    o = BytesIO(); wb.save(o); o.seek(0)
    return send_file(o, as_attachment=True, download_name=f'attendance_{course_filter or "all"}_{export_type}.xlsx')

@app.route('/admin/export-green')
def export_green():
    if not session.get('admin_logged_in') or not OPENPYXL_AVAILABLE: return redirect(url_for('admin_dashboard'))
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Safe"
    ws.append(['Reg No','Name','Course','Year','Present','Days','%','Status','Location'])
    for s in Student.query.all():
        st = get_attendance_with_working_days(s.id)
        if st['zone'] == 'green':
            loc = Attendance.query.filter_by(student_id=s.id).order_by(Attendance.timestamp.desc()).first()
            ws.append([s.reg_no, s.name, s.course, s.year, st['present'], st['total_working'],
                      f"{st['percentage']}%", 'SAFE', loc.location_name if loc else 'N/A'])
    o = BytesIO(); wb.save(o); o.seek(0)
    return send_file(o, as_attachment=True, download_name='Safe_Students.xlsx')

@app.route('/admin/export-yellow')
def export_yellow():
    if not session.get('admin_logged_in') or not OPENPYXL_AVAILABLE: return redirect(url_for('admin_dashboard'))
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Warning"
    ws.append(['Reg No','Name','Course','Year','Present','Days','%','Status','Shortage','Location'])
    for s in Student.query.all():
        st = get_attendance_with_working_days(s.id)
        if st['zone'] == 'yellow':
            loc = Attendance.query.filter_by(student_id=s.id).order_by(Attendance.timestamp.desc()).first()
            ws.append([s.reg_no, s.name, s.course, s.year, st['present'], st['total_working'],
                      f"{st['percentage']}%", 'WARNING', st['shortage'], loc.location_name if loc else 'N/A'])
    o = BytesIO(); wb.save(o); o.seek(0)
    return send_file(o, as_attachment=True, download_name='Warning_Students.xlsx')

@app.route('/admin/export-red')
def export_red():
    if not session.get('admin_logged_in') or not OPENPYXL_AVAILABLE: return redirect(url_for('admin_dashboard'))
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Critical"
    ws.append(['Reg No','Name','Course','Year','Present','Days','%','Status','Shortage','Location'])
    for s in Student.query.all():
        st = get_attendance_with_working_days(s.id)
        if st['zone'] == 'red':
            loc = Attendance.query.filter_by(student_id=s.id).order_by(Attendance.timestamp.desc()).first()
            ws.append([s.reg_no, s.name, s.course, s.year, st['present'], st['total_working'],
                      f"{st['percentage']}%", 'CRITICAL', st['shortage'], loc.location_name if loc else 'N/A'])
    o = BytesIO(); wb.save(o); o.seek(0)
    return send_file(o, as_attachment=True, download_name='Critical_Students.xlsx')

@app.route('/admin/export-pdf')
def export_pdf():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    from fpdf import FPDF
    dept = get_admin_department()
    course_filter = dept if dept != 'ALL' else request.args.get('course', '')
    year_filter = request.args.get('year', '')
    settings = get_app_settings()
    pdf = FPDF(); pdf.add_page()
    pdf.set_font('Helvetica', 'B', 18)
    pdf.cell(0, 12, 'VisionLog - Attendance Report', ln=True, align='C')
    pdf.ln(3)
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, f'Days: {settings["total_working_days"]} | Min: {settings["minimum_percent"]}%', ln=True, align='C')
    pdf.ln(5)
    pdf.set_font('Helvetica', 'B', 9); pdf.set_fill_color(167,139,250); pdf.set_text_color(255,255,255)
    pdf.cell(10,8,'ID',1,0,'C',True); pdf.cell(30,8,'Name',1,0,'C',True)
    pdf.cell(25,8,'Reg No',1,0,'C',True); pdf.cell(18,8,'Course',1,0,'C',True)
    pdf.cell(12,8,'Year',1,0,'C',True); pdf.cell(16,8,'Present',1,0,'C',True)
    pdf.cell(16,8,'%',1,0,'C',True); pdf.cell(28,8,'Status',1,0,'C',True)
    pdf.cell(35,8,'Location',1,1,'C',True)
    pdf.set_text_color(0,0,0)
    q = Student.query
    if course_filter: q = q.filter_by(course=course_filter)
    if year_filter: q = q.filter_by(year=year_filter)
    for s in q.all():
        st = get_attendance_with_working_days(s.id)
        loc = Attendance.query.filter_by(student_id=s.id).order_by(Attendance.timestamp.desc()).first()
        l = loc.location_name if loc else 'N/A'
        c = (209,250,229) if st['zone']=='green' else (254,243,199) if st['zone']=='yellow' else (254,226,226)
        pdf.set_fill_color(*c); pdf.set_font('Helvetica', '', 7)
        pdf.cell(10,7,str(s.id),1,0,'C',True); pdf.cell(30,7,s.name[:18],1,0,'L',True)
        pdf.cell(25,7,s.reg_no,1,0,'C',True); pdf.cell(18,7,s.course,1,0,'C',True)
        pdf.cell(12,7,s.year,1,0,'C',True)
        pdf.cell(16,7,f"{st['present']}/{st['total_working']}",1,0,'C',True)
        pdf.cell(16,7,f"{st['percentage']}%",1,0,'C',True)
        pdf.cell(28,7,st['status_text'],1,0,'C',True); pdf.cell(35,7,l[:18],1,1,'C',True)
    pdf_output = BytesIO()
    pdf.output(pdf_output); pdf_output.seek(0)
    return send_file(pdf_output, as_attachment=True, download_name='attendance_report.pdf', mimetype='application/pdf')

@app.route('/student/export-my-pdf')
def student_export_pdf():
    if 'student_id' not in session: return redirect(url_for('student_login'))
    from fpdf import FPDF
    s = Student.query.get(session['student_id'])
    st = get_attendance_with_working_days(s.id)
    pdf = FPDF(); pdf.add_page()
    pdf.set_font('Helvetica', 'B', 18)
    pdf.cell(0, 12, 'VisionLog - My Attendance Report', ln=True, align='C')
    pdf.ln(5); pdf.set_font('Helvetica', '', 12)
    pdf.cell(0,8,f'Name: {s.name}',ln=True); pdf.cell(0,8,f'Reg: {s.reg_no}',ln=True)
    pdf.cell(0,8,f'Course: {s.course}',ln=True); pdf.cell(0,8,f'Year: {s.year}',ln=True)
    pdf.cell(0,8,f'Email: {s.email}',ln=True)
    pdf.ln(5); pdf.set_font('Helvetica', 'B', 13); pdf.cell(0,9,'Summary',ln=True)
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0,7,f'Present: {st["present"]}/{st["total_working"]}',ln=True)
    pdf.cell(0,7,f'Percentage: {st["percentage"]}%',ln=True)
    pdf.cell(0,7,f'Status: {st["status_text"]}',ln=True)
    if st['shortage']>0: pdf.cell(0,7,f'Need {st["shortage"]} more days',ln=True)
    pdf_output = BytesIO()
    pdf.output(pdf_output); pdf_output.seek(0)
    return send_file(pdf_output, as_attachment=True, download_name=f'{s.reg_no}_attendance.pdf', mimetype='application/pdf')

@app.route('/admin/holidays', methods=['GET', 'POST'])
def admin_holidays():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    if request.method == 'POST':
        date_str = request.form.get('date'); name = request.form.get('name')
        if date_str and name:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if not Holiday.query.filter_by(date=date).first():
                db.session.add(Holiday(date=date, name=name))
                db.session.commit()
                flash(f'Holiday "{name}" added!', 'success')
            else: flash('Date already exists!', 'error')
        return redirect(url_for('admin_holidays'))
    holidays = Holiday.query.order_by(Holiday.date).all()
    return render_template('holidays.html', holidays=holidays)

@app.route('/admin/holidays/delete/<int:id>')
def delete_holiday(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    db.session.delete(Holiday.query.get_or_404(id))
    db.session.commit()
    flash('Holiday deleted!', 'success')
    return redirect(url_for('admin_holidays'))

@app.route('/admin/view-attendance')
def view_attendance():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    dept = get_admin_department()
    cf = request.args.get('course', '') or (dept if dept != 'ALL' else '')
    yf = request.args.get('year', '')
    q = db.session.query(Attendance, Student).join(Student)
    if cf: q = q.filter(Student.course == cf)
    if yf: q = q.filter(Student.year == yf)
    available_courses = COURSES if dept == 'ALL' else [dept]
    return render_template('view_attendance.html', records=q.order_by(Attendance.timestamp.desc()).all(),
                         courses=available_courses, years=YEARS,
                         selected_course=cf, selected_year=yf)

@app.route('/admin/student/<int:id>/chart')
def admin_student_chart(id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    s = Student.query.get_or_404(id)
    st = get_attendance_with_working_days(s.id)
    settings = get_app_settings()
    lbs=[]; pr=[]; ab=[]
    for i in range(6,-1,-1):
        d = get_ist_time().date()-timedelta(days=i)
        lbs.append(d.strftime('%a'))
        ds = datetime.combine(d, datetime.min.time()); de = datetime.combine(d, datetime.max.time())
        pr.append(Attendance.query.filter_by(student_id=s.id, status='Present').filter(Attendance.timestamp>=ds, Attendance.timestamp<=de).count())
        ab.append(Attendance.query.filter_by(student_id=s.id, status='Absent').filter(Attendance.timestamp>=ds, Attendance.timestamp<=de).count())
    return render_template('student_chart.html', student=s, stats=st, settings=settings,
                         daily_labels=lbs, daily_present=pr, daily_absent=ab)

@app.route('/api/counts')
def api_counts():
    student_count = Student.query.count()
    attendance_count = Attendance.query.count()
    stream_count = db.session.query(Student.course).distinct().count()
    return jsonify({'students': student_count, 'attendance': attendance_count, 'streams': stream_count})

# ==================== STUDENT ROUTES ====================
@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    session.pop('admin_logged_in', None)
    if request.method == 'GET':
        q, a = generate_captcha()
        session['captcha_answer'] = a; session['captcha_question'] = q
    else: q = session.get('captcha_question', '')
    if request.method == 'POST':
        if int(request.form.get('captcha',0)) != session.get('captcha_answer',0):
            flash('Wrong CAPTCHA!','error')
            q, a = generate_captcha(); session['captcha_answer']=a; session['captcha_question']=q
            return render_template('student_register.html', captcha_q=q, security_questions=SECURITY_QUESTIONS, courses=COURSES, years=YEARS)
        r = request.form.get('reg_no'); c = request.form.get('course')
        if not r: r = get_next_regno(c)
        if Student.query.filter((Student.reg_no==r)|(Student.email==request.form['email'])).first():
            flash('Reg no or email exists!','error')
            return redirect(url_for('student_register'))
        s = Student(reg_no=r, email=request.form['email'], name=request.form['name'],
                   mobile=request.form['mobile'], course=c,
                   year=request.form.get('year', '1st'),
                   security_question=request.form['security_question'],
                   security_answer=request.form['security_answer'].lower().strip(),
                   photo=request.form.get('photo', ''))
        s.set_password(request.form['password'])
        db.session.add(s); db.session.commit()
        flash(f'Registered! Reg No: {r}','success')
        return redirect(url_for('student_login'))
    return render_template('student_register.html', captcha_q=q, security_questions=SECURITY_QUESTIONS, courses=COURSES, years=YEARS)

@app.route('/api/check-regno')
def check_regno():
    r = request.args.get('reg_no','')
    if not r: return jsonify({'available':False})
    ex = Student.query.filter_by(reg_no=r).first()
    return jsonify({'available':not ex, 'message':f'Taken by {ex.name}' if ex else 'Available'})

@app.route('/api/suggest-regno/<course>')
def suggest_regno(course):
    return jsonify({'reg_no': get_next_regno(course)})

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    session.pop('admin_logged_in', None)
    if request.method == 'GET':
        q, a = generate_captcha()
        session['login_captcha_answer'] = a; session['login_captcha_question'] = q
    else: q = session.get('login_captcha_question', '')
    if request.method == 'POST':
        if int(request.form.get('captcha',0)) != session.get('login_captcha_answer',0):
            flash('Wrong CAPTCHA!','error')
            q, a = generate_captcha(); session['login_captcha_answer']=a; session['login_captcha_question']=q
            return render_template('student_login.html', captcha_q=q)
        s = Student.query.filter_by(reg_no=request.form['reg_no']).first()
        if s and s.check_password(request.form['password']):
            session['student_id']=s.id; session['student_name']=s.name
            flash(f'Welcome {s.name}!','success')
            return redirect(url_for('student_dashboard'))
        flash('Invalid credentials!','error')
    return render_template('student_login.html', captcha_q=q)

@app.route('/student/forgot-regno', methods=['GET', 'POST'])
def forgot_regno():
    if request.method == 'POST':
        s = Student.query.filter_by(email=request.form['email']).first()
        if s and s.security_answer == request.form.get('security_answer','').lower().strip():
            flash(f'Reg No: {s.reg_no}','success')
        else: flash('Incorrect!','error')
        return redirect(url_for('student_login'))
    return render_template('forgot_regno.html')

@app.route('/student/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        s = Student.query.filter_by(reg_no=request.form['reg_no']).first()
        if s and s.security_answer == request.form.get('security_answer','').lower().strip():
            s.set_password(request.form['new_password'])
            db.session.commit()
            flash('Password reset!','success')
        else: flash('Incorrect!','error')
        return redirect(url_for('student_login'))
    return render_template('forgot_password.html')

@app.route('/student/logout')
def student_logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/student/dashboard')
def student_dashboard():
    session.pop('admin_logged_in', None)
    if 'student_id' not in session: return redirect(url_for('student_login'))
    s = Student.query.get(session['student_id'])
    st = get_attendance_with_working_days(s.id)
    setts = get_app_settings()
    lbs=[]; pr=[]; ab=[]
    for i in range(6,-1,-1):
        d = get_ist_time().date()-timedelta(days=i)
        lbs.append(d.strftime('%a'))
        ds = datetime.combine(d, datetime.min.time()); de = datetime.combine(d, datetime.max.time())
        pr.append(Attendance.query.filter_by(student_id=s.id, status='Present').filter(Attendance.timestamp>=ds, Attendance.timestamp<=de).count())
        ab.append(Attendance.query.filter_by(student_id=s.id, status='Absent').filter(Attendance.timestamp>=ds, Attendance.timestamp<=de).count())
    return render_template('student_dashboard.html', student=s, stats=st, settings=setts,
                         daily_labels=lbs, daily_present=pr, daily_absent=ab)

@app.route('/student/register-face', methods=['GET', 'POST'])
def register_face():
    if 'student_id' not in session: return redirect(url_for('student_login'))
    if request.method == 'POST' and request.form.get('descriptor'):
        s = Student.query.get(session['student_id'])
        s.face_descriptor = request.form['descriptor']
        db.session.commit()
        flash('Face registered!','success')
        return redirect(url_for('student_dashboard'))
    return render_template('register_face.html')

@app.route('/student/mark-attendance')
def mark_attendance_page():
    session.pop('admin_logged_in', None)
    if 'student_id' not in session:
        return redirect(url_for('student_login'))
    
    today = get_ist_time().date()
    
    # Holiday check
    holiday = Holiday.query.filter_by(date=today).first()
    if holiday:
        flash(f'🎉 Today is {holiday.name} — Holiday! Attendance not allowed.', 'info')
        return redirect(url_for('student_dashboard'))
    
    # Already marked today check
    already_marked = Attendance.query.filter(
        Attendance.student_id == session['student_id'],
        Attendance.timestamp >= datetime.combine(today, datetime.min.time()),
        Attendance.timestamp <= datetime.combine(today, datetime.max.time())
    ).first()
    
    if already_marked:
        time_str = already_marked.timestamp.strftime('%I:%M %p')
        status_text = already_marked.status
        flash(f'✅ You have already marked {status_text} today at {time_str}. Please try again tomorrow!', 'success')
        return redirect(url_for('student_dashboard'))
    
    return render_template('mark_attendance.html')

@app.route('/student/process-attendance', methods=['POST'])
def process_attendance():
    session.pop('admin_logged_in', None)
    if 'student_id' not in session: return jsonify({'success':False,'message':'Not logged in'})
    
    # Check if already marked today
    today = get_ist_time().date()
    already_marked = Attendance.query.filter(
        Attendance.student_id == session['student_id'],
        Attendance.timestamp >= datetime.combine(today, datetime.min.time()),
        Attendance.timestamp <= datetime.combine(today, datetime.max.time())
    ).first()
    
    if already_marked:
        time_str = already_marked.timestamp.strftime('%I:%M %p')
        status_text = already_marked.status
        return jsonify({
            'success': False,
            'message': f'You have already marked {status_text} today at {time_str}. Please try again tomorrow!'
        })
    
    d = request.json
    if not d.get('descriptor'): return jsonify({'success':False,'message':'No face data'})
    students = Student.query.filter(Student.face_descriptor!=None).all()
    if not students: return jsonify({'success':False,'message':'No faces registered'})
    try:
        inp = np.array(d['descriptor'])
        best = None; md = 0.6
        for s in students:
            dist = np.linalg.norm(inp - np.array(json.loads(s.face_descriptor)))
            if dist < md: md = dist; best = s
        if best and best.id == session['student_id']:
            loc = get_location_name(d.get('latitude'), d.get('longitude'))
            current_time = get_ist_time().strftime('%I:%M %p')
            location_with_time = f"{loc} at {current_time}" if loc != "Location not available" else loc
            a = Attendance(student_id=best.id, latitude=d.get('latitude'), longitude=d.get('longitude'),
                          location_name=location_with_time, status=d.get('status','Present'))
            db.session.add(a); db.session.commit()
            return jsonify({'success':True,'message':f'Marked {d.get("status","Present")} for {best.name} at {location_with_time}'})
        return jsonify({'success':False,'message':'Face mismatch'})
    except Exception as e:
        return jsonify({'success':False,'message':str(e)})

@app.route('/student/attendance-history')
def attendance_history():
    if 'student_id' not in session: return redirect(url_for('student_login'))
    records = Attendance.query.filter_by(student_id=session['student_id']).order_by(Attendance.timestamp.desc()).all()
    st = get_attendance_with_working_days(session['student_id'])
    return render_template('attendance_history.html', records=records, stats=st)

@app.route('/admin/view-database')
def view_database():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    
    dept = get_admin_department()
    
    course_filter = request.args.get('course', '')
    year_filter = request.args.get('year', '')
    
    # If department admin, force their course
    if dept != 'ALL':
        course_filter = dept
    
    query = Student.query
    if course_filter:
        query = query.filter_by(course=course_filter)
    if year_filter:
        query = query.filter_by(year=year_filter)
    
    students = query.order_by(Student.course, Student.year, Student.reg_no).all()
    
    student_data = []
    for s in students:
        stats = get_attendance_with_working_days(s.id)
        last_att = Attendance.query.filter_by(student_id=s.id).order_by(Attendance.timestamp.desc()).first()
        student_data.append({
            'student': s, 'stats': stats,
            'last_location': last_att.location_name if last_att else 'N/A',
            'last_date': last_att.timestamp.strftime('%Y-%m-%d %H:%M') if last_att else 'N/A'
        })
    
    # Show only relevant courses for department admin
    available_courses = COURSES if dept == 'ALL' else [dept]
    
    return render_template('view_database.html', student_data=student_data,
                         courses=available_courses, years=YEARS,
                         selected_course=course_filter, selected_year=year_filter,
                         admin_dept=dept)

# ==================== INIT ====================
@app.before_request
def create_tables():
    db.create_all()
    if not hasattr(app, '_admins_initialized'):
        with app.app_context(): init_admins()
        app._admins_initialized = True

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)