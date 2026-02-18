from django.contrib import admin
from .models import Department, Subject, SubjectTeacher


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'hod', 'is_active', 'student_count', 'teacher_count')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'department', 'semester', 'credit_hours', 'teacher', 'is_active')
    list_filter = ('department', 'semester', 'is_active')
    search_fields = ('name', 'code')


@admin.register(SubjectTeacher)
class SubjectTeacherAdmin(admin.ModelAdmin):
    list_display = ('subject', 'teacher', 'assigned_at')
    list_filter = ('subject__department', 'subject__semester')
    search_fields = ('teacher__full_name', 'subject__name')