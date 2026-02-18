from django.db import models
from django.conf import settings
from django.utils import timezone


class Session(models.Model):
    """
    A single attendance session for a subject.
    Teacher starts → webcam runs → teacher ends → absent marked.
    """

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

    class Meta:
        unique_together = ['session', 'student']
        ordering = ['student__roll_no']

    def __str__(self):
        return f"{self.student.roll_no} — {self.get_status_display()} — {self.session}"