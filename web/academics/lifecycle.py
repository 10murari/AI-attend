"""
Academic lifecycle management:
- Promote students to next semester (batch)
- Graduate students (archive semester 8)
- Archive old sessions
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from accounts.models import CustomUser
from .models import Batch, Department


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
        batches = Batch.objects.filter(department=dept, is_active=True).order_by('-year')
        batch_rows = []

        for batch in batches:
            semesters = {}
            for sem in range(1, 9):
                count = CustomUser.objects.filter(
                    role='student',
                    department=dept,
                    batch=batch,
                    semester=sem,
                    is_active=True,
                ).count()
                if count > 0:
                    next_count = 0
                    can_promote = True
                    if sem < 8:
                        next_count = CustomUser.objects.filter(
                            role='student',
                            department=dept,
                            batch=batch,
                            semester=sem + 1,
                            is_active=True,
                        ).count()
                        can_promote = next_count == 0

                    semesters[sem] = {
                        'count': count,
                        'next_count': next_count,
                        'can_promote': can_promote,
                    }

            if semesters:
                batch_rows.append({
                    'batch': batch,
                    'semesters': semesters,
                    'total_students': sum(v['count'] for v in semesters.values()),
                })

        dept_data.append({'dept': dept, 'batch_rows': batch_rows})

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
        batch_id = request.POST.get('batch')
        from_sem = int(request.POST.get('from_semester', 0))

        if from_sem < 1 or from_sem > 7:
            messages.error(request, 'Invalid semester.')
            return redirect('semester_management')

        if not batch_id:
            messages.error(request, 'Batch is required for promotion.')
            return redirect('semester_management')

        batch = Batch.objects.filter(id=batch_id, department_id=dept_id, is_active=True).first()
        if not batch:
            messages.error(request, 'Invalid batch for selected department.')
            return redirect('semester_management')

        with transaction.atomic():
            source_students = CustomUser.objects.select_for_update().filter(
                role='student', department_id=dept_id,
                batch=batch, semester=from_sem, is_active=True,
            )
            source_count = source_students.count()

            if source_count == 0:
                messages.warning(request, 'No students found to promote.')
                return redirect('semester_management')

            target_count = CustomUser.objects.select_for_update().filter(
                role='student', department_id=dept_id,
                batch=batch, semester=from_sem + 1, is_active=True,
            ).count()

            if target_count > 0:
                messages.error(
                    request,
                    f'Promotion blocked: Batch {batch.year} already has {target_count} student(s) in Semester {from_sem + 1}. '
                    f'Clear/fix Semester {from_sem + 1} first to avoid appending.',
                )
                return redirect('semester_management')

            source_students.update(semester=from_sem + 1)

        messages.success(request,
            f'Promoted {source_count} students from Semester {from_sem} to Semester {from_sem + 1} for Batch {batch.year}.')
        return redirect('semester_management')

    return redirect('semester_management')


@login_required
@admin_required
def graduate_students(request):
    """Archive semester 8 students (mark inactive)."""
    if request.method == 'POST':
        dept_id = request.POST.get('department')
        batch_id = request.POST.get('batch')

        if not batch_id:
            messages.error(request, 'Batch is required for graduation.')
            return redirect('semester_management')

        batch = Batch.objects.filter(id=batch_id, department_id=dept_id, is_active=True).first()
        if not batch:
            messages.error(request, 'Invalid batch for selected department.')
            return redirect('semester_management')

        students = CustomUser.objects.filter(
            role='student', department_id=dept_id,
            batch=batch, semester=8, is_active=True,
        )
        count = students.count()

        if count == 0:
            messages.warning(request, 'No semester 8 students found.')
            return redirect('semester_management')

        students.update(is_active=False)
        messages.success(request,
            f'Graduated {count} students from Batch {batch.year} (marked inactive). '
            f'Their attendance data is preserved.')
        return redirect('semester_management')

    return redirect('semester_management')