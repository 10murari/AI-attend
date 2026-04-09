from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta, datetime, time



class Session(models.Model):
    """
    A single attendance session for a subject.
    Teacher starts → webcam runs → teacher ends → absent marked.
    """
    notification_sent = models.BooleanField(
    default=False,
    help_text="Whether absence notifications have been sent"
    )

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    subject = models.ForeignKey(
        'academics.Subject',
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sessions_created',
        limit_choices_to={'role__in': ['teacher', 'hod']},
    )
    department = models.ForeignKey(
        'academics.Department',
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    batch = models.ForeignKey(
        'academics.Batch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessions',
    )
    semester = models.PositiveIntegerField()
    date = models.DateField(default=timezone.now)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    total_present = models.PositiveIntegerField(default=0)
    total_absent = models.PositiveIntegerField(default=0)
    total_late = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-start_time']

    def __str__(self):
        return f"{self.subject.code} — {self.date} ({self.get_status_display()})"

    @property
    def total_students(self):
        return self.total_present + self.total_absent + self.total_late

    @property
    def attendance_rate(self):
        total = self.total_students
        if total == 0:
            return 0
        return round(((self.total_present + self.total_late) / total) * 100, 1)

    def send_absence_notifications(self):
        """Send notifications to all absent students"""
        if self.notification_sent:
            return

        absent_records = self.records.filter(status=Attendance.Status.ABSENT)

        for attendance in absent_records:
            Notification.create_absent_notification(attendance)

        self.notification_sent = True
        self.save()
    


class Attendance(models.Model):
    """Individual attendance record for one student in one session."""

    class Status(models.TextChoices):
        PRESENT = 'PRESENT', 'Present'
        ABSENT = 'ABSENT', 'Absent'
        LATE = 'LATE', 'Late'

    class MarkedBy(models.TextChoices):
        AUTO = 'auto', 'Auto (Face Recognition)'
        MANUAL = 'manual', 'Manual (Teacher)'

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='records',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attendance_records',
        limit_choices_to={'role': 'student'},
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ABSENT,
    )
    time_marked = models.TimeField(null=True, blank=True)
    confidence = models.FloatField(
        null=True, blank=True,
        help_text="Face recognition confidence (0.0 - 1.0)"
    )
    marked_by = models.CharField(
        max_length=10,
        choices=MarkedBy.choices,
        default=MarkedBy.AUTO,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['session', 'student']
        ordering = ['student__roll_no']

    def __str__(self):
        return f"{self.student.roll_no} — {self.get_status_display()} — {self.session}"
    



# ============================================================
# NOTIFICATION MODEL
# ============================================================

class Notification(models.Model):
    """
    In-app notifications for students about attendance.
    
    Types:
    - ABSENT: Student marked absent in a session
    - REQUEST_SUBMITTED: Correction request submitted
    - REQUEST_APPROVED: Correction request approved
    - REQUEST_REJECTED: Correction request rejected
    """
    
    class NotificationType(models.TextChoices):
        ABSENT = 'absent', 'Marked Absent'
        REQUEST_SUBMITTED = 'request_submitted', 'Correction Request Submitted'
        REQUEST_APPROVED = 'request_approved', 'Correction Request Approved'
        REQUEST_REJECTED = 'request_rejected', 'Correction Request Rejected'
    
    # Core fields
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Related objects
    session = models.ForeignKey(
        'attendance.Session',
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True
    )
    attendance = models.ForeignKey(
        'attendance.Attendance',
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True
    )
    correction_request = models.ForeignKey(
        'attendance.AttendanceCorrectionRequest',
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True
    )
    
    # Status tracking
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.user.roll_no} - {self.get_notification_type_display()}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()
    
    @staticmethod
    def create_absent_notification(attendance):
        """Create absence notification for student"""
        return Notification.objects.create(
            user=attendance.student,
            notification_type=Notification.NotificationType.ABSENT,
            title=f"Marked Absent - {attendance.session.subject.code}",
            message=f"You were marked absent in {attendance.session.subject.name} on {attendance.session.date}. You can request for correction within 48 hours.",
            session=attendance.session,
            attendance=attendance
        )


# ============================================================
# ATTENDANCE CORRECTION REQUEST MODEL
# ============================================================

