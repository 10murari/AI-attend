"""Bulk CSV import for departments, teachers and students.

All imports are atomic: if any row fails validation the whole file is
rejected and nothing is saved, so a file can safely be fixed and re-uploaded.
"""

import csv
import io
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Max
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render

from accounts.models import CustomUser
from .models import Batch, Department
from .views import admin_required, _generate_roll_no

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_ROWS = 1000


# ==============================================================
# CSV SPECS (columns, sample rows, help text per import kind)
# ==============================================================

IMPORT_SPECS = {
    'departments': {
        'title': 'Import Departments',
        'list_url': 'department_list',
        'columns': [
            {'name': 'name', 'required': True, 'note': 'Full department name, e.g. Computer Engineering'},
            {'name': 'code', 'required': True, 'note': 'Short unique code, e.g. COMP'},
            {'name': 'roll_code', 'required': False, 'note': 'Two-digit code used in roll numbers, e.g. 03'},
        ],
        'sample': [
            ['name', 'code', 'roll_code'],
            ['Computer Engineering', 'COMP', '03'],
            ['Civil Engineering', 'CIVIL', '01'],
        ],
    },
    'teachers': {
        'title': 'Import Teachers',
        'list_url': 'teacher_list',
        'columns': [
            {'name': 'username', 'required': True, 'note': 'Unique login username, e.g. prof.sharma'},
            {'name': 'full_name', 'required': True, 'note': 'Full name'},
            {'name': 'department_code', 'required': False, 'note': 'Existing department code, e.g. COMP'},
            {'name': 'email', 'required': False, 'note': 'Email address'},
            {'name': 'phone', 'required': False, 'note': 'Phone number'},
            {'name': 'password', 'required': False, 'note': 'Leave blank to use the username as password'},
        ],
        'sample': [
            ['username', 'full_name', 'department_code', 'email', 'phone', 'password'],
            ['prof.sharma', 'Prof. Ram Sharma', 'COMP', 'ram@example.com', '9800000001', ''],
            ['prof.thapa', 'Prof. Sita Thapa', 'CIVIL', '', '', 'secret123'],
        ],
    },
    'students': {
        'title': 'Import Students',
        'list_url': 'student_list',
        'columns': [
            {'name': 'full_name', 'required': True, 'note': 'Full name'},
            {'name': 'department_code', 'required': True, 'note': 'Existing department code (must have a roll code set)'},
            {'name': 'batch_year', 'required': True, 'note': 'Intake year, e.g. 2026 — batch is created/reused automatically'},
            {'name': 'semester', 'required': True, 'note': 'Current semester (1-8)'},
            {'name': 'email', 'required': False, 'note': 'Email address'},
            {'name': 'phone', 'required': False, 'note': 'Phone number'},
            {'name': 'password', 'required': False, 'note': 'Leave blank to use the roll number as password'},
        ],
        'sample': [
            ['full_name', 'department_code', 'batch_year', 'semester', 'email', 'phone', 'password'],
            ['Hari Bahadur', 'COMP', '2026', '1', 'hari@example.com', '9800000010', ''],
            ['Gita Kumari', 'COMP', '2026', '1', '', '', ''],
        ],
    },
}


# ==============================================================
# HELPERS
# ==============================================================

def _read_csv(uploaded_file):
    """Parse an uploaded CSV into a list of dicts with normalized keys.

    Returns (rows, error). Keys are lowercased/stripped; values stripped.
    """
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        return None, 'File too large (max 2 MB).'
    try:
        text = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        return None, 'File is not valid UTF-8 text. Save it as CSV (UTF-8) and retry.'

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return None, 'CSV file is empty.'

    rows = []
    for raw in reader:
        row = {}
        for key, value in raw.items():
            if key is None:
                continue
            row[key.strip().lower()] = (value or '').strip()
        if any(row.values()):  # skip fully blank lines
            rows.append(row)

    if not rows:
        return None, 'CSV has a header but no data rows.'
    if len(rows) > MAX_ROWS:
        return None, f'Too many rows (max {MAX_ROWS} per file).'
    return rows, None


def _missing_columns(rows, required):
    present = set(rows[0].keys())
    return [c for c in required if c not in present]


def _render_import(request, kind, errors=None):
    spec = IMPORT_SPECS[kind]
    return render(request, 'academics/csv_import.html', {
        'kind': kind,
        'title': spec['title'],
        'columns': spec['columns'],
        'list_url': spec['list_url'],
        'errors': errors or [],
    })


def _get_uploaded_rows(request, kind, required_columns):
    """Shared POST handling. Returns (rows, error_response)."""
    uploaded = request.FILES.get('csv_file')
    if not uploaded:
        return None, _render_import(request, kind, ['Please choose a CSV file to upload.'])
    rows, error = _read_csv(uploaded)
    if error:
        return None, _render_import(request, kind, [error])
    missing = _missing_columns(rows, required_columns)
    if missing:
        return None, _render_import(request, kind, [
            f"Missing required column(s): {', '.join(missing)}. "
            'Download the template below to see the expected format.'
        ])
    return rows, None


