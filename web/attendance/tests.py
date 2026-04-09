from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Attendance, AttendanceCorrectionRequest, Notification, Session
from academics.models import Batch, Department, Subject, SubjectTeacher

User = get_user_model()


class AttendanceTestDataMixin:
    def create_subject(self, department, code="CSE301", name="Data Structures"):
        kwargs = {
            "code": code,
            "name": name,
            "department": department,
        }

        field_names = {f.name for f in Subject._meta.get_fields()}
        if "semester" in field_names:
            kwargs["semester"] = 1
        if "credits" in field_names:
            kwargs["credits"] = 3
        if "is_active" in field_names:
            kwargs["is_active"] = True

        return Subject.objects.create(**kwargs)

    def setUp(self):
        self.student = User.objects.create_user(
            username="student1",
            roll_no="780322",
            password="testpass123",
            role="student",
        )
        self.teacher = User.objects.create_user(
            username="teacher1",
            password="testpass123",
            role="teacher",
        )

        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.subject = self.create_subject(self.dept)
        SubjectTeacher.objects.create(teacher=self.teacher, subject=self.subject)

        self.session = Session.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            department=self.dept,
            semester=getattr(self.subject, "semester", 1),
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status="COMPLETED",
        )


class NotificationModelTests(AttendanceTestDataMixin, TestCase):
    def test_create_notification(self):
        notification = Notification.objects.create(
            user=self.student,
            notification_type=Notification.NotificationType.ABSENT,
            title="Test Absent",
            message="You were marked absent",
        )

        self.assertEqual(notification.user, self.student)
        self.assertEqual(notification.notification_type, "absent")
        self.assertFalse(notification.is_read)

    def test_mark_notification_read(self):
        notification = Notification.objects.create(
            user=self.student,
            notification_type=Notification.NotificationType.ABSENT,
            title="Test",
            message="Test message",
        )

        notification.mark_as_read()
        notification.refresh_from_db()

        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_create_absence_notification(self):
        attendance = Attendance.objects.create(
            session=self.session,
            student=self.student,
            status=Attendance.Status.ABSENT,
        )

        notification = Notification.create_absent_notification(attendance)

        self.assertEqual(notification.user, self.student)
        self.assertEqual(notification.attendance, attendance)
        self.assertIn("Marked Absent", notification.title)


class AttendanceCorrectionRequestModelTests(AttendanceTestDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.attendance = Attendance.objects.create(
            session=self.session,
            student=self.student,
            status=Attendance.Status.ABSENT,
        )

    def test_create_correction_request(self):
        request = AttendanceCorrectionRequest.objects.create(
            attendance=self.attendance,
            student=self.student,
            reason="I was present but not marked",
            teacher=self.teacher,
        )

        self.assertEqual(request.student, self.student)
        self.assertEqual(request.status, "pending")

    def test_approve_correction_request(self):
        request = AttendanceCorrectionRequest.objects.create(
            attendance=self.attendance,
            student=self.student,
            reason="Test reason",
            teacher=self.teacher,
        )

        request.approve(self.teacher, Attendance.Status.PRESENT, "Approved")
        request.refresh_from_db()
        self.attendance.refresh_from_db()

        self.assertEqual(request.status, "approved")
        self.assertEqual(request.corrected_status, "PRESENT")
        self.assertEqual(self.attendance.status, "PRESENT")

    def test_reject_correction_request(self):
        request = AttendanceCorrectionRequest.objects.create(
            attendance=self.attendance,
            student=self.student,
            reason="Test reason",
            teacher=self.teacher,
        )

        request.reject(self.teacher, "No evidence provided")
        request.refresh_from_db()

        self.assertEqual(request.status, "rejected")

    def test_request_window_validation(self):
        old_session = Session.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            department=self.dept,
            semester=getattr(self.subject, "semester", 1),
            date=(timezone.now() - timedelta(days=3)).date(),
            start_time=timezone.now().time(),
            status="COMPLETED",
        )
        old_attendance = Attendance.objects.create(
            session=old_session,
            student=self.student,
            status=Attendance.Status.ABSENT,
        )

        request = AttendanceCorrectionRequest(
            attendance=old_attendance,
            student=self.student,
            reason="Test",
        )

        with self.assertRaises(ValidationError):
            request.full_clean()

    def test_duplicate_request_prevention(self):
        AttendanceCorrectionRequest.objects.create(
            attendance=self.attendance,
            student=self.student,
            reason="Test reason 1",
        )

        with self.assertRaises(Exception):
            AttendanceCorrectionRequest.objects.create(
                attendance=self.attendance,
                student=self.student,
                reason="Test reason 2",
            )


class NotificationAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username="student_api",
            roll_no="780323",
            password="testpass123",
            role="student",
        )
        self.client.login(username="student_api", password="testpass123")

    def test_get_notifications_api(self):
        Notification.objects.create(
            user=self.student,
            notification_type="absent",
            title="Test",
            message="Test message",
        )

        response = self.client.get("/attendance/api/notifications/")
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(len(data["notifications"]), 1)

    def test_mark_notification_read_api(self):
        notification = Notification.objects.create(
            user=self.student,
            notification_type="absent",
            title="Test",
            message="Test message",
        )

        response = self.client.post(
            f"/attendance/api/notifications/{notification.id}/read/"
        )

        self.assertEqual(response.status_code, 200)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)


class AttendanceFlowGuardTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.teacher = User.objects.create_user(
            username='teacher_guard',
            password='testpass123',
            role='teacher',
            full_name='Teacher Guard',
        )
        self.other_teacher = User.objects.create_user(
            username='teacher_other',
            password='testpass123',
            role='teacher',
            full_name='Teacher Other',
        )
        self.student_user = User.objects.create_user(
            username='student_guard',
            password='testpass123',
            role='student',
            roll_no='260101',
            full_name='Student Guard',
        )

        self.dept = Department.objects.create(code='CSE', name='Computer Science', roll_code='01')
        self.batch_2026 = Batch.objects.create(department=self.dept, year=2026, code='26', is_active=True)
        self.batch_2025 = Batch.objects.create(department=self.dept, year=2025, code='25', is_active=True)

        self.subject = Subject.objects.create(
            code='CSE401',
            name='Algorithms',
            department=self.dept,
            semester=4,
            credit_hours=3,
            is_active=True,
        )
        SubjectTeacher.objects.create(teacher=self.teacher, subject=self.subject)

        self.allowed_student = User.objects.create_user(
            username='allowed_student',
            password='testpass123',
            role='student',
            roll_no='260102',
            full_name='Allowed Student',
            department=self.dept,
            semester=4,
            batch=self.batch_2026,
            batch_sequence=2,
            is_active=True,
        )
        self.wrong_batch_student = User.objects.create_user(
            username='wrong_batch_student',
            password='testpass123',
            role='student',
            roll_no='250103',
            full_name='Wrong Batch Student',
            department=self.dept,
            semester=4,
            batch=self.batch_2025,
            batch_sequence=3,
            is_active=True,
        )

        self.session = Session.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            department=self.dept,
            batch=self.batch_2026,
            semester=4,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status='ACTIVE',
        )

    def test_mark_manual_blocks_student_outside_session_batch(self):
        self.client.login(username='teacher_guard', password='testpass123')

        response = self.client.get(
            reverse('mark_manual', args=[self.session.id, self.wrong_batch_student.id, 'PRESENT']),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Attendance.objects.filter(session=self.session, student=self.wrong_batch_student).exists()
        )
        self.assertContains(response, 'does not belong to this session cohort')

    def test_mark_manual_allows_student_in_session_batch(self):
        self.client.login(username='teacher_guard', password='testpass123')

        response = self.client.get(
            reverse('mark_manual', args=[self.session.id, self.allowed_student.id, 'PRESENT']),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        record = Attendance.objects.get(session=self.session, student=self.allowed_student)
        self.assertEqual(record.status, 'PRESENT')

    def test_student_cannot_export_session_detail_report(self):
        self.client.login(username='student_guard', password='testpass123')

        response = self.client.get(reverse('export_report_csv'), {
            'type': 'session_detail',
            'date_from': timezone.now().date().strftime('%Y-%m-%d'),
            'date_to': timezone.now().date().strftime('%Y-%m-%d'),
        })

        self.assertEqual(response.status_code, 403)

    def test_teacher_attendance_summary_limited_to_assigned_subjects(self):
        other_subject = Subject.objects.create(
            code='CSE402',
            name='Compiler',
            department=self.dept,
            semester=4,
            credit_hours=3,
            is_active=True,
        )
        SubjectTeacher.objects.create(teacher=self.other_teacher, subject=other_subject)

        Session.objects.create(
            subject=other_subject,
            teacher=self.other_teacher,
            department=self.dept,
            batch=self.batch_2026,
            semester=4,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status='COMPLETED',
            total_present=1,
            total_absent=0,
            total_late=0,
        )

        Session.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            department=self.dept,
            batch=self.batch_2026,
            semester=4,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status='COMPLETED',
            total_present=1,
            total_absent=0,
            total_late=0,
        )

        self.client.login(username='teacher_guard', password='testpass123')
        response = self.client.get(reverse('export_report_csv'), {
            'type': 'attendance',
            'date_from': timezone.now().date().strftime('%Y-%m-%d'),
            'date_to': timezone.now().date().strftime('%Y-%m-%d'),
        })

        self.assertEqual(response.status_code, 200)
        csv_text = response.content.decode('utf-8')
        self.assertIn('CSE401 - Algorithms', csv_text)
        self.assertNotIn('CSE402 - Compiler', csv_text)


class HodDepartmentBoundaryTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.dept_a = Department.objects.create(code='CSEA', name='CSE A', roll_code='11')
        self.dept_b = Department.objects.create(code='CSEB', name='CSE B', roll_code='12')

        self.hod_a = User.objects.create_user(
            username='hod_a',
            password='testpass123',
            role='hod',
            department=self.dept_a,
            full_name='HOD A',
        )

        self.batch_a = Batch.objects.create(department=self.dept_a, year=2026, code='26', is_active=True)

        self.teacher_b = User.objects.create_user(
            username='teacher_b',
            password='testpass123',
            role='teacher',
            department=self.dept_b,
            full_name='Teacher B',
        )

        self.batch_b = Batch.objects.create(department=self.dept_b, year=2026, code='26', is_active=True)

        self.subject_b = Subject.objects.create(
            code='B401',
            name='Networks',
            department=self.dept_b,
            semester=4,
            credit_hours=3,
            is_active=True,
        )
        SubjectTeacher.objects.create(teacher=self.teacher_b, subject=self.subject_b)

        self.session_b = Session.objects.create(
            subject=self.subject_b,
            teacher=self.teacher_b,
            department=self.dept_b,
            batch=self.batch_b,
            semester=4,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status='COMPLETED',
        )

        self.student_b = User.objects.create_user(
            username='student_b',
            password='testpass123',
            role='student',
            roll_no='261201',
            department=self.dept_b,
            batch=self.batch_b,
            batch_sequence=1,
            semester=4,
            full_name='Student B',
            is_active=True,
        )
        self.attendance_b = Attendance.objects.create(
            session=self.session_b,
            student=self.student_b,
            status=Attendance.Status.ABSENT,
        )
        self.request_b = AttendanceCorrectionRequest.objects.create(
            attendance=self.attendance_b,
            student=self.student_b,
            teacher=self.teacher_b,
            reason='Was present',
            status=AttendanceCorrectionRequest.Status.PENDING,
        )

        self.student_a = User.objects.create_user(
            username='student_a',
            password='testpass123',
            role='student',
            roll_no='261101',
            department=self.dept_a,
            batch=self.batch_a,
            batch_sequence=1,
            semester=6,
            full_name='Student A',
            is_active=True,
        )

    def test_hod_student_list_can_filter_by_batch(self):
        self.client.login(username='hod_a', password='testpass123')

        response = self.client.get(reverse('hod_students'), {'batch': self.batch_a.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student A')
        self.assertContains(response, '2026 (26)')
        self.assertNotContains(response, 'Student B')

    def test_hod_cannot_view_other_department_session_detail(self):
        self.client.login(username='hod_a', password='testpass123')

        response = self.client.get(reverse('session_detail', args=[self.session_b.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Access denied for other department session')

    def test_hod_cannot_export_other_department_session_csv(self):
        self.client.login(username='hod_a', password='testpass123')

        response = self.client.get(reverse('export_session_csv', args=[self.session_b.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Access denied for other department session')

    def test_hod_pending_requests_are_department_scoped(self):
        self.client.login(username='hod_a', password='testpass123')

        response = self.client.get(reverse('get_pending_correction_requests'))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['count'], 0)

    def test_hod_cannot_approve_other_department_request(self):
        self.client.login(username='hod_a', password='testpass123')

        response = self.client.post(
            reverse('approve_correction_request', args=[self.request_b.id]),
            data='{"corrected_status":"PRESENT","comment":"ok"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)


class StudentBatchScopedAttendanceStatsTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.dept = Department.objects.create(code='CSD', name='Computer Science Dept', roll_code='21')
        self.batch_a = Batch.objects.create(department=self.dept, year=2026, code='26', is_active=True)
        self.batch_b = Batch.objects.create(department=self.dept, year=2025, code='25', is_active=True)

        self.teacher = User.objects.create_user(
            username='teacher_stats',
            password='testpass123',
            role='teacher',
            department=self.dept,
        )
        self.student = User.objects.create_user(
            username='student_stats',
            password='testpass123',
            role='student',
            roll_no='262101',
            department=self.dept,
            semester=4,
            batch=self.batch_a,
            batch_sequence=1,
            is_active=True,
        )

        self.subject = Subject.objects.create(
            code='CSD401',
            name='Distributed Systems',
            department=self.dept,
            semester=4,
            credit_hours=3,
            is_active=True,
        )
        SubjectTeacher.objects.create(teacher=self.teacher, subject=self.subject)

        self.session_a = Session.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            department=self.dept,
            batch=self.batch_a,
            semester=4,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status='COMPLETED',
        )
        self.session_b = Session.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            department=self.dept,
            batch=self.batch_b,
            semester=4,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status='COMPLETED',
        )

        Attendance.objects.create(
            session=self.session_a,
            student=self.student,
            status=Attendance.Status.PRESENT,
        )

    def test_student_attendance_page_counts_only_students_batch_sessions(self):
        self.client.login(username='student_stats', password='testpass123')

        response = self.client.get(reverse('student_attendance'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_sessions'], 1)
        self.assertEqual(response.context['total_present'], 1)
        self.assertEqual(response.context['overall_percentage'], 100.0)


class SessionHistoryBatchFilterTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.dept = Department.objects.create(code='ME', name='Mechanical', roll_code='41')
        self.batch_2026 = Batch.objects.create(department=self.dept, year=2026, code='26', is_active=True)
        self.batch_2025 = Batch.objects.create(department=self.dept, year=2025, code='25', is_active=True)

        self.teacher = User.objects.create_user(
            username='teacher_history',
            password='testpass123',
            role='teacher',
            department=self.dept,
            full_name='Teacher History',
        )

        self.subject = Subject.objects.create(
            code='ME401',
            name='Thermodynamics',
            department=self.dept,
            semester=4,
            credit_hours=3,
            is_active=True,
        )
        SubjectTeacher.objects.create(teacher=self.teacher, subject=self.subject)

        self.session_2026 = Session.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            department=self.dept,
            batch=self.batch_2026,
            semester=4,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status='COMPLETED',
        )
        self.session_2025 = Session.objects.create(
            subject=self.subject,
            teacher=self.teacher,
            department=self.dept,
            batch=self.batch_2025,
            semester=4,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status='COMPLETED',
        )

    def test_session_history_can_filter_by_batch(self):
        self.client.login(username='teacher_history', password='testpass123')

        response = self.client.get(reverse('session_history'), {
            'batch': self.batch_2026.id,
        })

        self.assertEqual(response.status_code, 200)
        sessions = list(response.context['sessions'])
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].id, self.session_2026.id)
        self.assertIn(self.batch_2026, list(response.context['batches']))