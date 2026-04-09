from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """
    Extended user with role-based access.

    Roles:
        admin   — college-level administrator, full access
        hod     — head of department, department-level access
        teacher — subject teacher, subject-level access
        student — enrolled student, self-only access
    """

    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        HOD = 'hod', 'HOD'
        TEACHER = 'teacher', 'Teacher'
        STUDENT = 'student', 'Student'

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STUDENT,
    )
    full_name = models.CharField(max_length=150, blank=True)
    department = models.ForeignKey(
        'academics.Department',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='users',
    )
    # Student-specific fields
    roll_no = models.CharField(
        max_length=20, unique=True, null=True, blank=True,
        help_text="Unique roll number for students"
    )
    batch = models.ForeignKey(
        'academics.Batch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        help_text="Student intake batch/cohort",
    )
    batch_sequence = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Sequence number within selected batch and department",
    )
    semester = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Current semester (1-8) for students"
    )
    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['role', 'full_name']
        constraints = [
            models.UniqueConstraint(
                fields=['batch', 'batch_sequence'],
                name='unique_batch_student_sequence',
            )
        ]

    def __str__(self):
        if self.role == self.Role.STUDENT and self.roll_no:
            return f"{self.roll_no} — {self.full_name}"
        return f"{self.full_name} ({self.get_role_display()})"

    @property
    def is_admin_user(self):
        return self.role == self.Role.ADMIN

    @property
    def is_hod(self):
        return self.role == self.Role.HOD

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT