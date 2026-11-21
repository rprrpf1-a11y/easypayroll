import os
import sqlite3
import csv
import io
import re
import urllib.parse
from datetime import datetime, date
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, Response, send_file, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

def get_secret_key():
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            return f.read().strip()
    import secrets
    new_key = secrets.token_hex(32)
    try:
        with open(key_file, "w") as f:
            f.write(new_key)
    except Exception:
        pass
    return new_key

app.secret_key = get_secret_key()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payroll.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        company_name TEXT DEFAULT 'My Company Ltd',
        currency TEXT DEFAULT '₹',
        default_tax_rate REAL DEFAULT 10.0,
        address TEXT DEFAULT '123 Business Way, Suite 100',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        employee_code TEXT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        department TEXT,
        designation TEXT,
        salary_type TEXT DEFAULT 'Monthly',
        base_salary REAL NOT NULL DEFAULT 0.0,
        bank_name TEXT,
        bank_account TEXT,
        tax_id TEXT,
        status TEXT DEFAULT 'Active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payroll_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        pay_period_start TEXT,
        pay_period_end TEXT,
        pay_date TEXT,
        total_gross REAL DEFAULT 0.0,
        total_deductions REAL DEFAULT 0.0,
        total_net REAL DEFAULT 0.0,
        employee_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Completed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payslips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payroll_run_id INTEGER NOT NULL,
        employee_id INTEGER NOT NULL,
        base_salary REAL DEFAULT 0.0,
        bonus REAL DEFAULT 0.0,
        overtime_pay REAL DEFAULT 0.0,
        allowances REAL DEFAULT 0.0,
        tax_deduction REAL DEFAULT 0.0,
        insurance_deduction REAL DEFAULT 0.0,
        other_deductions REAL DEFAULT 0.0,
        da_amount REAL DEFAULT 0.0,
        hra_amount REAL DEFAULT 0.0,
        epf_deduction REAL DEFAULT 0.0,
        eps_deduction REAL DEFAULT 0.0,
        house_rent_deduction REAL DEFAULT 0.0,
        gross_pay REAL DEFAULT 0.0,
        total_deductions REAL DEFAULT 0.0,
        net_pay REAL DEFAULT 0.0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (payroll_run_id) REFERENCES payroll_runs(id) ON DELETE CASCADE,
        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        employee_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Present',
        clock_in TEXT DEFAULT '09:00',
        clock_out TEXT DEFAULT '17:00',
        working_hours REAL DEFAULT 8.0,
        overtime_hours REAL DEFAULT 0.0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
        UNIQUE(employee_id, date)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        employee_id INTEGER NOT NULL,
        leave_type TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        days_count REAL DEFAULT 1.0,
        status TEXT DEFAULT 'Approved',
        reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
    );
    """)

    # Auto-migrations for DA, House Rent, EPF, EPS
    new_user_cols = [
        ("default_da_rate", "REAL DEFAULT 0.0"),
        ("default_hra_rate", "REAL DEFAULT 0.0"),
        ("default_epf_rate", "REAL DEFAULT 12.0"),
        ("default_eps_rate", "REAL DEFAULT 0.0"),
        ("default_house_rent", "REAL DEFAULT 0.0"),
        ("logo_url", "TEXT DEFAULT ''")
    ]
    for col_name, col_type in new_user_cols:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
        except sqlite3.OperationalError:
            pass

    new_payslip_cols = [
        ("da_amount", "REAL DEFAULT 0.0"),
        ("hra_amount", "REAL DEFAULT 0.0"),
        ("epf_deduction", "REAL DEFAULT 0.0"),
        ("eps_deduction", "REAL DEFAULT 0.0"),
        ("house_rent_deduction", "REAL DEFAULT 0.0")
    ]
    for col_name, col_type in new_payslip_cols:
        try:
            cursor.execute(f"ALTER TABLE payslips ADD COLUMN {col_name} {col_type};")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


init_db()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in or sign up to access your payroll dashboard.", "info")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    if "user_id" not in session:
        return None
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return user


@app.context_processor
def inject_user():
    return dict(current_user=get_current_user())


# --- Authentication Routes ---

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        company_name = request.form.get("company_name", "").strip() or "My Company"
        currency = request.form.get("currency", "₹")

        if not name or not email or not password:
            flash("Name, Email, and Password are required.", "danger")
            return render_template("signup.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("signup.html")

        conn = get_db_connection()
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            flash("An account with that email already exists. Please log in.", "warning")
            return redirect(url_for("login"))

        pwd_hash = generate_password_hash(password)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, company_name, currency)
            VALUES (?, ?, ?, ?, ?)
        """, (name, email, pwd_hash, company_name, currency))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        session["user_id"] = user_id
        session["user_name"] = name
        flash(f"Welcome to EasyPayroll, {name}! Your stress-free payroll is ready.", "success")
        return redirect(url_for("dashboard"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password. Please try again.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out safely.", "info")
    return redirect(url_for("login"))


# --- Dashboard ---

@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    conn = get_db_connection()

    # Employee counts
    active_emp_count = conn.execute(
        "SELECT COUNT(*) FROM employees WHERE user_id = ? AND status = 'Active'",
        (user["id"],)
    ).fetchone()[0]

    total_emp_count = conn.execute(
        "SELECT COUNT(*) FROM employees WHERE user_id = ?",
        (user["id"],)
    ).fetchone()[0]

    # Payroll sums
    latest_run = conn.execute(
        "SELECT * FROM payroll_runs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user["id"],)
    ).fetchone()

    total_payout_all_time = conn.execute(
        "SELECT COALESCE(SUM(total_net), 0) FROM payroll_runs WHERE user_id = ?",
        (user["id"],)
    ).fetchone()[0]

    total_payroll_runs = conn.execute(
        "SELECT COUNT(*) FROM payroll_runs WHERE user_id = ?",
        (user["id"],)
    ).fetchone()[0]

    recent_runs = conn.execute(
        "SELECT * FROM payroll_runs WHERE user_id = ? ORDER BY id DESC LIMIT 5",
        (user["id"],)
    ).fetchall()

    recent_employees = conn.execute(
        "SELECT * FROM employees WHERE user_id = ? ORDER BY id DESC LIMIT 5",
        (user["id"],)
    ).fetchall()

    today_str = date.today().strftime("%Y-%m-%d")
    today_present = conn.execute(
        "SELECT COUNT(*) FROM attendance WHERE user_id = ? AND date = ? AND status = 'Present'",
        (user["id"], today_str)
    ).fetchone()[0]
    today_absent = conn.execute(
        "SELECT COUNT(*) FROM attendance WHERE user_id = ? AND date = ? AND status = 'Absent'",
        (user["id"], today_str)
    ).fetchone()[0]
    today_on_leave = conn.execute(
        "SELECT COUNT(*) FROM attendance WHERE user_id = ? AND date = ? AND status = 'On Leave'",
        (user["id"], today_str)
    ).fetchone()[0]
    pending_leaves = conn.execute(
        "SELECT COUNT(*) FROM leave_requests WHERE user_id = ? AND status = 'Pending'",
        (user["id"],)
    ).fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        active_emp_count=active_emp_count,
        total_emp_count=total_emp_count,
        latest_run=latest_run,
        total_payout_all_time=total_payout_all_time,
        total_payroll_runs=total_payroll_runs,
        recent_runs=recent_runs,
        recent_employees=recent_employees,
        today_present=today_present,
        today_absent=today_absent,
        today_on_leave=today_on_leave,
        pending_leaves=pending_leaves,
        today_str=today_str
    )


# --- Employees Management ---

@app.route("/employees")
@login_required
def employees():
    user = get_current_user()
    search = request.args.get("search", "").strip()
    dept = request.args.get("department", "").strip()
    status = request.args.get("status", "").strip()

    conn = get_db_connection()
    query = "SELECT * FROM employees WHERE user_id = ?"
    params = [user["id"]]

    if search:
        query += " AND (first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR employee_code LIKE ?)"
        like_search = f"%{search}%"
        params.extend([like_search, like_search, like_search, like_search])

    if dept:
        query += " AND department = ?"
        params.append(dept)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY first_name ASC, last_name ASC"
    employees_rows = conn.execute(query, params).fetchall()
    employees_list = [dict(row) for row in employees_rows]

    departments = conn.execute(
        "SELECT DISTINCT department FROM employees WHERE user_id = ? AND department IS NOT NULL AND department != ''",
        (user["id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "employees.html",
        employees=employees_list,
        departments=[d[0] for d in departments],
        search=search,
        selected_dept=dept,
        selected_status=status
    )


@app.route("/employees/add", methods=["POST"])
@login_required
def add_employee():
    user = get_current_user()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    department = request.form.get("department", "").strip() or "General"
    designation = request.form.get("designation", "").strip() or "Team Member"
    base_salary = float(request.form.get("base_salary", 0) or 0)
    bank_name = request.form.get("bank_name", "").strip()
    bank_account = request.form.get("bank_account", "").strip()
    tax_id = request.form.get("tax_id", "").strip()
    status = request.form.get("status", "Active")

    if not first_name or not last_name:
        flash("First name and Last name are required.", "danger")
        return redirect(url_for("employees"))

    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM employees WHERE user_id = ?", (user["id"],)).fetchone()[0]
    employee_code = f"EMP-{(count + 1):03d}"

    conn.execute("""
        INSERT INTO employees (
            user_id, employee_code, first_name, last_name, email, phone,
            department, designation, base_salary, bank_name, bank_account, tax_id, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user["id"], employee_code, first_name, last_name, email, phone,
        department, designation, base_salary, bank_name, bank_account, tax_id, status
    ))
    conn.commit()
    conn.close()

    flash(f"Employee {first_name} {last_name} ({employee_code}) added successfully!", "success")
    return redirect(url_for("employees"))


@app.route("/employees/edit/<int:emp_id>", methods=["POST"])
@login_required
def edit_employee(emp_id):
    user = get_current_user()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    department = request.form.get("department", "").strip()
    designation = request.form.get("designation", "").strip()
    base_salary = float(request.form.get("base_salary", 0) or 0)
    bank_name = request.form.get("bank_name", "").strip()
    bank_account = request.form.get("bank_account", "").strip()
    tax_id = request.form.get("tax_id", "").strip()
    status = request.form.get("status", "Active")

    conn = get_db_connection()
    conn.execute("""
        UPDATE employees SET
            first_name = ?, last_name = ?, email = ?, phone = ?,
            department = ?, designation = ?, base_salary = ?,
            bank_name = ?, bank_account = ?, tax_id = ?, status = ?
        WHERE id = ? AND user_id = ?
    """, (
        first_name, last_name, email, phone,
        department, designation, base_salary,
        bank_name, bank_account, tax_id, status,
        emp_id, user["id"]
    ))
    conn.commit()
    conn.close()

    flash(f"Employee {first_name} {last_name} details updated.", "success")
    return redirect(url_for("employees"))


@app.route("/employees/delete/<int:emp_id>", methods=["POST"])
@login_required
def delete_employee(emp_id):
    user = get_current_user()
    conn = get_db_connection()
    conn.execute("DELETE FROM employees WHERE id = ? AND user_id = ?", (emp_id, user["id"]))
    conn.commit()
    conn.close()
    flash("Employee removed successfully.", "info")
    return redirect(url_for("employees"))


@app.route("/employees/load-demo", methods=["POST"])
@login_required
def load_demo_data():
    """Populates 5 sample employees and 1 past payroll run so new visitors can try the app right away!"""
    user = get_current_user()
    conn = get_db_connection()

    sample_employees = [
        ("Sarah", "Jenkins", "sarah.j@example.com", "+1 555-0142", "Engineering", "Lead Fullstack Engineer", 8200.0, "Chase Bank", "****4589", "TAX-8841"),
        ("Marcus", "Chen", "marcus.c@example.com", "+1 555-0187", "Design", "Senior Product Designer", 6500.0, "Wells Fargo", "****1123", "TAX-9921"),
        ("Elena", "Rostova", "elena.r@example.com", "+1 555-0199", "Marketing", "Growth Marketing Specialist", 5400.0, "Bank of America", "****6742", "TAX-3312"),
        ("David", "Kalu", "david.k@example.com", "+1 555-0211", "Sales", "Enterprise Account Exec", 6000.0, "Citibank", "****8831", "TAX-5524"),
        ("Aisha", "Khan", "aisha.k@example.com", "+1 555-0245", "Human Resources", "People Operations Manager", 5800.0, "Barclays", "****2290", "TAX-1234"),
    ]

    emp_ids = []
    for idx, emp in enumerate(sample_employees, 1):
        emp_code = f"EMP-{idx:03d}"
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO employees (
                user_id, employee_code, first_name, last_name, email, phone,
                department, designation, base_salary, bank_name, bank_account, tax_id, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active')
        """, (
            user["id"], emp_code, emp[0], emp[1], emp[2], emp[3],
            emp[4], emp[5], emp[6], emp[7], emp[8], emp[9]
        ))
        emp_ids.append(cursor.lastrowid)

    # Generate 14 days of realistic sample attendance logs for current month
    today = date.today()
    for day_offset in range(1, 15):
        try:
            day_date = today.replace(day=day_offset).strftime("%Y-%m-%d")
        except ValueError:
            continue

        # Add attendance for each employee on this date
        for i, emp_id in enumerate(emp_ids):
            # Realistic variations
            if i == 0:  # Sarah (hard worker with OT)
                ot = 2.0 if day_offset in [3, 8] else 0.0
                st = "Present"
            elif i == 1:  # Marcus
                ot = 1.5 if day_offset == 5 else 0.0
                st = "Present"
            elif i == 2:  # Elena (took 1 half day, 1 leave)
                ot = 0.0
                st = "On Leave" if day_offset == 6 else ("Half Day" if day_offset == 11 else "Present")
            elif i == 3:  # David (1 absent)
                ot = 0.0
                st = "Absent" if day_offset == 9 else "Present"
            else:  # Aisha
                ot = 0.0
                st = "Present"

            hours = 4.0 if st == "Half Day" else (0.0 if st in ["Absent", "On Leave"] else 8.0)
            conn.execute("""
                INSERT OR IGNORE INTO attendance (
                    user_id, employee_id, date, status, clock_in, clock_out, working_hours, overtime_hours, notes
                ) VALUES (?, ?, ?, ?, '09:00', '17:00', ?, ?, '')
            """, (user["id"], emp_id, day_date, st, hours, ot))

    # Add 2 sample leave records
    if len(emp_ids) >= 4:
        conn.execute("""
            INSERT INTO leave_requests (user_id, employee_id, leave_type, start_date, end_date, days_count, status, reason)
            VALUES (?, ?, 'Sick Leave', ?, ?, 1.0, 'Approved', 'Seasonal flu recovery')
        """, (user["id"], emp_ids[2], today.strftime("%Y-%m-06"), today.strftime("%Y-%m-06")))

        conn.execute("""
            INSERT INTO leave_requests (user_id, employee_id, leave_type, start_date, end_date, days_count, status, reason)
            VALUES (?, ?, 'Annual Leave', ?, ?, 2.0, 'Pending', 'Family vacation')
        """, (user["id"], emp_ids[3], today.strftime("%Y-%m-20"), today.strftime("%Y-%m-21")))

    conn.commit()
    conn.close()
    flash("5 sample employees, attendance history, and leaves loaded! Ready for 1-click payroll.", "success")
    return redirect(url_for("employees"))


# --- Attendance Tracking Routes ---

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    user = get_current_user()
    conn = get_db_connection()

    selected_date = request.args.get("date", date.today().strftime("%Y-%m-%d"))

    if request.method == "POST":
        emp_ids = request.form.getlist("employee_ids")
        for emp_id in emp_ids:
            status = request.form.get(f"status_{emp_id}", "Present")
            clock_in = request.form.get(f"clock_in_{emp_id}", "09:00")
            clock_out = request.form.get(f"clock_out_{emp_id}", "17:00")
            ot_hours = float(request.form.get(f"ot_{emp_id}", 0) or 0)
            notes = request.form.get(f"notes_{emp_id}", "").strip()

            working_hours = 8.0
            if status == "Half Day":
                working_hours = 4.0
            elif status in ["Absent", "On Leave"]:
                working_hours = 0.0

            conn.execute("""
                INSERT INTO attendance (user_id, employee_id, date, status, clock_in, clock_out, working_hours, overtime_hours, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(employee_id, date) DO UPDATE SET
                    status = excluded.status,
                    clock_in = excluded.clock_in,
                    clock_out = excluded.clock_out,
                    working_hours = excluded.working_hours,
                    overtime_hours = excluded.overtime_hours,
                    notes = excluded.notes
            """, (user["id"], emp_id, selected_date, status, clock_in, clock_out, working_hours, ot_hours, notes))

        conn.commit()
        conn.close()
        flash(f"Attendance for {selected_date} saved successfully!", "success")
        return redirect(url_for("attendance", date=selected_date))

    # GET request
    active_employees = conn.execute("""
        SELECT * FROM employees 
        WHERE user_id = ? AND status = 'Active' 
        ORDER BY first_name ASC
    """, (user["id"],)).fetchall()

    existing_records = conn.execute("""
        SELECT * FROM attendance 
        WHERE user_id = ? AND date = ?
    """, (user["id"], selected_date)).fetchall()

    records_by_emp = {r["employee_id"]: dict(r) for r in existing_records}

    # Summary counts for the selected date
    present_cnt = sum(1 for r in records_by_emp.values() if r["status"] == "Present")
    absent_cnt = sum(1 for r in records_by_emp.values() if r["status"] == "Absent")
    half_cnt = sum(1 for r in records_by_emp.values() if r["status"] == "Half Day")
    leave_cnt = sum(1 for r in records_by_emp.values() if r["status"] == "On Leave")

    conn.close()

    return render_template(
        "attendance.html",
        employees=active_employees,
        records_by_emp=records_by_emp,
        selected_date=selected_date,
        present_cnt=present_cnt,
        absent_cnt=absent_cnt,
        half_cnt=half_cnt,
        leave_cnt=leave_cnt
    )


@app.route("/attendance/quick-all-present", methods=["POST"])
@login_required
def attendance_quick_all_present():
    user = get_current_user()
    selected_date = request.form.get("date", date.today().strftime("%Y-%m-%d"))

    conn = get_db_connection()
    active_employees = conn.execute(
        "SELECT id FROM employees WHERE user_id = ? AND status = 'Active'",
        (user["id"],)
    ).fetchall()

    for emp in active_employees:
        conn.execute("""
            INSERT INTO attendance (user_id, employee_id, date, status, clock_in, clock_out, working_hours, overtime_hours)
            VALUES (?, ?, ?, 'Present', '09:00', '17:00', 8.0, 0.0)
            ON CONFLICT(employee_id, date) DO UPDATE SET
                status = 'Present',
                clock_in = '09:00',
                clock_out = '17:00',
                working_hours = 8.0
        """, (user["id"], emp["id"], selected_date))

    conn.commit()
    conn.close()
    flash(f"All active employees marked 'Present' for {selected_date} in 1 click!", "success")
    return redirect(url_for("attendance", date=selected_date))


def build_whatsapp_attendance_url(emp, stats, selected_month, user, base_url=""):
    phone = emp.get("phone") or ""
    clean_phone = re.sub(r"[^\d]", "", str(phone))

    report_link = f"{base_url}/attendance/report/{emp['id']}?month={selected_month}"

    msg = (
        f"📋 *OFFICIAL ATTENDANCE STATEMENT*\n"
        f"🏢 *Company:* {user['company_name']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Employee:* {emp['first_name']} {emp['last_name']} ({emp['employee_code']})\n"
        f"💼 *Department:* {emp.get('department') or 'General'} • {emp.get('designation') or 'Staff'}\n"
        f"🗓️ *Month / Period:* {selected_month}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *MONTHLY ATTENDANCE SUMMARY:*\n"
        f"• Total Working Days: {stats['total_logged']}\n"
        f"• Present Days: {stats['present_days']} ✅\n"
        f"• Half Days: {stats['half_days']} 🌓\n"
        f"• Absent Days: {stats['absent_days']} ❌\n"
        f"• Approved Leaves: {stats['leave_days']} 🌴\n"
        f"• Overtime: {stats['total_ot']} hrs ⏱️\n"
        f"• Attendance Score: {stats['rate']}%\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📄 *View & Print Full Attendance PDF Statement:*\n"
        f"{report_link}\n\n"
        f"_Generated by EasyPayroll Attendance Tracking._"
    )

    encoded_text = urllib.parse.quote(msg)
    if clean_phone:
        return f"https://wa.me/{clean_phone}?text={encoded_text}"
    else:
        return f"https://api.whatsapp.com/send?text={encoded_text}"


@app.route("/attendance/summary")
@login_required
def attendance_summary():
    user = get_current_user()
    conn = get_db_connection()

    selected_month = request.args.get("month", date.today().strftime("%Y-%m"))
    month_pattern = f"{selected_month}%"

    active_employees = conn.execute("""
        SELECT * FROM employees 
        WHERE user_id = ? AND status = 'Active' 
        ORDER BY first_name ASC
    """, (user["id"],)).fetchall()

    base_url = request.host_url.rstrip("/")
    summary_list = []
    for emp in active_employees:
        stats = conn.execute("""
            SELECT 
                COUNT(*) as total_logged,
                COUNT(CASE WHEN status = 'Present' THEN 1 END) as present_days,
                COUNT(CASE WHEN status = 'Half Day' THEN 1 END) as half_days,
                COUNT(CASE WHEN status = 'Absent' THEN 1 END) as absent_days,
                COUNT(CASE WHEN status = 'On Leave' THEN 1 END) as leave_days,
                COUNT(CASE WHEN status = 'Late' THEN 1 END) as late_days,
                COALESCE(SUM(overtime_hours), 0.0) as total_ot
            FROM attendance
            WHERE employee_id = ? AND date LIKE ?
        """, (emp["id"], month_pattern)).fetchone()

        total = stats["total_logged"]
        rate = round(((stats["present_days"] + stats["half_days"] * 0.5) / total * 100), 1) if total > 0 else 100.0

        stats_dict = {
            "present_days": stats["present_days"],
            "half_days": stats["half_days"],
            "absent_days": stats["absent_days"],
            "leave_days": stats["leave_days"],
            "late_days": stats["late_days"],
            "total_ot": stats["total_ot"],
            "total_logged": total,
            "rate": rate
        }

        whatsapp_url = build_whatsapp_attendance_url(dict(emp), stats_dict, selected_month, user, base_url)
        report_url = url_for("attendance_employee_report", employee_id=emp["id"], month=selected_month)

        summary_list.append({
            "employee": emp,
            "present_days": stats["present_days"],
            "half_days": stats["half_days"],
            "absent_days": stats["absent_days"],
            "leave_days": stats["leave_days"],
            "late_days": stats["late_days"],
            "total_ot": stats["total_ot"],
            "total_logged": total,
            "rate": rate,
            "whatsapp_url": whatsapp_url,
            "report_url": report_url
        })

    conn.close()
    return render_template("attendance_summary.html", summary_list=summary_list, selected_month=selected_month)


@app.route("/attendance/report/<int:employee_id>")
@login_required
def attendance_employee_report(employee_id):
    user = get_current_user()
    conn = get_db_connection()

    emp = conn.execute("SELECT * FROM employees WHERE id = ? AND user_id = ?", (employee_id, user["id"])).fetchone()
    if not emp:
        conn.close()
        flash("Employee not found.", "warning")
        return redirect(url_for("attendance_summary"))

    selected_month = request.args.get("month", date.today().strftime("%Y-%m"))
    month_pattern = f"{selected_month}%"

    stats = conn.execute("""
        SELECT 
            COUNT(*) as total_logged,
            COUNT(CASE WHEN status = 'Present' THEN 1 END) as present_days,
            COUNT(CASE WHEN status = 'Half Day' THEN 1 END) as half_days,
            COUNT(CASE WHEN status = 'Absent' THEN 1 END) as absent_days,
            COUNT(CASE WHEN status = 'On Leave' THEN 1 END) as leave_days,
            COUNT(CASE WHEN status = 'Late' THEN 1 END) as late_days,
            COALESCE(SUM(overtime_hours), 0.0) as total_ot
        FROM attendance
        WHERE employee_id = ? AND date LIKE ?
    """, (emp["id"], month_pattern)).fetchone()

    total = stats["total_logged"]
    rate = round(((stats["present_days"] + stats["half_days"] * 0.5) / total * 100), 1) if total > 0 else 100.0
    stats_dict = dict(stats)
    stats_dict["rate"] = rate

    daily_records = conn.execute("""
        SELECT * FROM attendance
        WHERE employee_id = ? AND date LIKE ?
        ORDER BY date ASC
    """, (emp["id"], month_pattern)).fetchall()

    leaves = conn.execute("""
        SELECT * FROM leave_requests
        WHERE employee_id = ? AND (start_date LIKE ? OR end_date LIKE ?)
        ORDER BY start_date ASC
    """, (emp["id"], month_pattern, month_pattern)).fetchall()

    conn.close()

    whatsapp_url = build_whatsapp_attendance_url(dict(emp), stats_dict, selected_month, user, request.host_url.rstrip("/"))

    return render_template(
        "attendance_report.html",
        emp=emp,
        stats=stats_dict,
        daily_records=daily_records,
        leaves=leaves,
        selected_month=selected_month,
        user=user,
        whatsapp_url=whatsapp_url,
        today=date.today().strftime("%Y-%m-%d")
    )


@app.route("/attendance/whatsapp/<int:employee_id>")
@login_required
def send_attendance_whatsapp(employee_id):
    user = get_current_user()
    conn = get_db_connection()
    emp = conn.execute("SELECT * FROM employees WHERE id = ? AND user_id = ?", (employee_id, user["id"])).fetchone()
    if not emp:
        conn.close()
        flash("Employee not found.", "warning")
        return redirect(url_for("attendance_summary"))

    selected_month = request.args.get("month", date.today().strftime("%Y-%m"))
    month_pattern = f"{selected_month}%"

    stats = conn.execute("""
        SELECT 
            COUNT(*) as total_logged,
            COUNT(CASE WHEN status = 'Present' THEN 1 END) as present_days,
            COUNT(CASE WHEN status = 'Half Day' THEN 1 END) as half_days,
            COUNT(CASE WHEN status = 'Absent' THEN 1 END) as absent_days,
            COUNT(CASE WHEN status = 'On Leave' THEN 1 END) as leave_days,
            COUNT(CASE WHEN status = 'Late' THEN 1 END) as late_days,
            COALESCE(SUM(overtime_hours), 0.0) as total_ot
        FROM attendance
        WHERE employee_id = ? AND date LIKE ?
    """, (emp["id"], month_pattern)).fetchone()
    conn.close()

    total = stats["total_logged"]
    rate = round(((stats["present_days"] + stats["half_days"] * 0.5) / total * 100), 1) if total > 0 else 100.0
    stats_dict = dict(stats)
    stats_dict["rate"] = rate

    url = build_whatsapp_attendance_url(dict(emp), stats_dict, selected_month, user, request.host_url.rstrip("/"))
    return redirect(url)


@app.route("/attendance/report-team")
@login_required
def attendance_team_report():
    user = get_current_user()
    conn = get_db_connection()
    selected_month = request.args.get("month", date.today().strftime("%Y-%m"))
    month_pattern = f"{selected_month}%"

    active_employees = conn.execute("""
        SELECT * FROM employees 
        WHERE user_id = ? AND status = 'Active' 
        ORDER BY first_name ASC
    """, (user["id"],)).fetchall()

    summary_list = []
    for emp in active_employees:
        stats = conn.execute("""
            SELECT 
                COUNT(*) as total_logged,
                COUNT(CASE WHEN status = 'Present' THEN 1 END) as present_days,
                COUNT(CASE WHEN status = 'Half Day' THEN 1 END) as half_days,
                COUNT(CASE WHEN status = 'Absent' THEN 1 END) as absent_days,
                COUNT(CASE WHEN status = 'On Leave' THEN 1 END) as leave_days,
                COUNT(CASE WHEN status = 'Late' THEN 1 END) as late_days,
                COALESCE(SUM(overtime_hours), 0.0) as total_ot
            FROM attendance
            WHERE employee_id = ? AND date LIKE ?
        """, (emp["id"], month_pattern)).fetchone()

        total = stats["total_logged"]
        rate = round(((stats["present_days"] + stats["half_days"] * 0.5) / total * 100), 1) if total > 0 else 100.0

        summary_list.append({
            "employee": emp,
            "present_days": stats["present_days"],
            "half_days": stats["half_days"],
            "absent_days": stats["absent_days"],
            "leave_days": stats["leave_days"],
            "late_days": stats["late_days"],
            "total_ot": stats["total_ot"],
            "total_logged": total,
            "rate": rate
        })
    conn.close()
    return render_template("attendance_team_report.html", summary_list=summary_list, selected_month=selected_month, user=user)


# --- Leave Management Routes ---

@app.route("/leaves")
@login_required
def leaves():
    user = get_current_user()
    status_filter = request.args.get("status", "").strip()

    conn = get_db_connection()
    query = """
        SELECT l.*, e.first_name, e.last_name, e.employee_code, e.department
        FROM leave_requests l
        JOIN employees e ON l.employee_id = e.id
        WHERE l.user_id = ?
    """
    params = [user["id"]]

    if status_filter:
        query += " AND l.status = ?"
        params.append(status_filter)

    query += " ORDER BY l.id DESC"
    leave_list = conn.execute(query, params).fetchall()

    active_employees = conn.execute("""
        SELECT * FROM employees 
        WHERE user_id = ? AND status = 'Active' 
        ORDER BY first_name ASC
    """, (user["id"],)).fetchall()

    pending_count = conn.execute(
        "SELECT COUNT(*) FROM leave_requests WHERE user_id = ? AND status = 'Pending'",
        (user["id"],)
    ).fetchone()[0]

    approved_count = conn.execute(
        "SELECT COUNT(*) FROM leave_requests WHERE user_id = ? AND status = 'Approved'",
        (user["id"],)
    ).fetchone()[0]

    conn.close()

    return render_template(
        "leaves.html",
        leaves=leave_list,
        employees=active_employees,
        selected_status=status_filter,
        pending_count=pending_count,
        approved_count=approved_count
    )


@app.route("/leaves/add", methods=["POST"])
@login_required
def add_leave():
    user = get_current_user()
    employee_id = request.form.get("employee_id")
    leave_type = request.form.get("leave_type", "Paid Time Off")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date") or start_date
    days_count = float(request.form.get("days_count", 1.0) or 1.0)
    status = request.form.get("status", "Approved")
    reason = request.form.get("reason", "").strip()

    if not employee_id or not start_date:
        flash("Employee and Start Date are required.", "danger")
        return redirect(url_for("leaves"))

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO leave_requests (user_id, employee_id, leave_type, start_date, end_date, days_count, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user["id"], employee_id, leave_type, start_date, end_date, days_count, status, reason))

    # If approved, also sync as 'On Leave' into attendance table for that start date
    if status == "Approved":
        conn.execute("""
            INSERT INTO attendance (user_id, employee_id, date, status, clock_in, clock_out, working_hours, overtime_hours, notes)
            VALUES (?, ?, ?, 'On Leave', '-', '-', 0.0, 0.0, ?)
            ON CONFLICT(employee_id, date) DO UPDATE SET
                status = 'On Leave',
                working_hours = 0.0,
                notes = excluded.notes
        """, (user["id"], employee_id, start_date, f"Leave: {leave_type}"))

    conn.commit()
    conn.close()

    flash(f"Leave request recorded successfully!", "success")
    return redirect(url_for("leaves"))


@app.route("/leaves/status/<int:leave_id>", methods=["POST"])
@login_required
def update_leave_status(leave_id):
    user = get_current_user()
    new_status = request.form.get("status", "Approved")

    conn = get_db_connection()
    leave = conn.execute("SELECT * FROM leave_requests WHERE id = ? AND user_id = ?", (leave_id, user["id"])).fetchone()
    if leave:
        conn.execute("UPDATE leave_requests SET status = ? WHERE id = ?", (new_status, leave_id))
        if new_status == "Approved":
            conn.execute("""
                INSERT INTO attendance (user_id, employee_id, date, status, clock_in, clock_out, working_hours, overtime_hours, notes)
                VALUES (?, ?, ?, 'On Leave', '-', '-', 0.0, 0.0, ?)
                ON CONFLICT(employee_id, date) DO UPDATE SET
                    status = 'On Leave',
                    working_hours = 0.0,
                    notes = excluded.notes
            """, (user["id"], leave["employee_id"], leave["start_date"], f"Leave: {leave['leave_type']}"))
        conn.commit()
        flash(f"Leave status updated to {new_status}.", "success")

    conn.close()
    return redirect(url_for("leaves"))


@app.route("/leaves/delete/<int:leave_id>", methods=["POST"])
@login_required
def delete_leave(leave_id):
    user = get_current_user()
    conn = get_db_connection()
    conn.execute("DELETE FROM leave_requests WHERE id = ? AND user_id = ?", (leave_id, user["id"]))
    conn.commit()
    conn.close()
    flash("Leave record deleted.", "info")
    return redirect(url_for("leaves"))


# --- Payroll Runs & Processing ---

@app.route("/payroll")
@login_required
def payroll_list():
    user = get_current_user()
    conn = get_db_connection()
    runs = conn.execute("""
        SELECT * FROM payroll_runs 
        WHERE user_id = ? 
        ORDER BY id DESC
    """, (user["id"],)).fetchall()
    conn.close()
    return render_template("payroll.html", runs=runs)


@app.route("/payroll/new", methods=["GET", "POST"])
@login_required
def new_payroll():
    user = get_current_user()
    conn = get_db_connection()

    if request.method == "POST":
        title = request.form.get("title", "").strip() or f"Payroll - {datetime.now().strftime('%B %Y')}"
        pay_period_start = request.form.get("pay_period_start", "")
        pay_period_end = request.form.get("pay_period_end", "")
        pay_date = request.form.get("pay_date", "") or datetime.now().strftime("%Y-%m-%d")

        # Get list of employee IDs selected
        selected_emp_ids = request.form.getlist("employee_ids")
        if not selected_emp_ids:
            flash("Please select at least one employee to process payroll.", "warning")
            return redirect(url_for("new_payroll"))

        total_gross = 0.0
        total_deductions = 0.0
        total_net = 0.0
        payslips_data = []

        for emp_id in selected_emp_ids:
            emp = conn.execute("SELECT * FROM employees WHERE id = ? AND user_id = ?", (emp_id, user["id"])).fetchone()
            if not emp:
                continue

            base = float(request.form.get(f"base_{emp_id}", emp["base_salary"]) or 0)
            da = float(request.form.get(f"da_{emp_id}", 0) or 0)
            hra = float(request.form.get(f"hra_{emp_id}", 0) or 0)
            bonus = float(request.form.get(f"bonus_{emp_id}", 0) or 0)
            overtime = float(request.form.get(f"overtime_{emp_id}", 0) or 0)
            allowances = float(request.form.get(f"allowances_{emp_id}", 0) or 0)

            gross = base + da + hra + bonus + overtime + allowances

            epf = float(request.form.get(f"epf_{emp_id}", 0) or 0)
            eps = float(request.form.get(f"eps_{emp_id}", 0) or 0)
            house_rent = float(request.form.get(f"house_rent_{emp_id}", 0) or 0)
            tax_rate = float(request.form.get(f"tax_rate_{emp_id}", user["default_tax_rate"]) or 0)
            tax_deduction = round(gross * (tax_rate / 100.0), 2)
            insurance = float(request.form.get(f"insurance_{emp_id}", 0) or 0)
            other_ded = float(request.form.get(f"other_ded_{emp_id}", 0) or 0)

            total_ded = epf + eps + house_rent + tax_deduction + insurance + other_ded
            net = max(0.0, gross - total_ded)
            notes = request.form.get(f"notes_{emp_id}", "")

            total_gross += gross
            total_deductions += total_ded
            total_net += net

            payslips_data.append({
                "emp_id": emp_id,
                "base": base,
                "da": da,
                "hra": hra,
                "bonus": bonus,
                "overtime": overtime,
                "allowances": allowances,
                "gross": gross,
                "epf": epf,
                "eps": eps,
                "house_rent": house_rent,
                "tax": tax_deduction,
                "insurance": insurance,
                "other_ded": other_ded,
                "total_ded": total_ded,
                "net": net,
                "notes": notes
            })

        # Insert Payroll Run
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO payroll_runs (
                user_id, title, pay_period_start, pay_period_end, pay_date,
                total_gross, total_deductions, total_net, employee_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Completed')
        """, (
            user["id"], title, pay_period_start, pay_period_end, pay_date,
            total_gross, total_deductions, total_net, len(payslips_data)
        ))
        payroll_run_id = cursor.lastrowid

        # Insert individual Payslips
        for item in payslips_data:
            cursor.execute("""
                INSERT INTO payslips (
                    payroll_run_id, employee_id, base_salary, bonus, overtime_pay, allowances,
                    da_amount, hra_amount, epf_deduction, eps_deduction, house_rent_deduction,
                    tax_deduction, insurance_deduction, other_deductions,
                    gross_pay, total_deductions, net_pay, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                payroll_run_id, item["emp_id"], item["base"], item["bonus"], item["overtime"], item["allowances"],
                item["da"], item["hra"], item["epf"], item["eps"], item["house_rent"],
                item["tax"], item["insurance"], item["other_ded"],
                item["gross"], item["total_ded"], item["net"], item["notes"]
            ))

        conn.commit()
        conn.close()

        flash(f"🎉 Payroll '{title}' completed smoothly! Total payout: {user['currency']}{total_net:,.2f}", "success")
        return redirect(url_for("view_payroll", run_id=payroll_run_id))

    # GET request: load active employees
    active_employees = conn.execute("""
        SELECT * FROM employees 
        WHERE user_id = ? AND status = 'Active' 
        ORDER BY first_name ASC
    """, (user["id"],)).fetchall()

    # Default period: Current month
    today = date.today()
    first_day = today.replace(day=1).strftime("%Y-%m-%d")
    default_title = f"{today.strftime('%B %Y')} Payroll"

    period_start = request.args.get("pay_period_start", first_day)
    period_end = request.args.get("pay_period_end", today.strftime("%Y-%m-%d"))

    # Calculate attendance and leave adjustments for every active employee
    emp_cards = []
    for emp_row in active_employees:
        emp = dict(emp_row)
        att = conn.execute("""
            SELECT 
                COUNT(*) as total_logged,
                COUNT(CASE WHEN status = 'Present' THEN 1 END) as present_days,
                COUNT(CASE WHEN status = 'Half Day' THEN 1 END) as half_days,
                COUNT(CASE WHEN status = 'Absent' THEN 1 END) as absent_days,
                COUNT(CASE WHEN status = 'On Leave' THEN 1 END) as leave_days,
                COUNT(CASE WHEN status = 'Late' THEN 1 END) as late_days,
                COALESCE(SUM(overtime_hours), 0.0) as total_ot
            FROM attendance
            WHERE employee_id = ? AND date BETWEEN ? AND ?
        """, (emp["id"], period_start, period_end)).fetchone()

        daily_rate = round(emp["base_salary"] / 22.0, 2)
        hourly_rate = round(daily_rate / 8.0, 2)
        unpaid_deduction = round((att["absent_days"] + att["half_days"] * 0.5) * daily_rate, 2)
        ot_pay = round(att["total_ot"] * hourly_rate * 1.5, 2)

        emp["att_stats"] = {
            "total_logged": att["total_logged"],
            "present_days": att["present_days"],
            "half_days": att["half_days"],
            "absent_days": att["absent_days"],
            "leave_days": att["leave_days"],
            "late_days": att["late_days"],
            "total_ot": att["total_ot"],
            "unpaid_deduction": unpaid_deduction,
            "ot_pay": ot_pay,
            "has_records": att["total_logged"] > 0
        }

        # Statutory & Allowances Defaults
        da_rate = float(user["default_da_rate"] or 0) if "default_da_rate" in user.keys() else 0.0
        hra_rate = float(user["default_hra_rate"] or 0) if "default_hra_rate" in user.keys() else 0.0
        epf_rate = float(user["default_epf_rate"] if ("default_epf_rate" in user.keys() and user["default_epf_rate"] is not None) else 12.0)
        eps_rate = float(user["default_eps_rate"] or 0) if "default_eps_rate" in user.keys() else 0.0
        default_rent = float(user["default_house_rent"] or 0) if "default_house_rent" in user.keys() else 0.0

        calc_da = round(emp["base_salary"] * (da_rate / 100.0), 2) if da_rate > 0 else 0.0
        calc_hra = round(emp["base_salary"] * (hra_rate / 100.0), 2) if hra_rate > 0 else 0.0
        calc_epf = round((emp["base_salary"] + calc_da) * (epf_rate / 100.0), 2) if epf_rate > 0 else 0.0
        calc_eps = round(eps_rate, 2)
        calc_rent = round(default_rent, 2)

        emp["defaults"] = {
            "da": calc_da,
            "hra": calc_hra,
            "epf": calc_epf,
            "eps": calc_eps,
            "house_rent": calc_rent
        }
        emp_cards.append(emp)

    conn.close()

    return render_template(
        "payroll_new.html",
        employees=emp_cards,
        default_title=default_title,
        first_day=period_start,
        today=period_end
    )


@app.route("/payroll/view/<int:run_id>")
@login_required
def view_payroll(run_id):
    user = get_current_user()
    conn = get_db_connection()

    run = conn.execute("""
        SELECT * FROM payroll_runs 
        WHERE id = ? AND user_id = ?
    """, (run_id, user["id"])).fetchone()

    if not run:
        conn.close()
        flash("Payroll run not found.", "warning")
        return redirect(url_for("payroll_list"))

    payslip_rows = conn.execute("""
        SELECT p.*, e.first_name, e.last_name, e.employee_code, e.department, e.designation, 
               e.bank_name, e.bank_account, e.phone, e.email,
               pr.title AS run_title, pr.pay_date
        FROM payslips p
        JOIN payroll_runs pr ON p.payroll_run_id = pr.id
        JOIN employees e ON p.employee_id = e.id
        WHERE p.payroll_run_id = ?
        ORDER BY e.first_name ASC
    """, (run_id,)).fetchall()

    payslips = [dict(row) for row in payslip_rows]

    conn.close()
    return render_template("payroll_view.html", run=run, payslips=payslips)


@app.route("/payroll/delete/<int:run_id>", methods=["POST"])
@login_required
def delete_payroll(run_id):
    user = get_current_user()
    conn = get_db_connection()
    conn.execute("DELETE FROM payroll_runs WHERE id = ? AND user_id = ?", (run_id, user["id"]))
    conn.commit()
    conn.close()
    flash("Payroll run deleted successfully.", "info")
    return redirect(url_for("payroll_list"))


@app.route("/payroll/export/<int:run_id>")
@login_required
def export_payroll_csv(run_id):
    user = get_current_user()
    conn = get_db_connection()

    run = conn.execute("SELECT * FROM payroll_runs WHERE id = ? AND user_id = ?", (run_id, user["id"])).fetchone()
    if not run:
        conn.close()
        flash("Payroll run not found.", "warning")
        return redirect(url_for("payroll_list"))

    payslips = conn.execute("""
        SELECT p.*, e.first_name, e.last_name, e.employee_code, e.department, e.designation, e.bank_name, e.bank_account
        FROM payslips p
        JOIN employees e ON p.employee_id = e.id
        WHERE p.payroll_run_id = ?
        ORDER BY e.first_name ASC
    """, (run_id,)).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Employee Code", "Employee Name", "Department", "Designation",
        "Base Salary", "DA Amount", "HRA Amount", "Bonus", "Overtime", "Allowances", "Gross Pay",
        "EPF Deduction", "EPS Deduction", "House Rent Deduction",
        "Tax Deduction", "Insurance Deduction", "Other Deductions", "Total Deductions", "Net Pay",
        "Bank Name", "Bank Account"
    ])

    for p in payslips:
        writer.writerow([
            p["employee_code"],
            f"{p['first_name']} {p['last_name']}",
            p["department"],
            p["designation"],
            p["base_salary"],
            p["da_amount"] if "da_amount" in p.keys() else 0.0,
            p["hra_amount"] if "hra_amount" in p.keys() else 0.0,
            p["bonus"],
            p["overtime_pay"],
            p["allowances"],
            p["gross_pay"],
            p["epf_deduction"] if "epf_deduction" in p.keys() else 0.0,
            p["eps_deduction"] if "eps_deduction" in p.keys() else 0.0,
            p["house_rent_deduction"] if "house_rent_deduction" in p.keys() else 0.0,
            p["tax_deduction"],
            p["insurance_deduction"],
            p["other_deductions"],
            p["total_deductions"],
            p["net_pay"],
            p["bank_name"],
            p["bank_account"]
        ])

    output.seek(0)
    filename = f"payroll_{run['title'].replace(' ', '_')}_{run['pay_date']}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def build_whatsapp_payslip_url(p, user):
    phone = p.get("emp_phone") or p.get("phone") or ""
    clean_phone = re.sub(r"[^\d]", "", str(phone))

    bonus_ot = float(p.get("bonus") or 0) + float(p.get("overtime_pay") or 0)
    
    msg = (
        f"🏛️ *OFFICIAL SALARY ADVICE - {user['company_name']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Employee:* {p['first_name']} {p['last_name']} ({p['employee_code']})\n"
        f"💼 *Role:* {p.get('designation') or 'Team Member'} | {p.get('department') or 'General'}\n"
        f"📅 *Period:* {p.get('run_title', 'Payroll')}\n"
        f"🗓️ *Pay Date:* {p.get('pay_date', '')}\n\n"
        f"💵 *Base Salary:* {user['currency']}{float(p.get('base_salary') or 0):,.2f}\n"
    )
    if float(p.get("da_amount") or 0) > 0:
        msg += f"   • Dearness Allowance (DA): +{user['currency']}{float(p.get('da_amount')):,.2f}\n"
    if float(p.get("hra_amount") or 0) > 0:
        msg += f"   • House Rent Allowance (HRA): +{user['currency']}{float(p.get('hra_amount')):,.2f}\n"
    if bonus_ot > 0:
        msg += f"✨ *Bonus / Overtime:* +{user['currency']}{bonus_ot:,.2f}\n"
    
    msg += (
        f"📊 *Gross Pay:* {user['currency']}{float(p.get('gross_pay') or 0):,.2f}\n"
    )
    if float(p.get("epf_deduction") or 0) > 0:
        msg += f"   • EPF (Provident Fund): -{user['currency']}{float(p.get('epf_deduction')):,.2f}\n"
    if float(p.get("eps_deduction") or 0) > 0:
        msg += f"   • EPS (Pension Scheme): -{user['currency']}{float(p.get('eps_deduction')):,.2f}\n"
    if float(p.get("house_rent_deduction") or 0) > 0:
        msg += f"   • House Rent Deduction: -{user['currency']}{float(p.get('house_rent_deduction')):,.2f}\n"

    msg += (
        f"🔻 *Total Deductions:* -{user['currency']}{float(p.get('total_deductions') or 0):,.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *NET SALARY PAID:* *{user['currency']}{float(p.get('net_pay') or 0):,.2f}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 *Disbursed To:* {p.get('bank_name') or 'Bank'} ({p.get('bank_account') or 'Verified Account'})\n"
        f"✅ *Status:* Successfully Processed\n\n"
        f"_Generated securely via EasyPayroll._"
    )
    
    encoded_text = urllib.parse.quote(msg)
    if clean_phone:
        return f"https://wa.me/{clean_phone}?text={encoded_text}"
    else:
        return f"https://api.whatsapp.com/send?text={encoded_text}"


