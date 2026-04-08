"""
Reports — PDF + CSV generation with date range filters.
"""
import csv
import io
from datetime import datetime, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Count, Q
from .models import Session, Attendance
from academics.models import Department, Subject, SubjectTeacher
from accounts.models import CustomUser


@login_required
def reports_page(request):
    """Main reports page with date range selection."""
    user = request.user

    # Default: last 30 days
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if not date_from:
        date_from = (timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not date_to:
        date_to = timezone.now().strftime('%Y-%m-%d')

    context = {
        'date_from': date_from,
        'date_to': date_to,
    }

    if user.role == 'admin':
        context['departments'] = Department.objects.filter(is_active=True)
        context['report_type'] = 'admin'
    elif user.role == 'hod':
        context['department'] = user.department
        context['report_type'] = 'hod'
        context['subjects'] = Subject.objects.filter(
            department=user.department, is_active=True
        )
    elif user.role == 'teacher':
        context['report_type'] = 'teacher'
        context['assignments'] = SubjectTeacher.objects.filter(
            teacher=user
        ).select_related('subject')
    elif user.role == 'student':
        context['report_type'] = 'student'

    return render(request, 'attendance/reports.html', context)


@login_required
def export_report_csv(request):
    """Generate CSV report based on filters."""
    user = request.user
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    dept_id = request.GET.get('department', '')
    subject_id = request.GET.get('subject', '')
    report_type = request.GET.get('type', 'attendance')

    # Parse dates
    try:
        d_from = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else (timezone.now() - timedelta(days=30)).date()
        d_to = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else timezone.now().date()
    except ValueError:
        d_from = (timezone.now() - timedelta(days=30)).date()
        d_to = timezone.now().date()

    response = HttpResponse(content_type='text/csv')
    filename = f"attendance_report_{d_from}_{d_to}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)

    if report_type == 'student_summary' and user.role in ('admin', 'hod'):
        # Student summary report
        writer.writerow(['Roll No', 'Name', 'Department', 'Semester',
                         'Total Sessions', 'Present', 'Late', 'Absent', 'Attendance %'])

        students = CustomUser.objects.filter(role='student', is_active=True)
        if dept_id:
            students = students.filter(department_id=dept_id)

        for student in students.order_by('department__code', 'semester', 'roll_no'):
            total = Attendance.objects.filter(
                student=student,
                session__date__gte=d_from,
                session__date__lte=d_to,
                session__status='COMPLETED',
            ).count()

            present = Attendance.objects.filter(
                student=student, status='PRESENT',
                session__date__gte=d_from, session__date__lte=d_to,
                session__status='COMPLETED',
            ).count()

            late = Attendance.objects.filter(
                student=student, status='LATE',
                session__date__gte=d_from, session__date__lte=d_to,
                session__status='COMPLETED',
            ).count()

            absent = total - present - late
            pct = round(((present + late) / total) * 100, 1) if total > 0 else 0

            writer.writerow([
                student.roll_no, student.full_name,
                student.department.code if student.department else '-',
                student.semester or '-',
                total, present, late, max(absent, 0), pct,
            ])

    elif report_type == 'session_detail':
        # Session-by-session detail
        writer.writerow(['Date', 'Subject', 'Teacher', 'Department', 'Semester',
                         'Roll No', 'Student', 'Status', 'Time', 'Confidence', 'Method'])

        sessions = Session.objects.filter(
            date__gte=d_from, date__lte=d_to, status='COMPLETED'
        ).order_by('date', 'subject__code')

        if dept_id:
            sessions = sessions.filter(department_id=dept_id)
        if subject_id:
            sessions = sessions.filter(subject_id=subject_id)

        # Permission check
        if user.role == 'teacher':
            sessions = sessions.filter(teacher=user)
        elif user.role == 'hod':
            sessions = sessions.filter(department=user.department)

        for session in sessions:
            for record in session.records.select_related('student').order_by('student__roll_no'):
                writer.writerow([
                    session.date, session.subject.code, session.teacher.full_name,
                    session.department.code, session.semester,
                    record.student.roll_no, record.student.full_name,
                    record.status,
                    record.time_marked if record.time_marked else '',
                    f'{record.confidence:.3f}' if record.confidence else '',
                    record.get_marked_by_display(),
                ])

    elif report_type == 'my_attendance' and user.role == 'student':
        # Student's own report
        writer.writerow(['Date', 'Subject', 'Teacher', 'Status', 'Time', 'Method'])

        records = Attendance.objects.filter(
            student=user,
            session__date__gte=d_from,
            session__date__lte=d_to,
            session__status='COMPLETED',
        ).select_related('session__subject', 'session__teacher').order_by('session__date')

        for r in records:
            writer.writerow([
                r.session.date, r.session.subject.code,
                r.session.teacher.full_name, r.status,
                r.time_marked if r.time_marked else '',
                r.get_marked_by_display(),
            ])

    else:
        # Default: attendance summary
        writer.writerow(['Subject', 'Department', 'Semester', 'Total Sessions',
                         'Avg Present', 'Avg Absent', 'Avg Rate'])

        subjects = Subject.objects.filter(is_active=True)
        if dept_id:
            subjects = subjects.filter(department_id=dept_id)

        for subject in subjects:
            sessions = Session.objects.filter(
                subject=subject, status='COMPLETED',
                date__gte=d_from, date__lte=d_to,
            )
            total = sessions.count()
            if total == 0:
                continue

            avg_present = sum(s.total_present for s in sessions) / total
            avg_absent = sum(s.total_absent for s in sessions) / total
            avg_rate = sum(s.attendance_rate for s in sessions) / total

            writer.writerow([
                f'{subject.code} - {subject.name}',
                subject.department.code, subject.semester,
                total, round(avg_present, 1), round(avg_absent, 1),
                f'{round(avg_rate, 1)}%',
            ])

    return response