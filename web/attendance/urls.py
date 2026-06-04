from django.urls import path
from . import views
from . import api
from . import reports


urlpatterns = [
    # Teacher
    path('my-subjects/', views.teacher_subjects, name='teacher_subjects'),
    path('start-session/<int:subject_id>/', views.start_session, name='start_session'),
    path('session/<int:session_id>/', views.session_detail, name='session_detail'),
    path('session/<int:session_id>/end/', views.end_session, name='end_session'),
    path('session/<int:session_id>/mark/<int:student_id>/<str:status>/',
         views.mark_manual, name='mark_manual'),
    path('session/<int:session_id>/export/', views.export_session_csv, name='export_session_csv'),
    path('session-history/', views.session_history, name='session_history'),

    # Student
    path('my-attendance/', views.student_attendance, name='student_attendance'),

    # HOD
    path('dept-overview/', views.hod_overview, name='hod_overview'),
    path('dept-students/', views.hod_students, name='hod_students'),

    # Reports
    path('reports/', reports.reports_page, name='reports_page'),
    path('reports/export/', reports.export_report_csv, name='export_report_csv'),

    # API — face recognition
    path('api/recognize/<int:session_id>/', api.recognize_frame, name='recognize_frame'),


    # Notification endpoints
    path('api/notifications/', views.get_notifications, name='get_notifications'),
    path('api/notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('api/notifications/read-all/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('api/notifications/unread-count/', views.get_unread_count, name='get_unread_count'),
    
    # Correction request endpoints (student)
    path('api/attendance/<int:attendance_id>/correction-form/', views.get_correction_request_form, name='get_correction_request_form'),
    path('api/attendance/<int:attendance_id>/submit-correction/', views.submit_correction_request, name='submit_correction_request'),
    path('api/correction-requests/my-requests/', views.get_student_correction_requests, name='get_student_correction_requests'),
    path('api/correction-requests/<int:request_id>/withdraw/', views.withdraw_correction_request, name='withdraw_correction_request'),
    
    # Correction request endpoints (teacher)
    path('api/correction-requests/pending/', views.get_pending_correction_requests, name='get_pending_correction_requests'),
    path('api/correction-requests/<int:request_id>/approve/', views.approve_correction_request, name='approve_correction_request'),
    path('api/correction-requests/<int:request_id>/reject/', views.reject_correction_request, name='reject_correction_request'),


    # Page views
    path('notifications/', views.all_notifications_page, name='all_notifications'),
    path('session/<int:session_id>/detail/', views.session_detail_with_correction, name='session_detail_with_correction'),
    path('corrections/teacher/', views.correction_requests_teacher_page, name='correction_requests_teacher'),
    path('corrections/my-requests/', views.my_correction_requests, name='my_correction_requests'),
]