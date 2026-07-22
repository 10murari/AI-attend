"""End-to-end test of CSV bulk import views using Django's test client.

Runs against an in-memory test DB (via manage.py test-style setup) — does NOT
touch the real database.
"""
import io

from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from academics.models import Batch, Department


def csv_file(name, text):
    f = io.BytesIO(text.encode('utf-8'))
    f.name = name
    return f


class CSVImportTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin1', password='pass1234', role='admin', full_name='Admin'
        )
        self.client.login(username='admin1', password='pass1234')

    def test_department_import_ok(self):
        resp = self.client.post(reverse('department_import'), {
            'csv_file': csv_file('d.csv',
                'name,code,roll_code\n'
                'Computer Engineering,COMP,03\n'
                'Civil Engineering,CIVIL,01\n'
            )
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Department.objects.count(), 2)
        self.assertEqual(Department.objects.get(code='COMP').roll_code, '03')

    def test_department_import_bad_rollcode_rejects_all(self):
        resp = self.client.post(reverse('department_import'), {
            'csv_file': csv_file('d.csv',
                'name,code,roll_code\n'
                'Computer Engineering,COMP,03\n'
                'Civil Engineering,CIVIL,ABC\n'
            )
        })
        self.assertContains(resp, 'roll_code must be exactly 2 digits')
        self.assertEqual(Department.objects.count(), 0)  # all-or-nothing

    def test_teacher_import_ok_and_default_password(self):
        Department.objects.create(name='Comp', code='COMP', roll_code='03')
        resp = self.client.post(reverse('teacher_import'), {
            'csv_file': csv_file('t.csv',
                'username,full_name,department_code,email,phone,password\n'
                'prof.sharma,Ram Sharma,COMP,ram@example.com,980000,\n'
                'prof.thapa,Sita Thapa,,,,secret123\n'
            )
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        t1 = CustomUser.objects.get(username='prof.sharma')
        self.assertEqual(t1.role, 'teacher')
        self.assertEqual(t1.department.code, 'COMP')
        self.assertTrue(t1.check_password('prof.sharma'))  # default = username
        t2 = CustomUser.objects.get(username='prof.thapa')
        self.assertTrue(t2.check_password('secret123'))
        self.assertIsNone(t2.department)

    def test_teacher_import_duplicate_username(self):
        CustomUser.objects.create_user(username='prof.sharma', password='x1234', role='teacher')
        resp = self.client.post(reverse('teacher_import'), {
            'csv_file': csv_file('t.csv',
                'username,full_name\nprof.sharma,Ram Sharma\n'
            )
        })
        self.assertContains(resp, 'already exists')
        self.assertEqual(CustomUser.objects.filter(full_name='Ram Sharma').count(), 0)

    def test_student_import_generates_rolls_and_batch(self):
        Department.objects.create(name='Comp', code='COMP', roll_code='03')
        resp = self.client.post(reverse('student_import'), {
            'csv_file': csv_file('s.csv',
                'full_name,department_code,batch_year,semester\n'
                'Hari Bahadur,COMP,2026,1\n'
                'Gita Kumari,COMP,2026,1\n'
                'Shyam Lal,comp,2026,1\n'
            )
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        students = CustomUser.objects.filter(role='student').order_by('batch_sequence')
        self.assertEqual(students.count(), 3)
        rolls = [s.roll_no for s in students]
        self.assertEqual(rolls, ['260301', '260302', '260303'])
        self.assertEqual([s.username for s in students], rolls)
        self.assertTrue(students[0].check_password('260301'))  # default = roll no
        batch = Batch.objects.get(department__code='COMP', year=2026)
        self.assertEqual(batch.code, '26')
        self.assertEqual(batch.locked_semester, 1)

    def test_student_import_continues_existing_sequence(self):
        dept = Department.objects.create(name='Comp', code='COMP', roll_code='03')
        batch = Batch.objects.create(department=dept, year=2026, code='26', locked_semester=1)
        CustomUser.objects.create_user(
            username='260301', password='x1234', role='student',
            department=dept, batch=batch, batch_sequence=1, semester=1, roll_no='260301',
        )
        self.client.post(reverse('student_import'), {
            'csv_file': csv_file('s.csv',
                'full_name,department_code,batch_year,semester\nNew Kid,COMP,2026,1\n'
            )
        }, follow=True)
        new = CustomUser.objects.get(full_name='New Kid')
        self.assertEqual(new.roll_no, '260302')

    def test_student_import_semester_lock_violation_rejects_all(self):
        dept = Department.objects.create(name='Comp', code='COMP', roll_code='03')
        Batch.objects.create(department=dept, year=2026, code='26', locked_semester=1)
        resp = self.client.post(reverse('student_import'), {
            'csv_file': csv_file('s.csv',
                'full_name,department_code,batch_year,semester\n'
                'Good Row,COMP,2026,1\n'
                'Bad Row,COMP,2026,3\n'
            )
        })
        self.assertContains(resp, 'locked to')
        self.assertEqual(CustomUser.objects.filter(role='student').count(), 0)

    def test_student_import_missing_roll_code(self):
        Department.objects.create(name='Comp', code='COMP')  # no roll_code
        resp = self.client.post(reverse('student_import'), {
            'csv_file': csv_file('s.csv',
                'full_name,department_code,batch_year,semester\nHari,COMP,2026,1\n'
            )
        })
        self.assertContains(resp, 'no roll code')
        self.assertEqual(CustomUser.objects.filter(role='student').count(), 0)

    def test_missing_column_reported(self):
        resp = self.client.post(reverse('student_import'), {
            'csv_file': csv_file('s.csv', 'full_name\nHari\n')
        })
        self.assertContains(resp, 'Missing required column(s)')

    def test_template_download(self):
        for kind in ('departments', 'teachers', 'students'):
            resp = self.client.get(reverse('import_template', args=[kind]))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp['Content-Type'], 'text/csv')

    def test_non_admin_blocked(self):
        CustomUser.objects.create_user(username='teach', password='pass1234', role='teacher')
        self.client.login(username='teach', password='pass1234')
        resp = self.client.get(reverse('student_import'))
        self.assertEqual(resp.status_code, 302)  # redirected to dashboard
