import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Count, Q
from .models import Session, Attendance, Notification, AttendanceCorrectionRequest
from academics.models import Batch, SubjectTeacher, Subject
from accounts.models import CustomUser

from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_protect
import json

from datetime import datetime, timedelta, time
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden


def teacher_required(view_func):
    """Decorator: teacher or HOD only."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role not in ('teacher', 'hod'):
            messages.error(request, 'Teacher access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def current_local_time():
    return timezone.localtime(timezone.now()).time().replace(microsecond=0)


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

        student_qs = CustomUser.objects.filter(
            role='student', department=subject.department,
            semester=subject.semester, is_active=True,
        )
        student_count = student_qs.count()
        batch_counts = list(
            student_qs.values('batch__year')
            .annotate(total=Count('id'))
            .order_by('-batch__year')
        )

        subjects_data.append({
            'subject': subject,
            'total_sessions': total_sessions,
            'active_session': active_session,
            'student_count': student_count,
            'batch_counts': batch_counts,
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
    available_batches = Batch.objects.filter(
        department=subject.department,
        is_active=True,
    ).order_by('-year')

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
        batch_id = request.POST.get('batch')
        selected_batch = available_batches.filter(pk=batch_id).first()
        if not selected_batch:
            messages.error(request, 'Please select a valid batch before starting session.')
            return redirect('start_session', subject_id=subject.id)

        session = Session.objects.create(
            subject=subject,
            teacher=request.user,
            department=subject.department,
            batch=selected_batch,
            semester=subject.semester,
            date=timezone.now().date(),
            start_time=current_local_time(),
            status='ACTIVE',
        )
        messages.success(request, f'Session started for {subject.name} (Batch {selected_batch.year}).')
        return redirect('session_detail', session_id=session.id)

    selected_batch = available_batches.first()
    if selected_batch:
        student_count = CustomUser.objects.filter(
            role='student', department=subject.department,
            semester=subject.semester, batch=selected_batch, is_active=True,
        ).count()
    else:
        student_count = 0

    return render(request, 'attendance/start_session.html', {
        'subject': subject,
        'student_count': student_count,
        'available_batches': available_batches,
        'selected_batch': selected_batch,
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

    if request.user.role == 'hod' and session.department_id != request.user.department_id:
        messages.error(request, 'Access denied for other department session.')
        return redirect('teacher_subjects')

    # Get all students for this subject
    students = CustomUser.objects.filter(
        role='student', department=session.department,
        semester=session.semester, is_active=True,
    )
    if session.batch_id:
        students = students.filter(batch_id=session.batch_id)
    students = students.order_by('roll_no')

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

    if (
        student.department_id != session.department_id
        or student.semester != session.semester
        or (session.batch_id and student.batch_id != session.batch_id)
    ):
        messages.error(request, 'Selected student does not belong to this session cohort.')
        return redirect('session_detail', session_id=session.id)

    record, created = Attendance.objects.update_or_create(
        session=session,
        student=student,
        defaults={
            'status': status.upper(),
            'time_marked': current_local_time(),
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
        if session.batch_id:
            students = students.filter(batch_id=session.batch_id)

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
        session.end_time = current_local_time()
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
    ).select_related('subject', 'department', 'batch').order_by('-date', '-start_time')

    # Filter by subject if provided
    subject_id = request.GET.get('subject')
    batch_id = request.GET.get('batch')
    if subject_id:
        sessions = sessions.filter(subject_id=subject_id)
    if batch_id:
        sessions = sessions.filter(batch_id=batch_id)

    # Get teacher's subjects for filter dropdown
    assignments = SubjectTeacher.objects.filter(
        teacher=request.user
    ).select_related('subject')

    department_ids = assignments.values_list('subject__department_id', flat=True).distinct()
    batches = Batch.objects.filter(
        department_id__in=department_ids,
        is_active=True,
    ).select_related('department').order_by('department__code', '-year')

    return render(request, 'attendance/session_history.html', {
        'sessions': sessions,
        'assignments': assignments,
        'selected_subject': subject_id,
        'batches': batches,
        'selected_batch': batch_id,
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

    if request.user.role == 'hod' and session.department_id != request.user.department_id:
        messages.error(request, 'Access denied for other department session.')
        return redirect('teacher_subjects')

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

    session_filters = {
        'status': 'COMPLETED',
    }
    if user.batch_id:
        session_filters['batch_id'] = user.batch_id
    else:
        session_filters['batch__isnull'] = True

    subject_stats = []
    for subject in subjects:
        total = Session.objects.filter(subject=subject, **session_filters).count()
        present = Attendance.objects.filter(
            session__subject=subject,
            session__status='COMPLETED',
            student=user,
            status='PRESENT'
        ).count()
        late = Attendance.objects.filter(
            session__subject=subject,
            session__status='COMPLETED',
            student=user,
            status='LATE'
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



# ============================================================
# NOTIFICATION VIEWS
# ============================================================

@login_required
def get_notifications(request):
    """Get user's notifications with filtering"""
    user = request.user
    
    # Query parameters
    unread_only = request.GET.get('unread_only', 'false').lower() == 'true'
    notification_type = request.GET.get('type', '')
    limit = int(request.GET.get('limit', 20))
    
    # Build query
    query = Notification.objects.filter(user=user)
    
    if unread_only:
        query = query.filter(is_read=False)
    
    if notification_type:
        query = query.filter(notification_type=notification_type)
    
    notifications = query[:limit]
    
    return JsonResponse({
        'success': True,
        'count': query.count(),
        'unread_count': Notification.objects.filter(
            user=user,
            is_read=False
        ).count(),
        'notifications': [
            {
                'id': n.id,
                'type': n.notification_type,
                'title': n.title,
                'message': n.message,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
                'session_subject': n.session.subject.code if n.session else None,
                'session_id': n.session_id,
                'correction_request_id': n.correction_request_id,
            }
            for n in notifications
        ]
    })


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """Mark single notification as read"""
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user
    )
    notification.mark_as_read()
    
    return JsonResponse({'success': True})


