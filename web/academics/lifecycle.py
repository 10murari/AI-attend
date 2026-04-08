"""
Academic lifecycle management:
- Promote students to next semester (batch)
- Graduate students (archive semester 8)
- Archive old sessions
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.models import CustomUser
from .models import Department


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != 'admin':
            messages.error(request, 'Admin access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@admin_required
def semester_management(request):
    """View semester distribution and promote/graduate."""
    departments = Department.objects.filter(is_active=True)

    dept_data = []
    for dept in departments:
        semesters = {}
        for sem in range(1, 9):
            count = CustomUser.objects.filter(
                role='student', department=dept,
                semester=sem, is_active=True,
            ).count()
            if count > 0:
                semesters[sem] = count
        dept_data.append({'dept': dept, 'semesters': semesters})

    return render(request, 'academics/semester_management.html', {
        'dept_data': dept_data,
        'departments': departments,
    })


@login_required
@admin_required
def promote_semester(request):
    """Promote all students in a department from one semester to next."""
    if request.method == 'POST':
        dept_id = request.POST.get('department')
        from_sem = int(request.POST.get('from_semester', 0))

        if from_sem < 1 or from_sem > 7:
            messages.error(request, 'Invalid semester.')
            return redirect('semester_management')

        students = CustomUser.objects.filter(
            role='student', department_id=dept_id,
            semester=from_sem, is_active=True,
        )
        count = students.count()

        if count == 0:
            messages.warning(request, 'No students found to promote.')
            return redirect('semester_management')

        students.update(semester=from_sem + 1)
        messages.success(request,
            f'Promoted {count} students from Semester {from_sem} to Semester {from_sem + 1}.')
        return redirect('semester_management')

    return redirect('semester_management')


@login_required
@admin_required
def graduate_students(request):
    """Archive semester 8 students (mark inactive)."""
    if request.method == 'POST':
        dept_id = request.POST.get('department')

        students = CustomUser.objects.filter(
            role='student', department_id=dept_id,
            semester=8, is_active=True,
        )
        count = students.count()

        if count == 0:
            messages.warning(request, 'No semester 8 students found.')
            return redirect('semester_management')

        students.update(is_active=False)
        messages.success(request,
            f'Graduated {count} students (marked inactive). '
            f'Their attendance data is preserved.')
        return redirect('semester_management')

    return redirect('semester_management')