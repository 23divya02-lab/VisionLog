import sqlite3
import sys

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Parse arguments
filter_stream = None
filter_year = None

for arg in sys.argv[1:]:
    arg_upper = arg.upper()
    if arg_upper in ['1ST', '2ND', '3RD']:
        filter_year = arg_upper.lower()
    else:
        filter_stream = arg_upper

# Get settings
cursor.execute("SELECT total_working_days, minimum_percent FROM app_settings LIMIT 1")
settings = cursor.fetchone()
if settings:
    total_working = settings[0]
    minimum_pct = settings[1]
else:
    total_working = 90
    minimum_pct = 75

# Get courses
if filter_stream:
    cursor.execute("SELECT DISTINCT course FROM student WHERE course = ? ORDER BY course", (filter_stream,))
else:
    cursor.execute("SELECT DISTINCT course FROM student ORDER BY course")
courses = cursor.fetchall()

if not courses:
    print(f"\n⚠️  No students found for stream: {filter_stream}")
    conn.close()
    exit()

# Build report title
title_parts = []
if filter_stream: title_parts.append(filter_stream)
if filter_year: title_parts.append(f"{filter_year} Year")
title_str = " - ".join(title_parts) if title_parts else "All Students"

print("\n" + "="*120)
print(f"  VISIONLOG - ATTENDANCE REPORT - {title_str} (Working Days: {total_working} | Min Required: {minimum_pct}%)")
print("="*120)

grand_total = 0
grand_green = 0
grand_yellow = 0
grand_red = 0

for (course,) in courses:
    # Build query with optional year filter
    if filter_year:
        cursor.execute("""
            SELECT s.reg_no, s.name, s.course, s.year,
                   SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) as present
            FROM student s
            LEFT JOIN attendance a ON s.id = a.student_id
            WHERE s.course = ? AND s.year = ?
            GROUP BY s.id
            ORDER BY s.reg_no
        """, (course, filter_year))
    else:
        cursor.execute("""
            SELECT s.reg_no, s.name, s.course, s.year,
                   SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) as present
            FROM student s
            LEFT JOIN attendance a ON s.id = a.student_id
            WHERE s.course = ?
            GROUP BY s.id
            ORDER BY s.year, s.reg_no
        """, (course,))
    
    students = cursor.fetchall()
    if not students: continue
    
    course_green = []; course_yellow = []; course_red = []
    
    for student in students:
        reg_no, name, course, year, present = student
        present = present or 0
        percentage = round((present / total_working * 100), 2) if total_working > 0 else 0
        if percentage >= minimum_pct: zone = 'green'
        elif percentage >= 60: zone = 'yellow'
        else: zone = 'red'
        shortage = max(0, int(total_working * minimum_pct / 100) - present)
        
        cursor.execute("""
            SELECT location_name FROM attendance 
            WHERE student_id = (SELECT id FROM student WHERE reg_no = ?)
            ORDER BY timestamp DESC LIMIT 1
        """, (reg_no,))
        last_att = cursor.fetchone()
        location = last_att[0] if last_att and last_att[0] else 'N/A'
        
        student_data = {
            'reg_no': reg_no, 'name': name, 'course': course, 'year': year,
            'present': present, 'total': total_working, 'percentage': percentage,
            'zone': zone, 'shortage': shortage, 'location': location
        }
        
        if zone == 'green': course_green.append(student_data)
        elif zone == 'yellow': course_yellow.append(student_data)
        else: course_red.append(student_data)
    
    year_info = f" | Year: {filter_year}" if filter_year else ""
    print(f"\n{'='*120}")
    print(f"  STREAM: {course}{year_info} | Total: {len(students)} | 🟢 Safe: {len(course_green)} | 🟡 Warning: {len(course_yellow)} | 🔴 Critical: {len(course_red)}")
    print(f"{'='*120}")
    
    if course_green:
        print(f"\n  🟢 SAFE ZONE (Attendance >= {minimum_pct}%)")
        print(f"  {'-'*110}")
        print(f"  {'Reg No':<12} | {'Name':<22} | {'Year':<6} | {'Present':<10} | {'%':<8} | {'Last Location':<40}")
        print(f"  {'-'*110}")
        for s in course_green:
            print(f"  {s['reg_no']:<12} | {s['name']:<22} | {s['year']:<6} | {s['present']}/{s['total']:<7} | {s['percentage']:<7.1f}% | {s['location']:<40}")
    
    if course_yellow:
        print(f"\n  🟡 WARNING ZONE (60% - {minimum_pct-0.1}%)")
        print(f"  {'-'*110}")
        print(f"  {'Reg No':<12} | {'Name':<22} | {'Year':<6} | {'Present':<10} | {'%':<8} | {'Shortage':<8} | {'Last Location':<40}")
        print(f"  {'-'*110}")
        for s in course_yellow:
            print(f"  {s['reg_no']:<12} | {s['name']:<22} | {s['year']:<6} | {s['present']}/{s['total']:<7} | {s['percentage']:<7.1f}% | {s['shortage']} days{'':<2} | {s['location']:<40}")
    
    if course_red:
        print(f"\n  🔴 CRITICAL ZONE (< 60%)")
        print(f"  {'-'*110}")
        print(f"  {'Reg No':<12} | {'Name':<22} | {'Year':<6} | {'Present':<10} | {'%':<8} | {'Shortage':<8} | {'Last Location':<40}")
        print(f"  {'-'*110}")
        for s in course_red:
            print(f"  {s['reg_no']:<12} | {s['name']:<22} | {s['year']:<6} | {s['present']}/{s['total']:<7} | {s['percentage']:<7.1f}% | {s['shortage']} days{'':<2} | {s['location']:<40}")
    
    grand_total += len(students)
    grand_green += len(course_green)
    grand_yellow += len(course_yellow)
    grand_red += len(course_red)

print(f"\n{'='*120}")
print(f"  GRAND TOTAL: {grand_total} Students | 🟢 Safe: {grand_green} | 🟡 Warning: {grand_yellow} | 🔴 Critical: {grand_red}")
print(f"{'='*120}\n")

conn.close()