@login_required
@require_POST
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    Notification.objects.filter(
        user=request.user,
        is_read=False
    ).update(is_read=True, read_at=timezone.now())
    
    return JsonResponse({'success': True})


@login_required
def get_unread_count(request):
    """Get unread notification count (for badge)"""
    count = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).count()
    
    return JsonResponse({'unread_count': count})


# ============================================================
# ATTENDANCE CORRECTION REQUEST VIEWS
# ============================================================

@login_required
def get_correction_request_form(request, attendance_id):
    """Get form data for creating correction request"""
    attendance = get_object_or_404(
        Attendance,
        id=attendance_id,
        student=request.user
    )
    
    # Check if student already has a request for this session
    existing_request = AttendanceCorrectionRequest.objects.filter(
        student=request.user,
        attendance__session=attendance.session
    ).first()
    
    # Check if request window is open
    now = timezone.now()
    request_window = timedelta(hours=getattr(settings, 'ATTENDANCE_REQUEST_WINDOW', 48))
    session_end = timezone.make_aware(
        datetime.combine(
            attendance.session.date,
            attendance.session.end_time or time(23, 59, 59)
        )
    )
    
    window_open = now <= session_end + request_window
    time_remaining = (session_end + request_window - now).total_seconds() / 3600  # hours
    
    return JsonResponse({
        'success': True,
        'attendance': {
            'id': attendance.id,
            'status': attendance.status,
            'session': {
                'id': attendance.session.id,
                'subject': attendance.session.subject.code,
                'date': attendance.session.date.isoformat(),
            }
        },
        'existing_request': {
            'id': existing_request.id,
            'status': existing_request.status,
        } if existing_request else None,
        'request_window': {
            'open': window_open,
            'hours_remaining': round(time_remaining, 1) if window_open else 0,
            'deadline': (session_end + request_window).isoformat(),
        }
    })


