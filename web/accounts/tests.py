from django.test import TestCase

from academics.models import Batch, Department, Subject, SubjectTeacher
from attendance.models import Attendance, Session
from accounts.models import CustomUser
from .views import get_student_context


class StudentDashboardBatchScopedStatsTests(TestCase):
	def setUp(self):
		self.dept = Department.objects.create(code='ECE', name='Electronics', roll_code='31')
		self.batch_a = Batch.objects.create(department=self.dept, year=2026, code='26', is_active=True)
		self.batch_b = Batch.objects.create(department=self.dept, year=2025, code='25', is_active=True)

		self.teacher = CustomUser.objects.create_user(
			username='teacher_dash',
			password='testpass123',
			role='teacher',
			department=self.dept,
		)
		self.student = CustomUser.objects.create_user(
			username='student_dash',
			password='testpass123',
			role='student',
			roll_no='263101',
			department=self.dept,
			semester=3,
			batch=self.batch_a,
			batch_sequence=1,
			is_active=True,
		)

		self.subject = Subject.objects.create(
			code='ECE301',
			name='Signals',
			department=self.dept,
			semester=3,
			credit_hours=3,
			is_active=True,
		)
		SubjectTeacher.objects.create(teacher=self.teacher, subject=self.subject)

		self.session_a = Session.objects.create(
			subject=self.subject,
			teacher=self.teacher,
			department=self.dept,
			batch=self.batch_a,
			semester=3,
			date='2026-04-01',
			status='COMPLETED',
			total_present=1,
		)
		self.session_b = Session.objects.create(
			subject=self.subject,
			teacher=self.teacher,
			department=self.dept,
			batch=self.batch_b,
			semester=3,
			date='2026-04-01',
			status='COMPLETED',
			total_present=1,
		)

		Attendance.objects.create(
			session=self.session_a,
			student=self.student,
			status=Attendance.Status.PRESENT,
		)

	def test_get_student_context_counts_only_own_batch(self):
		context = get_student_context(self.student)

		self.assertEqual(context['total_sessions'], 1)
		self.assertEqual(context['total_present'], 1)
		self.assertEqual(context['overall_percentage'], 100.0)
