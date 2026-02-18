import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Count, Q
from .models import Session, Attendance
from academics.models import SubjectTeacher, Subject
from accounts.models import CustomUser


def teacher_required(view_func):
    """Decorator: teacher or HOD only."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role not in ('teacher', 'hod'):
            messages.error(request, 'Teacher access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ==============================================================
# TEACHER: MY SUBJECTS
# ==============================================================

@login_required
@teacher_required
def teacher_subjects(request):
    assignments = SubjectTeacher.objects.filter(
        teacher=request.user
    ).select_related('subject', 'subject__department')

    subjects_data = []
    for a in assignments:
        subject = a.subject
        total_sessions = Session.objects.filter(
            subject=subject, status='COMPLETED'
        ).count()

        active_session = Session.objects.filter(
            subject=subject, teacher=request.user, status='ACTIVE'
        ).first()

        student_count = CustomUser.objects.filter(
            role='student', department=subject.department,
            semester=subject.semester, is_active=True,
        ).count()

        subjects_data.append({
            'subject': subject,
            'total_sessions': total_sessions,
            'active_session': active_session,
            'student_count': student_count,
        })

    return render(request, 'attendance/teacher_subjects.html', {
        'subjects_data': subjects_data,
    })


# ==============================================================
# TEACHER: START SESSION
# ==============================================================

@login_required
@teacher_required
def start_session(request, subject_id):
    subject = get_object_or_404(Subject, pk=subject_id, is_active=True)

    # Verify teacher is assigned to this subject
    if not SubjectTeacher.objects.filter(teacher=request.user, subject=subject).exists():
        messages.error(request, "You're not assigned to this subject.")
        return redirect('teacher_subjects')

    # Check no active session already
    active = Session.objects.filter(subject=subject, teacher=request.user, status='ACTIVE').first()
    if active:
        messages.warning(request, f'Session already active for {subject.code}.')
        return redirect('session_detail', session_id=active.id)

    if request.method == 'POST':
        session = Session.objects.create(
            subject=subject,
            teacher=request.user,
            department=subject.department,
            semester=subject.semester,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            status='ACTIVE',
        )
        messages.success(request, f'Session started for {subject.name}.')
        return redirect('session_detail', session_id=session.id)

    student_count = CustomUser.objects.filter(
        role='student', department=subject.department,
        semester=subject.semester, is_active=True,
    ).count()

    return render(request, 'attendance/start_session.html', {
        'subject': subject,
        'student_count': student_count,
    })


# ==============================================================
# TEACHER: SESSION DETAIL (live attendance view)
# ==============================================================

@login_required
@teacher_required
def session_detail(request, session_id):
    session = get_object_or_404(Session, pk=session_id)

    if session.teacher != request.user and request.user.role != 'hod':
        messages.error(request, 'Not your session.')
        return redirect('teacher_subjects')

    # Get all students for this subject
    students = CustomUser.objects.filter(
        role='student', department=session.department,
        semester=session.semester, is_active=True,
    ).order_by('roll_no')

    # Get existing attendance records
    records = {r.student_id: r for r in session.records.all()}

    student_data = []
    for student in students:
        record = records.get(student.id)
        student_data.append({
            'student': student,
            'status': record.status if record else 'NOT_MARKED',
            'time_marked': record.time_marked if record else None,
            'confidence': record.confidence if record else None,
            'marked_by': record.marked_by if record else None,
        })

    present_count = sum(1 for s in student_data if s['status'] == 'PRESENT')
    late_count = sum(1 for s in student_data if s['status'] == 'LATE')
    absent_count = sum(1 for s in student_data if s['status'] in ('ABSENT', 'NOT_MARKED'))

    return render(request, 'attendance/session_detail.html', {
        'session': session,
        'student_data': student_data,
        'present_count': present_count,
        'late_count': late_count,
        'absent_count': absent_count,
        'total_count': len(student_data),
    })


# ==============================================================
# TEACHER: MARK ATTENDANCE (manual toggle)
# ==============================================================

@login_required
@teacher_required
def mark_manual(request, session_id, student_id, status):
    session = get_object_or_404(Session, pk=session_id, teacher=request.user)
    student = get_object_or_404(CustomUser, pk=student_id, role='student')

    if session.status != 'ACTIVE':
        messages.error(request, 'Session is not active.')
        return redirect('session_detail', session_id=session.id)

    record, created = Attendance.objects.update_or_create(
        session=session,
        student=student,
        defaults={
            'status': status.upper(),
            'time_marked': timezone.now().time(),
            'marked_by': 'manual',
        }
    )
    return redirect('session_detail', session_id=session.id)


# ==============================================================
# TEACHER: END SESSION
# ==============================================================

@login_required
@teacher_required
def end_session(request, session_id):
    session = get_object_or_404(Session, pk=session_id, teacher=request.user)

    if request.method == 'POST':
        # Mark all unmarked students as ABSENT
        students = CustomUser.objects.filter(
            role='student', department=session.department,
            semester=session.semester, is_active=True,
        )

        marked_ids = set(session.records.values_list('student_id', flat=True))
        absent_count = 0

        for student in students:
            if student.id not in marked_ids:
                Attendance.objects.create(
                    session=session,
                    student=student,
                    status='ABSENT',
                    marked_by='auto',
                )
                absent_count += 1

        # Update session
        session.status = 'COMPLETED'
        session.end_time = timezone.now().time()
        session.total_present = session.records.filter(status='PRESENT').count()
        session.total_late = session.records.filter(status='LATE').count()
        session.total_absent = session.records.filter(status='ABSENT').count()
        session.save()

        messages.success(request,
            f'Session ended. Present: {session.total_present}, '
            f'Late: {session.total_late}, Absent: {session.total_absent}')
        return redirect('session_detail', session_id=session.id)

    return redirect('session_detail', session_id=session.id)


# ==============================================================
# TEACHER: SESSION HISTORY
# ==============================================================
@login_required
@teacher_required
def session_history(request):
    sessions = Session.objects.filter(
        teacher=request.user
    ).select_related('subject', 'department').order_by('-date', '-start_time')

    # Filter by subject if provided
    subject_id = request.GET.get('subject')
    if subject_id:
        sessions = sessions.filter(subject_id=subject_id)

    # Get teacher's subjects for filter dropdown
    assignments = SubjectTeacher.objects.filter(
        teacher=request.user
    ).select_related('subject')

    return render(request, 'attendance/session_history.html', {
        'sessions': sessions,
        'assignments': assignments,
        'selected_subject': subject_id,
    })
# ==============================================================
# TEACHER: EXPORT CSV
# ==============================================================

@login_required
@teacher_required
def export_session_csv(request, session_id):
    session = get_object_or_404(Session, pk=session_id)

    if session.teacher != request.user and request.user.role not in ('admin', 'hod'):
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    response = HttpResponse(content_type='text/csv')
    filename = f"attendance_{session.subject.code}_{session.date}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Date', 'Subject', 'Roll No', 'Name', 'Status',
        'Time Marked', 'Confidence', 'Marked By'
    ])

    records = session.records.select_related('student').order_by('student__roll_no')
    for r in records:
        writer.writerow([
            session.date, session.subject.code,
            r.student.roll_no, r.student.full_name,
            r.status,
            r.time_marked if r.time_marked else '',
            f'{r.confidence:.3f}' if r.confidence else '',
            r.get_marked_by_display(),
        ])

    return response


# ==============================================================
# STUDENT: MY ATTENDANCE
# ==============================================================

@login_required
def student_attendance(request):
    user = request.user
    if user.role != 'student':
        messages.error(request, 'Student access only.')
        return redirect('dashboard')

    subjects = Subject.objects.filter(
        department=user.department,
        semester=user.semester,
        is_active=True,
    )

    subject_stats = []
    for subject in subjects:
        total = Session.objects.filter(subject=subject, status='COMPLETED').count()
        present = Attendance.objects.filter(
            session__subject=subject, student=user, status='PRESENT'
        ).count()
        late = Attendance.objects.filter(
            session__subject=subject, student=user, status='LATE'
        ).count()
        absent = total - present - late
        pct = round(((present + late) / total) * 100, 1) if total > 0 else 0

        teacher_assign = SubjectTeacher.objects.filter(subject=subject).first()

        subject_stats.append({
            'subject': subject,
            'teacher': teacher_assign.teacher.full_name if teacher_assign else 'N/A',
            'total': total, 'present': present, 'late': late,
            'absent': max(absent, 0), 'percentage': pct,
        })

    total_all = sum(s['total'] for s in subject_stats)
    present_all = sum(s['present'] + s['late'] for s in subject_stats)
    overall = round((present_all / total_all) * 100, 1) if total_all > 0 else 0

    return render(request, 'attendance/student_attendance.html', {
        'subject_stats': subject_stats,
        'overall_percentage': overall,
        'total_sessions': total_all,
        'total_present': present_all,
    })


# ==============================================================
# HOD: DEPARTMENT OVERVIEW
# ==============================================================

@login_required
def hod_overview(request):
    user = request.user
    if user.role != 'hod':
        messages.error(request, 'HOD access only.')
        return redirect('dashboard')

    dept = user.department
    subjects = Subject.objects.filter(department=dept, is_active=True)
    today = timezone.now().date()

    subject_data = []
    for subject in subjects:
        total_sessions = Session.objects.filter(subject=subject, status='COMPLETED').count()
        today_session = Session.objects.filter(subject=subject, date=today).first()
        teacher_assign = SubjectTeacher.objects.filter(subject=subject).first()

        subject_data.append({
            'subject': subject,
            'teacher': teacher_assign.teacher.full_name if teacher_assign else 'Not Assigned',
            'total_sessions': total_sessions,
            'today_session': today_session,
        })

    return render(request, 'attendance/hod_overview.html', {
        'department': dept,
        'subject_data': subject_data,
        'total_students': CustomUser.objects.filter(role='student', department=dept, is_active=True).count(),
        'total_teachers': CustomUser.objects.filter(role__in=['teacher', 'hod'], department=dept, is_active=True).count(),
        'today_sessions': Session.objects.filter(department=dept, date=today).count(),
    })


@login_required
def hod_students(request):
    user = request.user
    if user.role != 'hod':
        messages.error(request, 'HOD access only.')
        return redirect('dashboard')

    dept = user.department
    students = CustomUser.objects.filter(
        role='student', department=dept, is_active=True
    ).order_by('semester', 'roll_no')

    student_data = []
    for student in students:
        total = Attendance.objects.filter(student=student).count()
        present = Attendance.objects.filter(student=student, status__in=['PRESENT', 'LATE']).count()
        pct = round((present / total) * 100, 1) if total > 0 else 0

        student_data.append({
            'student': student,
            'total': total,
            'present': present,
            'percentage': pct,
        })

    return render(request, 'attendance/hod_students.html', {
        'department': dept,
        'student_data': student_data,
    })