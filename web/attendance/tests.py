from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from .models import Attendance, AttendanceCorrectionRequest, Notification, Session
from academics.models import Department, Subject, SubjectTeacher

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