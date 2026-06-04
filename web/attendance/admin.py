from django.contrib import admin
from .models import Session, Attendance
from .models import Notification, AttendanceCorrectionRequest, NotificationPreference

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
    list_display = ('student', 'session', 'status', 'time_marked', 'marked_by')
    list_filter = ('status', 'marked_by', 'session__date')
    search_fields = ('student__roll_no', 'student__name')
    readonly_fields = ('created_at', 'updated_at')



@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__roll_no', 'user__name', 'title')
    readonly_fields = ('created_at', 'updated_at', 'read_at')
    
    fieldsets = (
        ('Recipient', {'fields': ('user',)}),
        ('Content', {'fields': ('notification_type', 'title', 'message')}),
        ('Related Objects', {'fields': ('session', 'attendance', 'correction_request')}),
        ('Status', {'fields': ('is_read', 'read_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(AttendanceCorrectionRequest)
class AttendanceCorrectionRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'get_subject', 'status', 'created_at', 'responded_at')
    list_filter = ('status', 'created_at', 'attendance__session__subject')
    search_fields = ('student__roll_no', 'student__name', 'reason')
    readonly_fields = ('created_at', 'updated_at', 'responded_at')
    
    fieldsets = (
        ('Request Info', {'fields': ('student', 'attendance', 'status')}),
        ('Student Request', {'fields': ('reason',)}),
        ('Teacher Response', {'fields': ('teacher', 'teacher_comment', 'corrected_status', 'responded_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    
    def get_subject(self, obj):
        return obj.attendance.session.subject.code
    get_subject.short_description = 'Subject'


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'notify_on_absence', 'notify_on_request_response')
    list_filter = ('notify_on_absence', 'notify_on_request_response')
    search_fields = ('user__roll_no', 'user__name')