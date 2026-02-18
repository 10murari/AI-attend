from django.db import models
from django.conf import settings


class Department(models.Model):
    """College department (e.g., Computer Engineering)."""
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(
        max_length=10, unique=True,
        help_text="Short code, e.g., COMP, CIVIL"
    )
    hod = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='headed_department',
        limit_choices_to={'role': 'hod'},
        help_text="Head of Department"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def student_count(self):
        return self.users.filter(role='student', is_active=True).count()

    @property
    def teacher_count(self):
        return self.users.filter(role='teacher', is_active=True).count()


class Subject(models.Model):
    """Subject/course offered in a department for a specific semester."""
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='subjects',
    )
    semester = models.PositiveIntegerField(
        help_text="Semester number (1-8)"
    )
    credit_hours = models.PositiveIntegerField(default=3)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['department', 'semester', 'name']
        unique_together = ['department', 'code']

    def __str__(self):
        return f"{self.code} — {self.name} (Sem {self.semester})"

    @property
    def teacher(self):
        """Get assigned teacher (one teacher per subject)."""
        assignment = self.teacher_assignments.first()
        return assignment.teacher if assignment else None


class SubjectTeacher(models.Model):
    """Links one teacher to one subject."""
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subject_assignments',
        limit_choices_to={'role__in': ['teacher', 'hod']},
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='teacher_assignments',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['subject']  # One teacher per subject
        ordering = ['subject']

    def __str__(self):
        return f"{self.teacher.full_name} → {self.subject.code}"