# --- Payslip Detailed View (Print / PDF) ---

@app.route("/payslip/<int:payslip_id>")
@login_required
def view_payslip(payslip_id):
    user = get_current_user()
    conn = get_db_connection()

    payslip = conn.execute("""
        SELECT p.*, 
               pr.title AS run_title, pr.pay_date, pr.pay_period_start, pr.pay_period_end,
               e.first_name, e.last_name, e.employee_code, e.department, e.designation,
               e.email AS emp_email, e.phone AS emp_phone, e.tax_id, e.bank_name, e.bank_account
        FROM payslips p
        JOIN payroll_runs pr ON p.payroll_run_id = pr.id
        JOIN employees e ON p.employee_id = e.id
        WHERE p.id = ? AND pr.user_id = ?
    """, (payslip_id, user["id"])).fetchone()

    conn.close()

    if not payslip:
        flash("Payslip not found.", "warning")
        return redirect(url_for("payroll_list"))

    return render_template("payslip.html", payslip=payslip, user=user)


@app.route("/payslip/<int:payslip_id>/whatsapp")
@login_required
def send_payslip_whatsapp(payslip_id):
    flash("Payslip WhatsApp sharing has been disabled. You can share Attendance Statements via WhatsApp from the Attendance Tracker.", "info")
    return redirect(url_for("view_payslip", payslip_id=payslip_id))


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon"
    )