@login_required
@require_POST
def submit_correction_request(request, attendance_id):
    """Submit attendance correction request"""
    try:
        data = json.loads(request.body)
        reason = data.get('reason', '').strip()
        
        if not reason:
            return JsonResponse({
                'success': False,
                'error': 'Reason is required'
            }, status=400)
        
        attendance = get_object_or_404(
            Attendance,
            id=attendance_id,
            student=request.user
        )
        
        # Validation
        if attendance.status != Attendance.Status.ABSENT:
            return JsonResponse({
                'success': False,
                'error': 'You can only request correction for absences'
            }, status=400)
        
        # Check if already has a request for this session
        if AttendanceCorrectionRequest.objects.filter(
            student=request.user,
            attendance__session=attendance.session
        ).exists():
            return JsonResponse({
                'success': False,
                'error': 'You already have a correction request for this session'
            }, status=400)
        
        # Create request (will validate window in clean())
        correction_request = AttendanceCorrectionRequest(
            attendance=attendance,
            student=request.user,
            reason=reason,
            teacher=attendance.session.teacher  # Assign to session teacher
        )
        
        try:
            correction_request.full_clean()
            correction_request.save()
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'error': str(e.message)
            }, status=400)
        
        # Create notification for student
        Notification.objects.create(
            user=request.user,
            notification_type=Notification.NotificationType.REQUEST_SUBMITTED,
            title="Correction Request Submitted",
            message=f"Your correction request for {attendance.session.subject.code} has been submitted to your teacher.",
            session=attendance.session,
            correction_request=correction_request
        )

        if correction_request.teacher and correction_request.teacher != request.user:
            Notification.objects.create(
                user=correction_request.teacher,
                notification_type=Notification.NotificationType.REQUEST_SUBMITTED,
                title="New Correction Request",
                message=f"{request.user.full_name or request.user.username} submitted a correction request for {attendance.session.subject.code}.",
                session=attendance.session,
                correction_request=correction_request
            )
        
        return JsonResponse({
            'success': True,
            'request_id': correction_request.id,
            'message': 'Correction request submitted successfully'
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def get_student_correction_requests(request):
    """Get student's correction requests"""
    status_filter = request.GET.get('status', '')
    
    query = AttendanceCorrectionRequest.objects.filter(
        student=request.user
    ).select_related('attendance__session__subject', 'teacher')
    
    if status_filter:
        query = query.filter(status=status_filter)
    
    requests = query.order_by('-created_at')
    
    return JsonResponse({
        'success': True,
        'requests': [
            {
                'id': req.id,
                'session': {
                    'id': req.attendance.session.id,
                    'subject': req.attendance.session.subject.code,
                    'date': req.attendance.session.date.isoformat(),
                },
                'reason': req.reason,
                'status': req.status,
                'teacher': {
                    'name': req.teacher.full_name if req.teacher else 'Pending',
                    'comment': req.teacher_comment,
                } if req.teacher else None,
                'corrected_status': req.corrected_status,
                'created_at': req.created_at.isoformat(),
                'responded_at': req.responded_at.isoformat() if req.responded_at else None,
            }
            for req in requests
        ]
    })


@login_required
@require_POST
def withdraw_correction_request(request, request_id):
    """Student withdraws their correction request"""
    correction_request = get_object_or_404(
        AttendanceCorrectionRequest,
        id=request_id,
        student=request.user
    )
    
    if correction_request.status != AttendanceCorrectionRequest.Status.PENDING:
        return JsonResponse({
            'success': False,
            'error': f'Cannot withdraw {correction_request.status} request'
        }, status=400)
    
    correction_request.withdraw()
    
    return JsonResponse({'success': True})


# ============================================================
# TEACHER VIEWS (FOR REQUEST APPROVAL)
# ============================================================

@login_required
def get_pending_correction_requests(request):
    """Get pending correction requests for teacher"""
    if request.user.role not in ['teacher', 'hod']:
        return JsonResponse({
            'success': False,
            'error': 'Only teachers can view requests'
        }, status=403)
    
    # Filter by teacher or HOD viewing all
    if request.user.role == 'teacher':
        query = AttendanceCorrectionRequest.objects.filter(
            teacher=request.user,
            status=AttendanceCorrectionRequest.Status.PENDING
        )
    else:  # HOD
        query = AttendanceCorrectionRequest.objects.filter(
            attendance__session__department=request.user.department,
            status=AttendanceCorrectionRequest.Status.PENDING
        )
    
    requests = query.select_related(
        'attendance__session__subject',
        'student'
    ).order_by('-created_at')
    
    return JsonResponse({
        'success': True,
        'count': requests.count(),
        'requests': [
            {
                'id': req.id,
                'student': {
                    'roll_no': req.student.roll_no,
                    'name': req.student.full_name,
                    'id': req.student.id,
                },
                'session': {
                    'id': req.attendance.session.id,
                    'subject': req.attendance.session.subject.code,
                    'date': req.attendance.session.date.isoformat(),
                },
                'reason': req.reason,
                'created_at': req.created_at.isoformat(),
                'requested_window_remaining': (
                    (req.attendance.session.date + timedelta(hours=getattr(settings, 'ATTENDANCE_REQUEST_WINDOW', 48))
                     - timezone.now()).total_seconds() / 3600
                ),
            }
            for req in requests
        ]
    })


@login_required
@require_POST
def approve_correction_request(request, request_id):
    """Teacher approves correction request"""
    try:
        data = json.loads(request.body)
        corrected_status = data.get('corrected_status')
        comment = data.get('comment', '')
        
        if corrected_status not in dict(Attendance.Status.choices):
            return JsonResponse({
                'success': False,
                'error': 'Invalid attendance status'
            }, status=400)
        
        correction_request = get_object_or_404(
            AttendanceCorrectionRequest,
            id=request_id
        )
        
        # Check permission
        if request.user.role == 'teacher' and correction_request.teacher != request.user:
            return JsonResponse({
                'success': False,
                'error': 'You can only approve requests assigned to you'
            }, status=403)

        if request.user.role == 'hod' and correction_request.attendance.session.department_id != request.user.department_id:
            return JsonResponse({
                'success': False,
                'error': 'You can only approve requests from your department'
            }, status=403)
        
        correction_request.approve(request.user, corrected_status, comment)
        
        return JsonResponse({
            'success': True,
            'message': 'Request approved successfully',
            'request_id': correction_request.id,
            'new_status': corrected_status,
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def reject_correction_request(request, request_id):
    """Teacher rejects correction request"""
    try:
        data = json.loads(request.body)
        comment = data.get('comment', '')
        
        if not comment:
            return JsonResponse({
                'success': False,
                'error': 'Reason for rejection is required'
            }, status=400)
        
        correction_request = get_object_or_404(
            AttendanceCorrectionRequest,
            id=request_id
        )
        
        # Check permission
        if request.user.role == 'teacher' and correction_request.teacher != request.user:
            return JsonResponse({
                'success': False,
                'error': 'You can only reject requests assigned to you'
            }, status=403)

        if request.user.role == 'hod' and correction_request.attendance.session.department_id != request.user.department_id:
            return JsonResponse({
                'success': False,
                'error': 'You can only reject requests from your department'
            }, status=403)
        
        correction_request.reject(request.user, comment)
        
        return JsonResponse({
            'success': True,
            'message': 'Request rejected'
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
    

@login_required
def all_notifications_page(request):
    """Render all notifications page"""
    context = {
        'page_title': 'Notifications'
    }
    return render(request, 'attendance/notifications.html', context)


@login_required
def session_detail_with_correction(request, session_id):
    """Session detail page with correction request"""
    session = get_object_or_404(
        Session.objects.select_related('subject', 'teacher', 'department'),
        id=session_id,
    )
    
    if request.user.role == 'student':
        attendance = get_object_or_404(
            Attendance,
            session=session,
            student=request.user
        )
    elif request.user.role == 'teacher':
        if session.teacher_id != request.user.id:
            return HttpResponseForbidden('Access denied.')
        attendance = None
    elif request.user.role == 'hod':
        if session.department_id != request.user.department_id:
            return HttpResponseForbidden('Access denied.')
        attendance = None
    elif request.user.role == 'admin':
        attendance = None
    else:
        return HttpResponseForbidden('Access denied.')
    
    # Check request window
    now = timezone.now()
    request_window = timedelta(hours=getattr(settings, 'ATTENDANCE_REQUEST_WINDOW', 48))
    session_end = timezone.make_aware(
        datetime.combine(
            session.date,
            session.end_time or time(23, 59, 59)
        )
    )
    
    request_window_open = now <= session_end + request_window
    time_remaining = (session_end + request_window - now).total_seconds() / 3600

    session_duration_minutes = None
    if session.start_time and session.end_time:
        start_dt = datetime.combine(session.date, session.start_time)
        end_dt = datetime.combine(session.date, session.end_time)
        if end_dt >= start_dt:
            session_duration_minutes = int((end_dt - start_dt).total_seconds() // 60)
    
    correction_request = None
    if attendance and attendance.status == Attendance.Status.ABSENT:
        correction_request = AttendanceCorrectionRequest.objects.filter(
            student=request.user,
            attendance__session=session
        ).first()
    
    context = {
        'session': session,
        'attendance': attendance,
        'records': session.records.select_related('student').order_by('student__roll_no'),
        'correction_request': correction_request,
        'request_window_open': request_window_open,
        'request_window_hours': round(time_remaining, 1),
        'session_duration_minutes': session_duration_minutes,
    }
    
    return render(request, 'attendance/session_detail_with_correction.html', context)


@login_required
def correction_requests_teacher_page(request):
    """Teacher page for managing correction requests"""
    if request.user.role not in ['teacher', 'hod']:
        return HttpResponseForbidden()

    if request.user.role == 'teacher':
        requests_qs = AttendanceCorrectionRequest.objects.filter(teacher=request.user)
    else:
        requests_qs = AttendanceCorrectionRequest.objects.filter(
            attendance__session__department=request.user.department
        )

    requests_qs = requests_qs.select_related(
        'student',
        'attendance__session__subject',
        'teacher',
    ).order_by('-created_at')

    context = {
        'page_title': 'Correction Requests',
        'correction_requests': requests_qs,
        'pending_count': requests_qs.filter(status=AttendanceCorrectionRequest.Status.PENDING).count(),
        'approved_count': requests_qs.filter(status=AttendanceCorrectionRequest.Status.APPROVED).count(),
        'rejected_count': requests_qs.filter(status=AttendanceCorrectionRequest.Status.REJECTED).count(),
        'total_count': requests_qs.count(),
    }
    
    return render(request, 'attendance/correction_requests_teacher.html', context)


@login_required
def my_correction_requests(request):
    """Student page to view their correction requests"""
    requests = AttendanceCorrectionRequest.objects.filter(
        student=request.user
    ).select_related('attendance__session__subject', 'teacher')
    
    context = {
        'correction_requests': requests,
        'page_title': 'My Correction Requests'
    }
    
    return render(request, 'attendance/my_correction_requests.html', context)