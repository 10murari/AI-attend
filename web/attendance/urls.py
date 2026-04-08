from django.urls import path
from . import views
from . import api
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
]