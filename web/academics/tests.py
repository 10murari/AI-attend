from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from .models import Batch, Department, Subject


class StudentBatchRollGenerationTests(TestCase):
	def setUp(self):
		self.admin_user = CustomUser.objects.create(
			username='admin1',
			full_name='Admin User',
			role='admin',
			is_active=True,
		)
		self.admin_user.set_password('admin1234')
		self.admin_user.save(update_fields=['password'])

		self.department = Department.objects.create(
			name='Computer Engineering',
			code='COMP',
			roll_code='03',
			is_active=True,
		)
		self.batch_2026 = Batch.objects.create(
			department=self.department,
			year=2026,
			is_active=True,
		)

		self.client.login(username='admin1', password='admin1234')

	def _create_student(self, full_name):
		return self.client.post(reverse('student_create'), {
			'batch_year': 2026,
			'department': self.department.id,
			'full_name': full_name,
			'semester': 1,
			'email': '',
			'phone': '',
			'password': '',
		})

	def test_student_create_generates_first_roll(self):
		response = self._create_student('First Student')
		self.assertEqual(response.status_code, 302)

		student = CustomUser.objects.get(full_name='First Student')
		self.assertEqual(student.role, 'student')
		self.assertEqual(student.batch_id, self.batch_2026.id)
		self.assertEqual(student.batch_sequence, 1)
		self.assertEqual(student.roll_no, '260301')
		self.assertEqual(student.username, '260301')

	def test_student_create_increments_batch_sequence(self):
		response_1 = self._create_student('First Student')
		response_2 = self._create_student('Second Student')
		self.assertEqual(response_1.status_code, 302)
		self.assertEqual(response_2.status_code, 302)

		student_1 = CustomUser.objects.get(full_name='First Student')
		student_2 = CustomUser.objects.get(full_name='Second Student')
		self.assertEqual(student_1.roll_no, '260301')
		self.assertEqual(student_2.roll_no, '260302')
		self.assertEqual(student_2.batch_sequence, 2)

	def test_student_create_auto_creates_batch(self):
		Batch.objects.all().delete()
		response = self._create_student('Auto Batch Student')
		self.assertEqual(response.status_code, 302)

		batch = Batch.objects.get(department=self.department, year=2026)
		student = CustomUser.objects.get(full_name='Auto Batch Student')
		self.assertEqual(student.batch_id, batch.id)
		self.assertEqual(batch.code, '26')


class SemesterLifecyclePromotionGuardTests(TestCase):
	def setUp(self):
		self.admin_user = CustomUser.objects.create(
			username='admin_lifecycle',
			full_name='Admin Lifecycle',
			role='admin',
			is_active=True,
		)
		self.admin_user.set_password('admin1234')
		self.admin_user.save(update_fields=['password'])

		self.department = Department.objects.create(
			name='Civil Engineering',
			code='CIVIL',
			roll_code='01',
			is_active=True,
		)
		self.batch = Batch.objects.create(
			department=self.department,
			year=2026,
			code='26',
			is_active=True,
		)

		self.client.login(username='admin_lifecycle', password='admin1234')

	def _create_student(self, username, full_name, roll_no, semester, sequence):
		return CustomUser.objects.create(
			username=username,
			full_name=full_name,
			role='student',
			roll_no=roll_no,
			department=self.department,
			batch=self.batch,
			batch_sequence=sequence,
			semester=semester,
			is_active=True,
		)

	def test_promote_semester_blocked_if_target_has_students(self):
		source_student = self._create_student(
			username='s501',
			full_name='Sem5 Student',
			roll_no='260101',
			semester=5,
			sequence=1,
		)
		self._create_student(
			username='s601',
			full_name='Sem6 Existing',
			roll_no='260102',
			semester=6,
			sequence=2,
		)

		response = self.client.post(reverse('promote_semester'), {
			'department': self.department.id,
			'batch': self.batch.id,
			'from_semester': 5,
		}, follow=True)

		self.assertEqual(response.status_code, 200)
		source_student.refresh_from_db()
		self.assertEqual(source_student.semester, 5)
		self.assertContains(response, 'Promotion blocked', status_code=200)

	def test_promote_semester_success_when_target_empty(self):
		source_student = self._create_student(
			username='s701',
			full_name='Sem7 Student',
			roll_no='260103',
			semester=7,
			sequence=3,
		)

		response = self.client.post(reverse('promote_semester'), {
			'department': self.department.id,
			'batch': self.batch.id,
			'from_semester': 7,
		}, follow=True)

		self.assertEqual(response.status_code, 200)
		source_student.refresh_from_db()
		self.assertEqual(source_student.semester, 8)
		self.assertContains(response, 'Promoted 1 students from Semester 7 to Semester 8', status_code=200)


class AdminAllSessionsBatchFilterTests(TestCase):
	def setUp(self):
		self.admin_user = CustomUser.objects.create(
			username='admin_sessions',
			full_name='Admin Sessions',
			role='admin',
			is_active=True,
		)
		self.admin_user.set_password('admin1234')
		self.admin_user.save(update_fields=['password'])

		self.department = Department.objects.create(
			name='Electrical Engineering',
			code='ELEC',
			roll_code='51',
			is_active=True,
		)
		self.batch_2026 = Batch.objects.create(department=self.department, year=2026, code='26', is_active=True)
		self.batch_2025 = Batch.objects.create(department=self.department, year=2025, code='25', is_active=True)

		self.teacher = CustomUser.objects.create(
			username='teacher_sessions',
			full_name='Teacher Sessions',
			role='teacher',
			department=self.department,
			is_active=True,
		)

		from attendance.models import Session
		subject = Subject.objects.create(
			name='Power Systems',
			code='ELEC401',
			department=self.department,
			semester=4,
			credit_hours=3,
			is_active=True,
		)

		self.session_2026 = Session.objects.create(
			subject=subject,
			teacher=self.teacher,
			department=self.department,
			batch=self.batch_2026,
			semester=4,
			status='COMPLETED',
		)
		self.session_2025 = Session.objects.create(
			subject=subject,
			teacher=self.teacher,
			department=self.department,
			batch=self.batch_2025,
			semester=4,
			status='COMPLETED',
		)

		self.client.login(username='admin_sessions', password='admin1234')

	def test_admin_all_sessions_can_filter_by_batch(self):
		response = self.client.get(reverse('admin_all_sessions'), {
			'batch': self.batch_2026.id,
		})

		self.assertEqual(response.status_code, 200)
		sessions = list(response.context['sessions'])
		self.assertEqual(len(sessions), 1)
		self.assertEqual(sessions[0].id, self.session_2026.id)
