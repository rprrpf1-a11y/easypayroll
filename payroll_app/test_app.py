import unittest
from datetime import datetime
from app import app, get_db_connection

class PayrollAppTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def test_flow(self):
        # 1. Access landing page & brand logo / favicon
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"EasyPayroll", res.data)
        self.assertIn(b"logo.svg", res.data)

        # 1b. Verify Favicon and Logo assets serve correctly
        res_fav = self.client.get('/favicon.ico')
        self.assertEqual(res_fav.status_code, 200)
        res_logo = self.client.get('/static/images/logo.svg')
        self.assertEqual(res_logo.status_code, 200)

        test_email = f"alice_{datetime.now().timestamp()}@skyline.com"
        # 2. Signup new visitor
        res = self.client.post('/signup', data={
            'name': 'Alice Founder',
            'company_name': 'Skyline Tech',
            'email': test_email,
            'currency': '$',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Welcome to EasyPayroll", res.data)
        self.assertIn(b"Skyline Tech", res.data)

        # 3. Load demo team
        res = self.client.post('/employees/load-demo', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"sample employees", res.data)
        self.assertIn(b"Sarah Jenkins", res.data)

        # 4. Add a manual employee
        res = self.client.post('/employees/add', data={
            'first_name': 'Bob',
            'last_name': 'Martin',
            'email': f'bob_{datetime.now().timestamp()}@skyline.com',
            'phone': '1234567890',
            'department': 'DevOps',
            'designation': 'Cloud Architect',
            'base_salary': '9000',
            'status': 'Active',
            'bank_name': 'Chase',
            'bank_account': '****9999',
            'tax_id': 'TX-100'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Bob Martin", res.data)

        # 5. Access payroll new page
        res = self.client.get('/payroll/new')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Run Payroll", res.data)

        # 6. Process payroll run
        conn = get_db_connection()
        user = conn.execute("SELECT id FROM users WHERE email = ?", (test_email,)).fetchone()
        emp = conn.execute("SELECT id, base_salary FROM employees WHERE user_id = ? LIMIT 1", (user['id'],)).fetchone()
        conn.close()

        res = self.client.post('/payroll/new', data={
            'title': 'Test Payroll Run Nov 2026',
            'pay_period_start': '2026-11-01',
            'pay_period_end': '2026-11-30',
            'pay_date': '2026-11-30',
            'employee_ids': [emp['id']],
            f'base_{emp["id"]}': emp['base_salary'],
            f'da_{emp["id"]}': '2000',
            f'hra_{emp["id"]}': '4000',
            f'bonus_{emp["id"]}': '500',
            f'overtime_{emp["id"]}': '0',
            f'epf_{emp["id"]}': '1800',
            f'eps_{emp["id"]}': '1250',
            f'house_rent_{emp["id"]}': '800',
            f'tax_rate_{emp["id"]}': '10',
            f'insurance_{emp["id"]}': '50',
            f'other_ded_{emp["id"]}': '0'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Test Payroll Run Nov 2026", res.data)
        self.assertIn(b"Generated Payslips", res.data)

        # 7. Check payslip view
        conn = get_db_connection()
        payslip = conn.execute("SELECT id FROM payslips ORDER BY id DESC LIMIT 1").fetchone()
        run = conn.execute("SELECT id FROM payroll_runs ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        res = self.client.get(f'/payslip/{payslip["id"]}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Confidential Payslip", res.data)
        self.assertIn(b"Dearness Allowance (DA)", res.data)
        self.assertIn(b"Provident Fund (EPF)", res.data)
        self.assertIn(b"Pension Scheme (EPS)", res.data)
        self.assertNotIn(b"Send via WhatsApp", res.data)

        # 8. Check CSV export
        res = self.client.get(f'/payroll/export/{run["id"]}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, 'text/csv')
        self.assertIn(b"Employee Code,Employee Name", res.data)
        self.assertIn(b"DA Amount", res.data)
        self.assertIn(b"EPF Deduction", res.data)

        # 9. Test Attendance tracking
        res = self.client.get('/attendance')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Attendance Tracker", res.data)

        # 10. Test Quick Mark All Present
        res = self.client.post('/attendance/quick-all-present', data={'date': '2026-11-16'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"All active employees marked", res.data)

        # 11. Test Monthly Attendance Summary
        res = self.client.get('/attendance/summary?month=2026-11')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Monthly Attendance Summary", res.data)
        self.assertIn(b"Statement / PDF", res.data)
        self.assertIn(b"WhatsApp", res.data)

        # 11b. Test Employee Attendance Statement PDF & WhatsApp Link
        res = self.client.get(f'/attendance/report/{emp["id"]}?month=2026-11')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Attendance Statement", res.data)
        self.assertIn(b"Daily Attendance Breakdown", res.data)
        self.assertIn(b"Share Attendance on WhatsApp", res.data)

        # 11c. Test Attendance WhatsApp 1-Click Redirect
        res = self.client.get(f'/attendance/whatsapp/{emp["id"]}?month=2026-11')
        self.assertEqual(res.status_code, 302)
        loc = res.headers.get("Location", "").lower()
        self.assertTrue("wa.me" in loc or "whatsapp" in loc)

        # 11d. Test Team Attendance Report PDF
        res = self.client.get('/attendance/report-team?month=2026-11')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Team Monthly Attendance Statement", res.data)

        # 12. Test Leave Management
        res = self.client.get('/leaves')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Leave Management", res.data)

        # 13. Test Recording a Leave
        res = self.client.post('/leaves/add', data={
            'employee_id': emp['id'],
            'leave_type': 'Paid Time Off',
            'start_date': '2026-11-25',
            'end_date': '2026-11-26',
            'days_count': '2.0',
            'status': 'Approved',
            'reason': 'Thanksgiving holiday'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Leave request recorded successfully", res.data)

        print("\nAll 13 automated tests (including Attendance & Leaves) passed successfully!")

if __name__ == '__main__':
    unittest.main()
