# EasyPayroll — Comprehensive Free & Stress-Free Payroll Management System

A modern, fast, and completely free web-based payroll and HR management platform designed to make payroll, attendance, and leave management effortless for small business owners, agencies, startups, and freelancers.

---

## 🌟 Complete Tool Suite Included

### 1. 🕒 Attendance & Time Clock
- **Daily Attendance Sheet**: Select any date to record employee presence (`Present`, `Half Day`, `Absent (Unpaid)`, `On Leave`, `Late`).
- **1-Click "Mark All Present"**: Mark the entire team present in 1 second.
- **Work Hours & Overtime**: Track clock-in time, clock-out time, standard working hours, and overtime hours.
- **Monthly Attendance Summary**: Monthly rollup per team member showing total days logged, days present, half days, absences, total overtime hours, and percentage attendance rates.

### 2. 🏖️ Leave Management
- **Leave Requests & PTO**: Record time off across Paid Annual Leave, Sick Leave, Casual Leave, and Unpaid Leave.
- **1-Click Status Workflow**: Approve, Reject, or Review pending leave requests.
- **Automatic Attendance Sync**: When a leave is approved, the system automatically registers the employee as `On Leave` for those dates.

### 3. 🤖 Intelligent Attendance-to-Payroll Integration
- **Automated Absence Deductions**: The system automatically scans attendance logs for the chosen pay period and calculates exact salary deductions for unpaid absences and half-days (`base_salary / 22 * absent_days`).
- **Automated Overtime Pay**: Overtime hours logged in attendance automatically calculate overtime pay into the payroll sheet.
- **Visual Attendance Badges**: In the pay run wizard, you see an immediate breakdown: `✅ 20 Present | ❌ 2 Absent (-$454.55) | ⏱️ 4h OT (+$155.00)`.

### 4. ⚡ 1-Click Pay Runs
- Pre-fills all active employee salaries automatically.
- Adjust overtime, bonuses, tax withholding, and insurance in real-time.
- Live interactive summary calculation before confirming.

### 5. 👥 Employee Directory & Pre-loaded Demo Team
- Manage team roster with designations, departments, compensation, and bank payout details.
- Real-time search and filter by department or status (Active, On Leave, Inactive).
- **"Add Demo Team" button**: Pre-populates 5 realistic sample employees across Engineering, Design, Marketing, Sales, and HR with realistic attendance records and leaves for instant testing!

### 6. 📄 Professional Payslips & Exports
- Auto-generated for every employee in every pay run.
- Clean breakdown of earnings vs. deductions.
- Built-in **Print & Save as PDF** styling.
- Full pay run export to **CSV** for record-keeping and external accountants.

### 7. ⚙️ Company & Multi-Currency Settings
- Set company name, office address, default tax rate, and preferred currency symbol (`$`, `€`, `£`, `₹`, `AED`, `¥`, `C$`, `A$`, etc.).

---

## 🚀 How to Run the Website

### Starting the Server
From the project directory:
```bash
python app.py
```

Then open your browser:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 📂 Project Structure

```
payroll_app/
│
├── app.py                  # Full Flask backend, SQLite schema & calculations
├── test_app.py             # 13 automated unit & integration tests
├── payroll.db              # SQLite database (auto-created on start)
├── README.md               # Documentation & usage guide
│
├── templates/              # Modern Jinja2 HTML templates
│   ├── base.html           # Responsive layout & top navigation
│   ├── index.html          # Public landing page
│   ├── signup.html         # Free visitor sign-up
│   ├── login.html          # User login
│   ├── dashboard.html      # Overview & live attendance stats
│   ├── employees.html      # Employee roster & modals
│   ├── attendance.html     # Daily attendance tracker
│   ├── attendance_summary.html # Monthly attendance summary
│   ├── leaves.html         # Leave management & requests
│   ├── payroll.html        # Pay run history
│   ├── payroll_new.html    # Interactive 1-click payroll runner with auto-deductions
│   ├── payroll_view.html   # Run summary & payslips list
│   ├── payslip.html        # Printable PDF-ready payslip
│   └── settings.html       # Company & tax settings
│
└── static/
    └── css/
        └── custom.css      # Print & design stylesheets
```

---

## 📬 Developer Contact & Support
For support, feedback, or custom integrations:
- **Email**: [rprrpf1@gmail.com](mailto:rprrpf1@gmail.com)