# --- Settings ---

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user = get_current_user()
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip() or user["company_name"]
        currency = request.form.get("currency", "").strip() or "₹"
        default_tax_rate = float(request.form.get("default_tax_rate", 10.0) or 0)
        default_da_rate = float(request.form.get("default_da_rate", 0.0) or 0)
        default_hra_rate = float(request.form.get("default_hra_rate", 0.0) or 0)
        default_epf_rate = float(request.form.get("default_epf_rate", 12.0) or 0)
        default_eps_rate = float(request.form.get("default_eps_rate", 0.0) or 0)
        default_house_rent = float(request.form.get("default_house_rent", 0.0) or 0)
        address = request.form.get("address", "").strip() or ""
        logo_url = request.form.get("logo_url", "").strip()

        conn = get_db_connection()
        conn.execute("""
            UPDATE users SET 
                company_name = ?, currency = ?, default_tax_rate = ?, 
                default_da_rate = ?, default_hra_rate = ?, default_epf_rate = ?,
                default_eps_rate = ?, default_house_rent = ?, address = ?, logo_url = ?
            WHERE id = ?
        """, (company_name, currency, default_tax_rate, 
              default_da_rate, default_hra_rate, default_epf_rate,
              default_eps_rate, default_house_rent, address, logo_url, user["id"]))
        conn.commit()
        conn.close()

        flash("Settings updated successfully!", "success")
        return redirect(url_for("settings"))

    return render_template("settings.html", user=user)


@app.route("/settings/backup")
@login_required
def download_backup():
    if os.path.exists(DB_PATH):
        return send_file(
            DB_PATH,
            as_attachment=True,
            download_name=f"payroll_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        )
    flash("Database file not found.", "danger")
    return redirect(url_for("settings"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
