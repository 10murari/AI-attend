from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models import Max
from .models import Department, Subject, SubjectTeacher
from .forms import (
    BatchForm, DepartmentForm, SubjectForm, SubjectTeacherForm,
    TeacherForm, TeacherEditForm, StudentForm, StudentEditForm
)
from accounts.models import CustomUser
from .models import Batch


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != 'admin':
            messages.error(request, 'Admin access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def _generate_roll_no(batch, department, sequence):
    batch_code = batch.code or str(batch.year)[-2:]
    return f"{batch_code}{department.roll_code}{sequence:02d}"


# ==============================================================
# BATCH MANAGEMENT
# ============================================================== 

@login_required
@admin_required
def batch_list(request):
    batches = Batch.objects.select_related('department').order_by('department__code', '-year')

    dept_filter = request.GET.get('department')
    if dept_filter:
        batches = batches.filter(department_id=dept_filter)

    return render(request, 'academics/batch_list.html', {
        'batches': batches,
        'departments': Department.objects.filter(is_active=True),
        'selected_dept': dept_filter,
    })


@login_required
@admin_required
def batch_create(request):
    if request.method == 'POST':
        form = BatchForm(request.POST)
        if form.is_valid():
            batch = form.save()
            messages.success(request, f'Batch {batch.year} ({batch.code}) created for {batch.department.code}.')
            return redirect('batch_list')
    else:
        form = BatchForm()

    return render(request, 'academics/batch_form.html', {
        'form': form,
        'title': 'Add Batch',
        'is_edit': False,
    })


# ============================================================== 
# DEPARTMENT CRUD
# ==============================================================

@login_required
@admin_required
def department_list(request):
    departments = Department.objects.filter(is_active=True)

    dept_data = []
    for dept in departments:
        dept_data.append({
            'dept': dept,
            'num_students': CustomUser.objects.filter(
                role='student', department=dept, is_active=True
            ).count(),
            'num_teachers': CustomUser.objects.filter(
                role__in=['teacher', 'hod'], department=dept, is_active=True
            ).count(),
            'num_subjects': Subject.objects.filter(
                department=dept, is_active=True
            ).count(),
        })

    return render(request, 'academics/department_list.html', {
        'dept_data': dept_data,
    })


@login_required
@admin_required
def department_create(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Department created successfully.')
            return redirect('department_list')
    else:
        form = DepartmentForm()
    return render(request, 'academics/department_form.html', {
        'form': form, 'title': 'Add Department', 'is_edit': False,
    })


@login_required
@admin_required
def department_edit(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=dept)
        if form.is_valid():
            form.save()
            messages.success(request, f'{dept.name} updated.')
            return redirect('department_list')
    else:
        form = DepartmentForm(instance=dept)
    return render(request, 'academics/department_form.html', {
        'form': form, 'title': f'Edit: {dept.name}', 'is_edit': True, 'dept': dept,
    })


@login_required
@admin_required
def department_delete(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        dept.is_active = False
        dept.save()
        messages.success(request, f'{dept.name} deactivated.')
        return redirect('department_list')
    return render(request, 'academics/department_confirm_delete.html', {'dept': dept})


# ==============================================================
# TEACHER MANAGEMENT
# ==============================================================

@login_required
@admin_required
def teacher_list(request):
    teachers = CustomUser.objects.filter(
        role__in=['teacher', 'hod'], is_active=True
    ).select_related('department').prefetch_related('subject_assignments__subject')

    dept_filter = request.GET.get('department')
    if dept_filter:
        teachers = teachers.filter(department_id=dept_filter)

    return render(request, 'academics/teacher_list.html', {
        'teachers': teachers,
        'departments': Department.objects.filter(is_active=True),
        'selected_dept': dept_filter,
    })


@login_required
@admin_required
def teacher_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'teacher'
            user.save()
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, f'Teacher "{user.full_name}" created. Username: {user.username}')
            return redirect('teacher_list')
    else:
        form = TeacherForm()
    return render(request, 'academics/teacher_form.html', {
        'form': form, 'title': 'Add Teacher', 'is_edit': False,
    })


@login_required
@admin_required
def teacher_edit(request, pk):
    teacher = get_object_or_404(CustomUser, pk=pk, role__in=['teacher', 'hod'])
    if request.method == 'POST':
        form = TeacherEditForm(request.POST, instance=teacher)
        if form.is_valid():
            form.save()
            messages.success(request, f'{teacher.full_name} updated.')
            return redirect('teacher_list')
    else:
        form = TeacherEditForm(instance=teacher)
    return render(request, 'academics/teacher_form.html', {
        'form': form, 'title': f'Edit: {teacher.full_name}', 'is_edit': True, 'teacher': teacher,
    })


@login_required
@admin_required
def teacher_delete(request, pk):
    teacher = get_object_or_404(CustomUser, pk=pk, role__in=['teacher', 'hod'])
    if request.method == 'POST':
        teacher.is_active = False
        teacher.save()
        messages.success(request, f'{teacher.full_name} deactivated.')
        return redirect('teacher_list')
    return render(request, 'academics/confirm_delete.html', {
        'obj': teacher,
        'obj_type': 'Teacher',
        'obj_name': teacher.full_name,
        'cancel_url': 'teacher_list',
    })


@login_required
@admin_required
def teacher_promote_hod(request, pk):
    """Promote a teacher to HOD and assign to their department."""
    teacher = get_object_or_404(CustomUser, pk=pk, role__in=['teacher', 'hod'])

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'promote':
            # Remove HOD from current department if any
            dept = teacher.department
            if dept:
                old_hod = dept.hod
                if old_hod and old_hod != teacher:
                    old_hod.role = 'teacher'
                    old_hod.save()
                    messages.info(request, f'{old_hod.full_name} demoted from HOD.')

                dept.hod = teacher
                dept.save()

            teacher.role = 'hod'
            teacher.save()
            messages.success(request, f'{teacher.full_name} promoted to HOD of {dept.name}.')

        elif action == 'demote':
            if teacher.department:
                dept = teacher.department
                if dept.hod == teacher:
                    dept.hod = None
                    dept.save()
            teacher.role = 'teacher'
            teacher.save()
            messages.success(request, f'{teacher.full_name} demoted to Teacher.')

        return redirect('teacher_list')

    return render(request, 'academics/teacher_promote_hod.html', {
        'teacher': teacher,
    })


@login_required
@admin_required
def teacher_reset_password(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        if len(new_password) < 4:
            messages.error(request, 'Password must be at least 4 characters.')
        else:
            user.set_password(new_password)
            user.save()
            messages.success(request, f'Password reset for {user.full_name}.')
        return redirect('teacher_list')

    return render(request, 'academics/reset_password.html', {
        'target_user': user,
        'cancel_url': 'teacher_list',
    })


# ==============================================================
# SUBJECT MANAGEMENT
# ==============================================================

@login_required
@admin_required
def subject_list(request):
    subjects = Subject.objects.filter(is_active=True).select_related(
        'department'
    ).prefetch_related('teacher_assignments__teacher')

    dept_filter = request.GET.get('department')
    sem_filter = request.GET.get('semester')
    if dept_filter:
        subjects = subjects.filter(department_id=dept_filter)
    if sem_filter:
        subjects = subjects.filter(semester=sem_filter)

    return render(request, 'academics/subject_list.html', {
        'subjects': subjects,
        'departments': Department.objects.filter(is_active=True),
        'selected_dept': dept_filter,
        'selected_sem': sem_filter,
    })


@login_required
@admin_required
def subject_create(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save()
            teacher_id = request.POST.get('teacher')
            if teacher_id:
                SubjectTeacher.objects.create(teacher_id=teacher_id, subject=subject)
            messages.success(request, f'Subject "{subject.code} — {subject.name}" created.')
            return redirect('subject_list')
    else:
        form = SubjectForm()

    teachers = CustomUser.objects.filter(
        role__in=['teacher', 'hod'], is_active=True
    ).select_related('department')

    return render(request, 'academics/subject_form.html', {
        'form': form, 'title': 'Add Subject', 'is_edit': False,
        'teachers': teachers,
    })


@login_required
@admin_required
def subject_edit(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    current_assignment = SubjectTeacher.objects.filter(subject=subject).first()

    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            teacher_id = request.POST.get('teacher')

            # Update teacher assignment
            if teacher_id:
                if current_assignment:
                    current_assignment.teacher_id = teacher_id
                    current_assignment.save()
                else:
                    SubjectTeacher.objects.create(teacher_id=teacher_id, subject=subject)
            elif current_assignment:
                current_assignment.delete()

            messages.success(request, f'{subject.code} updated.')
            return redirect('subject_list')
    else:
        form = SubjectForm(instance=subject)

    teachers = CustomUser.objects.filter(
        role__in=['teacher', 'hod'], is_active=True
    ).select_related('department')

    return render(request, 'academics/subject_form.html', {
        'form': form, 'title': f'Edit: {subject.code}', 'is_edit': True,
        'teachers': teachers, 'subject': subject,
        'current_teacher_id': current_assignment.teacher_id if current_assignment else None,
    })


@login_required
@admin_required
def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        subject.is_active = False
        subject.save()
        messages.success(request, f'{subject.code} deactivated.')
        return redirect('subject_list')
    return render(request, 'academics/confirm_delete.html', {
        'obj': subject,
        'obj_type': 'Subject',
        'obj_name': f'{subject.code} — {subject.name}',
        'cancel_url': 'subject_list',
    })


# ==============================================================
# STUDENT MANAGEMENT
# ==============================================================

@login_required
@admin_required
def student_list(request):
    students = CustomUser.objects.filter(
        role='student', is_active=True
    ).select_related('department', 'batch', 'batch__department').order_by('department__code', 'semester', 'roll_no')

    dept_filter = request.GET.get('department')
    sem_filter = request.GET.get('semester')
    batch_filter = request.GET.get('batch')
    if dept_filter:
        students = students.filter(department_id=dept_filter)
    if sem_filter:
        students = students.filter(semester=sem_filter)
    if batch_filter:
        students = students.filter(batch_id=batch_filter)

    from enrollment.models import FaceEmbedding
    enrolled_user_ids = set(
        FaceEmbedding.objects.filter(is_active=True).values_list('user_id', flat=True)
    )

    student_data = []
    for s in students:
        student_data.append({
            'user': s,
            'has_embedding': s.id in enrolled_user_ids,
        })

    return render(request, 'academics/student_list.html', {
        'student_data': student_data,
        'total_students': len(student_data),
        'departments': Department.objects.filter(is_active=True),
        'batches': Batch.objects.select_related('department').filter(is_active=True).order_by('department__code', '-year'),
        'selected_dept': dept_filter,
        'selected_sem': sem_filter,
        'selected_batch': batch_filter,
    })


@login_required
@admin_required
def student_create(request):
    active_batch_exists = Batch.objects.filter(is_active=True).exists()
    missing_roll_departments = Department.objects.filter(
        is_active=True,
    ).filter(
        Q(roll_code__isnull=True) | Q(roll_code='')
    ).order_by('code')

    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.role = 'student'
                    batch_year = form.cleaned_data['batch_year']
                    department = user.department

                    locked_department = Department.objects.select_for_update().get(pk=department.id)
                    locked_batch, _ = Batch.objects.select_for_update().get_or_create(
                        department=locked_department,
                        year=batch_year,
                        defaults={
                            'code': str(batch_year)[-2:],
                            'is_active': True,
                        },
                    )

                    current_max = CustomUser.objects.filter(
                        role='student',
                        batch_id=locked_batch.id,
                        department_id=locked_department.id,
                    ).aggregate(max_seq=Max('batch_sequence'))['max_seq'] or 0

                    sequence = current_max + 1
                    if sequence > 99:
                        form.add_error('batch', 'Batch sequence limit reached for selected department (max 99).')
                        raise ValueError('batch sequence limit reached')

                    user.batch_sequence = sequence
                    user.batch = locked_batch
                    user.roll_no = _generate_roll_no(locked_batch, locked_department, sequence)
                    user.username = user.roll_no
                    user.save()
                    user.set_password(form.cleaned_data.get('password', user.roll_no))
                    user.save(update_fields=['password'])

                messages.success(request,
                    f'Student "{user.full_name}" ({user.roll_no}) created. '
                    f'Password: {form.cleaned_data.get("password", user.roll_no)}'
                )
                return redirect('student_list')
            except ValueError:
                pass
            except IntegrityError:
                form.add_error(None, 'Could not generate a unique roll number. Please retry.')
    else:
        form = StudentForm()

    return render(request, 'academics/student_form.html', {
        'form': form, 'title': 'Add Student', 'is_edit': False,
        'active_batch_exists': active_batch_exists,
        'missing_roll_departments': missing_roll_departments,
    })


@login_required
@admin_required
def student_edit(request, pk):
    student = get_object_or_404(CustomUser, pk=pk, role='student')
    if request.method == 'POST':
        form = StudentEditForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, f'{student.full_name} updated.')
            return redirect('student_list')
    else:
        form = StudentEditForm(instance=student)
    return render(request, 'academics/student_form.html', {
        'form': form, 'title': f'Edit: {student.full_name}', 'is_edit': True,
        'student': student,
    })


@login_required
@admin_required
def student_delete(request, pk):
    student = get_object_or_404(CustomUser, pk=pk, role='student')
    if request.method == 'POST':
        student.is_active = False
        student.save()
        messages.success(request, f'{student.full_name} ({student.roll_no}) deactivated.')
        return redirect('student_list')
    return render(request, 'academics/confirm_delete.html', {
        'obj': student,
        'obj_type': 'Student',
        'obj_name': f'{student.roll_no} — {student.full_name}',
        'cancel_url': 'student_list',
    })


@login_required
@admin_required
def student_reset_password(request, pk):
    student = get_object_or_404(CustomUser, pk=pk, role='student')
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        if len(new_password) < 4:
            messages.error(request, 'Password must be at least 4 characters.')
        else:
            student.set_password(new_password)
            student.save()
            messages.success(request, f'Password reset for {student.full_name} ({student.roll_no}).')
        return redirect('student_list')
    return render(request, 'academics/reset_password.html', {
        'target_user': student,
        'cancel_url': 'student_list',
    })


# ==============================================================
# ADMIN: ALL SESSIONS VIEW
# ==============================================================

@login_required
@admin_required
def admin_all_sessions(request):
    from attendance.models import Session
    sessions = Session.objects.all().select_related(
        'subject', 'teacher', 'department', 'batch'
    ).order_by('-date', '-start_time')

    dept_filter = request.GET.get('department')
    batch_filter = request.GET.get('batch')
    if dept_filter:
        sessions = sessions.filter(department_id=dept_filter)
    if batch_filter:
        sessions = sessions.filter(batch_id=batch_filter)

    batches = Batch.objects.select_related('department').filter(is_active=True).order_by('department__code', '-year')
    if dept_filter:
        batches = batches.filter(department_id=dept_filter)

    return render(request, 'academics/admin_all_sessions.html', {
        'sessions': sessions,
        'departments': Department.objects.filter(is_active=True),
        'batches': batches,
        'selected_dept': dept_filter,
        'selected_batch': batch_filter,
    })