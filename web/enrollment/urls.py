from django.urls import path
from . import views

urlpatterns = [
    path('', views.enroll_page, name='enroll_page'),
    path('process/', views.enroll_process, name='enroll_process'),
    path('delete/<int:student_id>/', views.enroll_delete, name='enroll_delete'),
]