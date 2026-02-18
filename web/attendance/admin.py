from django.contrib import admin
from .models import Session, Attendance


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        'subject', 'teacher', 'department', 'semester', 'date',
        'start_time', 'end_time', 'status',
        'total_present', 'total_absent', 'total_late', 'attendance_rate',
    )
    list_filter = ('status', 'department', 'semester', 'date')
    search_fields = ('subject__name', 'teacher__full_name')
    date_hierarchy = 'date'


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        'student', 'session', 'status', 'time_marked',
        'confidence', 'marked_by',
    )
    list_filter = ('status', 'marked_by', 'session__date', 'session__subject')
    search_fields = ('student__full_name', 'student__roll_no')