class AttendanceCorrectionRequest(models.Model):
    """
    Request from student to teacher for attendance correction.
    
    Workflow:
    PENDING → APPROVED/REJECTED
    
    Rules:
    - One request per session per student
    - Request must be made within REQUEST_WINDOW (e.g., 48 hours)
    - After approval, teacher can modify attendance status
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        WITHDRAWN = 'withdrawn', 'Withdrawn'
    
    # Core relationships
    attendance = models.OneToOneField(
        'attendance.Attendance',
        on_delete=models.CASCADE,
        related_name='correction_request'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='correction_requests',
        limit_choices_to={'role': 'student'}
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='correction_requests_received',
        limit_choices_to={'role__in': ['teacher', 'hod']},
        null=True,
        blank=True
    )
    
    # Request details
    reason = models.TextField(
        help_text="Why are you requesting attendance correction?"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # Teacher's response
    teacher_comment = models.TextField(
        blank=True,
        help_text="Teacher's comment/reason for approval/rejection"
    )
    corrected_status = models.CharField(
        max_length=10,
        choices=Attendance.Status.choices,
        null=True,
        blank=True,
        help_text="New attendance status after correction"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['attendance', 'student']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['teacher', 'status']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.student.roll_no} - {self.attendance.session.subject.code} - {self.get_status_display()}"
    
    def clean(self):
        """Validation rules"""
        from django.core.exceptions import ValidationError
        
        # Rule 1: Check if request is within REQUEST_WINDOW
        now = timezone.now()
        request_window = timedelta(hours=getattr(settings, 'ATTENDANCE_REQUEST_WINDOW', 48))
        session_end = timezone.make_aware(
            datetime.combine(self.attendance.session.date, self.attendance.session.end_time or time(23, 59, 59))
        )
        
        if now > session_end + request_window:
            raise ValidationError(
                f"Request window has closed. You can only request within {getattr(settings, 'ATTENDANCE_REQUEST_WINDOW', 48)} hours of session end."
            )
        
        # Rule 2: Only absent students can request
        if self.attendance.status != Attendance.Status.ABSENT:
            raise ValidationError("You can only request correction for absences.")
        
        # Rule 3: Only one request per session
        existing = AttendanceCorrectionRequest.objects.filter(
            student=self.student,
            attendance__session=self.attendance.session
        ).exclude(id=self.id)
        
        if existing.exists():
            raise ValidationError("You already have a correction request for this session.")
    
    def approve(self, teacher, corrected_status, comment=""):
        """Approve correction request and update attendance"""
        self.status = self.Status.APPROVED
        self.teacher = teacher
        self.corrected_status = corrected_status
        self.teacher_comment = comment
        self.responded_at = timezone.now()
        self.save()
        
        # Update attendance record
        self.attendance.status = corrected_status
        self.attendance.marked_by = 'manual'  # Mark as manually corrected
        self.attendance.save()
        
        # Create notification for student
        Notification.objects.create(
            user=self.student,
            notification_type=Notification.NotificationType.REQUEST_APPROVED,
            title="Attendance Correction Approved",
            message=f"Your correction request for {self.attendance.session.subject.code} has been approved. Your status is now {corrected_status}.",
            session=self.attendance.session,
            correction_request=self
        )
    
    def reject(self, teacher, comment=""):
        """Reject correction request"""
        self.status = self.Status.REJECTED
        self.teacher = teacher
        self.teacher_comment = comment
        self.responded_at = timezone.now()
        self.save()
        
        # Create notification for student
        Notification.objects.create(
            user=self.student,
            notification_type=Notification.NotificationType.REQUEST_REJECTED,
            title="Attendance Correction Rejected",
            message=f"Your correction request for {self.attendance.session.subject.code} has been rejected. Reason: {comment}",
            session=self.attendance.session,
            correction_request=self
        )
    
    def withdraw(self):
        """Student withdraws their request"""
        if self.status != self.Status.PENDING:
            raise ValidationError("Can only withdraw pending requests.")
        
        self.status = self.Status.WITHDRAWN
        self.save()
    
    @property
    def is_request_window_open(self):
        """Check if request is still within allowed window"""
        now = timezone.now()
        request_window = timedelta(hours=getattr(settings, 'ATTENDANCE_REQUEST_WINDOW', 48))
        session_end = timezone.make_aware(
            datetime.combine(
                self.attendance.session.date,
                self.attendance.session.end_time or time(23, 59, 59)
            )
        )
        return now <= session_end + request_window


# ============================================================
# NOTIFICATION SETTINGS MODEL
# ============================================================

class NotificationPreference(models.Model):
    """User notification preferences"""
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preference'
    )
    
    # Notification types to receive
    notify_on_absence = models.BooleanField(default=True)
    notify_on_request_response = models.BooleanField(default=True)
    notify_on_request_received = models.BooleanField(default=True)
    
    # Email notifications (optional)
    email_on_absence = models.BooleanField(default=False)
    email_on_request_response = models.BooleanField(default=False)
    
    # Quiet hours (optional)
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True)  # e.g., 22:00
    quiet_hours_end = models.TimeField(null=True, blank=True)    # e.g., 07:00
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Notification Preferences - {self.user.roll_no}"
