from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import LoginForm, ChangePasswordForm, ProfileForm


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Welcome, {user.full_name or user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def dashboard_view(request):
    user = request.user
    if user.is_admin_user:
        return render(request, 'dashboards/admin_dashboard.html', get_admin_context())
    elif user.is_hod:
        return render(request, 'dashboards/hod_dashboard.html', get_hod_context(user))
    elif user.is_teacher:
        return render(request, 'dashboards/teacher_dashboard.html', get_teacher_context(user))
    elif user.is_student:
        return render(request, 'dashboards/student_dashboard.html', get_student_context(user))
    return render(request, 'dashboards/admin_dashboard.html')


@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html')


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = ChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully.')
            return redirect('profile')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = ChangePasswordForm(request.user)
    return render(request, 'accounts/change_password.html', {'form': form})


# ==============================================================
# DASHBOARD CONTEXT FUNCTIONS
# ==============================================================

def get_admin_context():
    from academics.models import Department, Subject
    from accounts.models import CustomUser
    from attendance.models import Session
    from django.utils import timezone

    today = timezone.now().date()
    return {
        'total_departments': Department.objects.filter(is_active=True).count(),
        'total_teachers': CustomUser.objects.filter(role__in=['teacher', 'hod'], is_active=True).count(),
        'total_students': CustomUser.objects.filter(role='student', is_active=True).count(),
        'total_subjects': Subject.objects.filter(is_active=True).count(),
        'today_sessions': Session.objects.filter(date=today).count(),
        'active_sessions': Session.objects.filter(status='ACTIVE').count(),
        'departments': Department.objects.filter(is_active=True).prefetch_related('subjects'),
        'recent_sessions': Session.objects.select_related(
            'subject', 'teacher', 'department'
        ).order_by('-date', '-start_time')[:5],
    }


def get_hod_context(user):
    from academics.models import Subject
    from accounts.models import CustomUser
    from attendance.models import Session
    from django.utils import timezone

    dept = user.department
    today = timezone.now().date()
    return {
        'department': dept,
        'total_students': CustomUser.objects.filter(role='student', department=dept, is_active=True).count(),
        'total_subjects': Subject.objects.filter(department=dept, is_active=True).count(),
        'total_teachers': CustomUser.objects.filter(role__in=['teacher', 'hod'], department=dept, is_active=True).count(),
        'today_sessions': Session.objects.filter(department=dept, date=today).count(),
        'subjects': Subject.objects.filter(department=dept, is_active=True).prefetch_related('teacher_assignments__teacher'),
    }


def get_teacher_context(user):
    from academics.models import SubjectTeacher
    from attendance.models import Session
    from django.utils import timezone

    today = timezone.now().date()
    assignments = SubjectTeacher.objects.filter(
        teacher=user
    ).select_related('subject', 'subject__department')

    return {
        'assignments': assignments,
        'today_sessions': Session.objects.filter(teacher=user, date=today).select_related('subject'),
        'active_sessions': Session.objects.filter(teacher=user, status='ACTIVE').select_related('subject'),
    }


def get_student_context(user):
    from academics.models import Subject, SubjectTeacher
    from attendance.models import Attendance, Session

    subjects = Subject.objects.filter(
        department=user.department, semester=user.semester, is_active=True,
    )

    subject_stats = []
    for subject in subjects:
        total = Session.objects.filter(subject=subject, status='COMPLETED').count()
        present = Attendance.objects.filter(session__subject=subject, student=user, status='PRESENT').count()
        late = Attendance.objects.filter(session__subject=subject, student=user, status='LATE').count()
        absent = max(total - present - late, 0)
        pct = round(((present + late) / total) * 100, 1) if total > 0 else 0

        subject_stats.append({
            'subject': subject, 'total': total,
            'present': present, 'late': late, 'absent': absent,
            'percentage': pct,
        })

    total_all = sum(s['total'] for s in subject_stats)
    present_all = sum(s['present'] + s['late'] for s in subject_stats)
    overall = round((present_all / total_all) * 100, 1) if total_all > 0 else 0

    return {
        'subject_stats': subject_stats,
        'overall_percentage': overall,
        'total_sessions': total_all,
        'total_present': present_all,
    }