def _valid_email(value):
    try:
        validate_email(value)
        return True
    except ValidationError:
        return False


# ==============================================================
# TEMPLATE DOWNLOAD
# ==============================================================

@login_required
@admin_required
def download_template(request, kind):
    spec = IMPORT_SPECS.get(kind)
    if not spec:
        raise Http404
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(spec['sample'])
    response = HttpResponse(buffer.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{kind}_template.csv"'
    return response


# ==============================================================
# DEPARTMENTS
# ==============================================================

@login_required
@admin_required
def department_import(request):
    if request.method != 'POST':
        return _render_import(request, 'departments')

    rows, error_response = _get_uploaded_rows(request, 'departments', ['name', 'code'])
    if error_response:
        return error_response

    errors = []
    seen_names, seen_codes, seen_rolls = set(), set(), set()
    to_create = []

    for line, row in enumerate(rows, start=2):
        name = row.get('name', '')
        code = row.get('code', '').upper()
        roll_code = row.get('roll_code', '')

        if not name:
            errors.append(f'Row {line}: name is required.')
            continue
        if not code:
            errors.append(f'Row {line}: code is required.')
            continue
        if roll_code and not re.fullmatch(r'\d{2}', roll_code):
            errors.append(f'Row {line}: roll_code must be exactly 2 digits (got "{roll_code}").')
            continue

        if name.lower() in seen_names:
            errors.append(f'Row {line}: duplicate name "{name}" in file.')
            continue
        if code in seen_codes:
            errors.append(f'Row {line}: duplicate code "{code}" in file.')
            continue
        if roll_code and roll_code in seen_rolls:
            errors.append(f'Row {line}: duplicate roll_code "{roll_code}" in file.')
            continue

        if Department.objects.filter(name__iexact=name).exists():
            errors.append(f'Row {line}: department name "{name}" already exists.')
            continue
        if Department.objects.filter(code__iexact=code).exists():
            errors.append(f'Row {line}: department code "{code}" already exists.')
            continue
        if roll_code and Department.objects.filter(roll_code=roll_code).exists():
            errors.append(f'Row {line}: roll_code "{roll_code}" is already used by another department.')
            continue

        seen_names.add(name.lower())
        seen_codes.add(code)
        if roll_code:
            seen_rolls.add(roll_code)
        to_create.append(Department(name=name, code=code, roll_code=roll_code or None))

    if errors:
        return _render_import(request, 'departments', errors)

    with transaction.atomic():
        Department.objects.bulk_create(to_create)

    messages.success(request, f'{len(to_create)} department(s) imported successfully.')
    return redirect('department_list')


# ==============================================================
# TEACHERS
# ==============================================================

@login_required
@admin_required
def teacher_import(request):
    if request.method != 'POST':
        return _render_import(request, 'teachers')

    rows, error_response = _get_uploaded_rows(request, 'teachers', ['username', 'full_name'])
    if error_response:
        return error_response

    departments = {d.code.upper(): d for d in Department.objects.filter(is_active=True)}
    errors = []
    seen_usernames = set()
    validated = []

    for line, row in enumerate(rows, start=2):
        username = row.get('username', '')
        full_name = row.get('full_name', '')
        dept_code = row.get('department_code', '').upper()
        email = row.get('email', '')
        phone = row.get('phone', '')
        password = row.get('password', '')

        if not username:
            errors.append(f'Row {line}: username is required.')
            continue
        if not full_name:
            errors.append(f'Row {line}: full_name is required.')
            continue
        if username.lower() in seen_usernames:
            errors.append(f'Row {line}: duplicate username "{username}" in file.')
            continue
        if CustomUser.objects.filter(username__iexact=username).exists():
            errors.append(f'Row {line}: username "{username}" already exists.')
            continue

        department = None
        if dept_code:
            department = departments.get(dept_code)
            if not department:
                errors.append(f'Row {line}: department code "{dept_code}" not found.')
                continue
        if email and not _valid_email(email):
            errors.append(f'Row {line}: invalid email "{email}".')
            continue
        if password and len(password) < 4:
            errors.append(f'Row {line}: password must be at least 4 characters.')
            continue

        seen_usernames.add(username.lower())
        validated.append({
            'username': username, 'full_name': full_name, 'department': department,
            'email': email, 'phone': phone, 'password': password or username,
        })

    if errors:
        return _render_import(request, 'teachers', errors)

    with transaction.atomic():
        for item in validated:
            user = CustomUser(
                username=item['username'],
                full_name=item['full_name'],
                role='teacher',
                department=item['department'],
                email=item['email'],
                phone=item['phone'],
            )
            user.set_password(item['password'])
            user.save()

    messages.success(
        request,
        f'{len(validated)} teacher(s) imported. '
        'Teachers without a password column value use their username as password.'
    )
    return redirect('teacher_list')


# ==============================================================
# STUDENTS
# ==============================================================

@login_required
@admin_required
def student_import(request):
    if request.method != 'POST':
        return _render_import(request, 'students')

    rows, error_response = _get_uploaded_rows(
        request, 'students', ['full_name', 'department_code', 'batch_year', 'semester']
    )
    if error_response:
        return error_response

    errors = []
    created_rolls = []

    try:
        with transaction.atomic():
            departments = {
                d.code.upper(): d
                for d in Department.objects.select_for_update().filter(is_active=True)
            }
            batches = {}       # (dept_id, year) -> Batch (locked)
            next_sequence = {}  # (dept_id, batch_id) -> next batch_sequence

            for line, row in enumerate(rows, start=2):
                full_name = row.get('full_name', '')
                dept_code = row.get('department_code', '').upper()
                batch_year_raw = row.get('batch_year', '')
                semester_raw = row.get('semester', '')
                email = row.get('email', '')
                phone = row.get('phone', '')
                password = row.get('password', '')

                if not full_name:
                    errors.append(f'Row {line}: full_name is required.')
                    continue

                department = departments.get(dept_code)
                if not department:
                    errors.append(f'Row {line}: department code "{dept_code}" not found.')
                    continue
                if not department.roll_code:
                    errors.append(
                        f'Row {line}: department "{department.code}" has no roll code set. '
                        'Set it in Departments first.'
                    )
                    continue

                if not batch_year_raw.isdigit() or not (2000 <= int(batch_year_raw) <= 2099):
                    errors.append(f'Row {line}: batch_year must be between 2000 and 2099 (got "{batch_year_raw}").')
                    continue
                batch_year = int(batch_year_raw)

                if not semester_raw.isdigit() or not (1 <= int(semester_raw) <= 8):
                    errors.append(f'Row {line}: semester must be between 1 and 8 (got "{semester_raw}").')
                    continue
                semester = int(semester_raw)

                if email and not _valid_email(email):
                    errors.append(f'Row {line}: invalid email "{email}".')
                    continue
                if password and len(password) < 4:
                    errors.append(f'Row {line}: password must be at least 4 characters.')
                    continue

                batch_key = (department.id, batch_year)
                batch = batches.get(batch_key)
                if batch is None:
                    batch, _ = Batch.objects.select_for_update().get_or_create(
                        department=department,
                        year=batch_year,
                        defaults={'code': str(batch_year)[-2:], 'is_active': True},
                    )
                    batches[batch_key] = batch

                # Semester lock — same rules as single-student create
                if batch.semester_lock_enabled:
                    if batch.locked_semester is None:
                        existing_semesters = set(
                            CustomUser.objects.filter(
                                role='student',
                                batch_id=batch.id,
                                department_id=department.id,
                                is_active=True,
                            )
                            .exclude(semester__isnull=True)
                            .values_list('semester', flat=True)
                        )
                        if len(existing_semesters) > 1:
                            errors.append(
                                f'Row {line}: batch {batch.year} ({department.code}) has mixed '
                                'semesters. Clean batch data before importing.'
                            )
                            continue
                        if len(existing_semesters) == 1:
                            batch.locked_semester = next(iter(existing_semesters))
                            batch.save(update_fields=['locked_semester'])

                    if batch.locked_semester is not None and semester != batch.locked_semester:
                        errors.append(
                            f'Row {line}: batch {batch.year} ({department.code}) is locked to '
                            f'Semester {batch.locked_semester}, cannot add Semester {semester}.'
                        )
                        continue

                    if batch.locked_semester is None:
                        batch.locked_semester = semester
                        batch.save(update_fields=['locked_semester'])

                seq_key = (department.id, batch.id)
                if seq_key not in next_sequence:
                    current_max = CustomUser.objects.filter(
                        role='student',
                        batch_id=batch.id,
                        department_id=department.id,
                    ).aggregate(max_seq=Max('batch_sequence'))['max_seq'] or 0
                    next_sequence[seq_key] = current_max + 1

                sequence = next_sequence[seq_key]
                if sequence > 99:
                    errors.append(
                        f'Row {line}: batch {batch.year} ({department.code}) sequence limit '
                        'reached (max 99 students).'
                    )
                    continue
                next_sequence[seq_key] = sequence + 1

                roll_no = _generate_roll_no(batch, department, sequence)
                user = CustomUser(
                    role='student',
                    full_name=full_name,
                    department=department,
                    batch=batch,
                    batch_sequence=sequence,
                    semester=semester,
                    roll_no=roll_no,
                    username=roll_no,
                    email=email,
                    phone=phone,
                )
                user.set_password(password or roll_no)
                user.save()
                created_rolls.append(roll_no)

            if errors:
                # Roll everything back — the file must import cleanly or not at all.
                transaction.set_rollback(True)
    except Exception:
        errors.append('Unexpected error while importing. No students were saved.')

    if errors:
        return _render_import(request, 'students', errors)

    messages.success(
        request,
        f'{len(created_rolls)} student(s) imported (roll numbers '
        f'{created_rolls[0]} … {created_rolls[-1]}). '
        'Students without a password column value use their roll number as password.'
    )
    return redirect('student_list')
