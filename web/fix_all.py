"""
Master fix script. Rewrites ALL templates with clean UTF-8.
Run: cd C:\\Final_Project\\web && python fix_all.py
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def w(rel_path, content):
    full = os.path.join(BASE, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content.lstrip('\n'))
    print(f"  OK  {rel_path}")


print("=" * 50)
print("  FIXING ALL TEMPLATES + VIEWS")
print("=" * 50)

# ─────────────────────────────────────────────
# 1. PATCH: academics/views.py department_list
# ─────────────────────────────────────────────
print("\n[1] Patching department_list counts...")
vp = os.path.join(BASE, 'academics', 'views.py')
with open(vp, 'r', encoding='utf-8') as f:
    code = f.read()

OLD = """def department_list(request):
    departments = Department.objects.annotate(
        num_students=Count('users', filter=Q(users__role='student', users__is_active=True)),
        num_teachers=Count('users', filter=Q(users__role__in=['teacher', 'hod'], users__is_active=True)),
        num_subjects=Count('subjects', filter=Q(subjects__is_active=True)),
    )
    return render(request, 'academics/department_list.html', {
        'departments': departments,
    })"""

NEW = """def department_list(request):
    departments = Department.objects.filter(is_active=True)
    dept_data = []
    for dept in departments:
        dept_data.append({
            'dept': dept,
            'num_students': CustomUser.objects.filter(role='student', department=dept, is_active=True).count(),
            'num_teachers': CustomUser.objects.filter(role__in=['teacher', 'hod'], department=dept, is_active=True).count(),
            'num_subjects': Subject.objects.filter(department=dept, is_active=True).count(),
        })
    return render(request, 'academics/department_list.html', {
        'dept_data': dept_data,
    })"""

if OLD in code:
    code = code.replace(OLD, NEW)
    with open(vp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(code)
    print("  OK  academics/views.py")
else:
    print("  SKIP (already patched or different format)")

# ─────────────────────────────────────────────
# 2. PATCH: accounts/views.py admin context
# ─────────────────────────────────────────────
print("\n[2] Patching admin dashboard context...")
ap = os.path.join(BASE, 'accounts', 'views.py')
with open(ap, 'r', encoding='utf-8') as f:
    acc = f.read()

OLD2 = "'departments': Department.objects.filter(is_active=True).prefetch_related('subjects'),"
NEW2 = """'dept_data': [
            {'dept': d,
             'num_students': CustomUser.objects.filter(role='student', department=d, is_active=True).count(),
             'num_subjects': Subject.objects.filter(department=d, is_active=True).count()}
            for d in Department.objects.filter(is_active=True)
        ],"""

if OLD2 in acc:
    acc = acc.replace(OLD2, NEW2)
    with open(ap, 'w', encoding='utf-8', newline='\n') as f:
        f.write(acc)
    print("  OK  accounts/views.py")
else:
    print("  SKIP (already patched)")

# ─────────────────────────────────────────────
# 3. ALL TEMPLATES — clean UTF-8 rewrite
# ─────────────────────────────────────────────
print("\n[3] Rewriting all templates...\n")

# ── Department List ──
w('templates/academics/department_list.html', '''{% extends "base.html" %}
{% block title %}Departments{% endblock %}
{% block content %}
<div class="page-header">
    <h4><i class="bi bi-building"></i> Departments</h4>
    <a href="{% url 'department_create' %}" class="btn btn-primary btn-sm btn-icon"><i class="bi bi-plus-lg"></i> Add Department</a>
</div>
<div class="card"><div class="card-body p-0">
<table class="table table-hover">
<thead><tr><th>Code</th><th>Name</th><th>HOD</th><th>Students</th><th>Teachers</th><th>Subjects</th><th>Actions</th></tr></thead>
<tbody>
{% for item in dept_data %}
<tr>
    <td><span class="badge bg-dark">{{ item.dept.code }}</span></td>
    <td><strong>{{ item.dept.name }}</strong></td>
    <td>{% if item.dept.hod %}{{ item.dept.hod.full_name }}{% else %}<span class="text-muted">-</span>{% endif %}</td>
    <td>{{ item.num_students }}</td>
    <td>{{ item.num_teachers }}</td>
    <td>{{ item.num_subjects }}</td>
    <td><div class="d-flex gap-1">
        <a href="{% url 'department_edit' item.dept.pk %}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-pencil"></i></a>
        <a href="{% url 'department_delete' item.dept.pk %}" class="btn btn-outline-danger btn-sm"><i class="bi bi-trash"></i></a>
    </div></td>
</tr>
{% empty %}<tr><td colspan="7"><div class="empty-state"><i class="bi bi-building"></i><h6>No departments yet</h6></div></td></tr>{% endfor %}
</tbody></table></div></div>
{% endblock %}
''')

# ── Teacher List ──
w('templates/academics/teacher_list.html', '''{% extends "base.html" %}
{% block title %}Teachers{% endblock %}
{% block content %}
<div class="page-header">
    <h4><i class="bi bi-person-badge"></i> Teachers</h4>
    <a href="{% url 'teacher_create' %}" class="btn btn-primary btn-sm btn-icon"><i class="bi bi-plus-lg"></i> Add Teacher</a>
</div>
<div class="card mb-3"><div class="card-body py-2">
    <form method="get" class="d-flex gap-3 align-items-center">
        <select name="department" class="form-select form-select-sm" style="max-width:220px;" onchange="this.form.submit()">
            <option value="">All Departments</option>
            {% for dept in departments %}<option value="{{ dept.id }}" {% if selected_dept == dept.id|stringformat:"d" %}selected{% endif %}>{{ dept.code }} - {{ dept.name }}</option>{% endfor %}
        </select>
        {% if selected_dept %}<a href="{% url 'teacher_list' %}" class="btn btn-outline-secondary btn-sm">Clear</a>{% endif %}
    </form>
</div></div>
<div class="card"><div class="card-body p-0">
<table class="table table-hover">
<thead><tr><th>Name</th><th>Username</th><th>Department</th><th>Role</th><th>Subjects</th><th>Actions</th></tr></thead>
<tbody>
{% for teacher in teachers %}
<tr>
    <td><strong>{{ teacher.full_name }}</strong></td>
    <td><code>{{ teacher.username }}</code></td>
    <td>{% if teacher.department %}<span class="badge bg-dark">{{ teacher.department.code }}</span>{% else %}-{% endif %}</td>
    <td>{% if teacher.role == 'hod' %}<span class="badge badge-hod badge-role">HOD</span>{% else %}<span class="badge badge-teacher badge-role">Teacher</span>{% endif %}</td>
    <td>{% for a in teacher.subject_assignments.all %}<span class="badge" style="background:var(--primary-light);color:var(--primary);">{{ a.subject.code }}</span> {% empty %}<span class="text-muted small">None</span>{% endfor %}</td>
    <td><div class="d-flex gap-1">
        <a href="{% url 'teacher_edit' teacher.pk %}" class="btn btn-outline-secondary btn-sm" title="Edit"><i class="bi bi-pencil"></i></a>
        <a href="{% url 'teacher_promote_hod' teacher.pk %}" class="btn btn-outline-warning btn-sm" title="HOD"><i class="bi bi-shield-check"></i></a>
        <a href="{% url 'teacher_reset_password' teacher.pk %}" class="btn btn-outline-info btn-sm" title="Reset Password"><i class="bi bi-key"></i></a>
        <a href="{% url 'teacher_delete' teacher.pk %}" class="btn btn-outline-danger btn-sm" title="Deactivate"><i class="bi bi-trash"></i></a>
    </div></td>
</tr>
{% empty %}<tr><td colspan="6"><div class="empty-state"><i class="bi bi-person-badge"></i><h6>No teachers yet</h6></div></td></tr>{% endfor %}
</tbody></table></div></div>
{% endblock %}
''')

# ── Teacher Promote HOD ──
w('templates/academics/teacher_promote_hod.html', '''{% extends "base.html" %}
{% block title %}HOD Management{% endblock %}
{% block content %}
<div class="page-header"><h4><i class="bi bi-shield-check"></i> HOD Management</h4></div>
<div class="row"><div class="col-md-6"><div class="card">
<div class="card-header"><h6>{{ teacher.full_name }}</h6></div>
<div class="card-body">
    <table class="table table-borderless mb-4">
        <tr><td class="text-muted" style="width:120px">Name</td><td><strong>{{ teacher.full_name }}</strong></td></tr>
        <tr><td class="text-muted">Username</td><td><code>{{ teacher.username }}</code></td></tr>
        <tr><td class="text-muted">Current Role</td><td>{% if teacher.role == 'hod' %}<span class="badge badge-hod badge-role">HOD</span>{% else %}<span class="badge badge-teacher badge-role">Teacher</span>{% endif %}</td></tr>
        <tr><td class="text-muted">Department</td><td>{% if teacher.department %}{{ teacher.department.name }}{% else %}<span class="text-danger">Not assigned</span>{% endif %}</td></tr>
    </table>
    {% if teacher.role == 'teacher' %}
        {% if teacher.department %}
            {% if teacher.department.hod and teacher.department.hod != teacher %}
            <div class="alert alert-warning"><i class="bi bi-exclamation-triangle"></i> <strong>{{ teacher.department.name }}</strong> already has HOD: <strong>{{ teacher.department.hod.full_name }}</strong>. Promoting will demote the current HOD.</div>
            {% endif %}
            <form method="post">{% csrf_token %}<input type="hidden" name="action" value="promote">
            <button type="submit" class="btn btn-success btn-icon" onclick="return confirm('Promote to HOD?')"><i class="bi bi-arrow-up-circle"></i> Promote to HOD of {{ teacher.department.code }}</button></form>
        {% else %}
            <div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> No department assigned. Edit the teacher first.</div>
        {% endif %}
    {% elif teacher.role == 'hod' %}
        <div class="alert alert-info"><i class="bi bi-info-circle"></i> Currently HOD of <strong>{{ teacher.department.name }}</strong>.</div>
        <form method="post">{% csrf_token %}<input type="hidden" name="action" value="demote">
        <button type="submit" class="btn btn-warning btn-icon" onclick="return confirm('Demote to Teacher?')"><i class="bi bi-arrow-down-circle"></i> Demote to Teacher</button></form>
    {% endif %}
    <a href="{% url 'teacher_list' %}" class="btn btn-outline-secondary mt-3">Back to Teachers</a>
</div></div></div></div>
{% endblock %}
''')

# ── Subject List ──
w('templates/academics/subject_list.html', '''{% extends "base.html" %}
{% block title %}Subjects{% endblock %}
{% block content %}
<div class="page-header">
    <h4><i class="bi bi-book"></i> Subjects</h4>
    <a href="{% url 'subject_create' %}" class="btn btn-primary btn-sm btn-icon"><i class="bi bi-plus-lg"></i> Add Subject</a>
</div>
<div class="card mb-3"><div class="card-body py-2">
    <form method="get" class="d-flex gap-3 align-items-center">
        <select name="department" class="form-select form-select-sm" style="max-width:220px;" onchange="this.form.submit()">
            <option value="">All Departments</option>
            {% for dept in departments %}<option value="{{ dept.id }}" {% if selected_dept == dept.id|stringformat:"d" %}selected{% endif %}>{{ dept.code }} - {{ dept.name }}</option>{% endfor %}
        </select>
        <select name="semester" class="form-select form-select-sm" style="max-width:160px;" onchange="this.form.submit()">
            <option value="">All Semesters</option>
            <option value="1" {% if selected_sem == "1" %}selected{% endif %}>Sem 1</option>
            <option value="2" {% if selected_sem == "2" %}selected{% endif %}>Sem 2</option>
            <option value="3" {% if selected_sem == "3" %}selected{% endif %}>Sem 3</option>
            <option value="4" {% if selected_sem == "4" %}selected{% endif %}>Sem 4</option>
            <option value="5" {% if selected_sem == "5" %}selected{% endif %}>Sem 5</option>
            <option value="6" {% if selected_sem == "6" %}selected{% endif %}>Sem 6</option>
            <option value="7" {% if selected_sem == "7" %}selected{% endif %}>Sem 7</option>
            <option value="8" {% if selected_sem == "8" %}selected{% endif %}>Sem 8</option>
        </select>
        {% if selected_dept or selected_sem %}<a href="{% url 'subject_list' %}" class="btn btn-outline-secondary btn-sm">Clear</a>{% endif %}
    </form>
</div></div>
<div class="card"><div class="card-body p-0">
<table class="table table-hover">
<thead><tr><th>Code</th><th>Subject</th><th>Department</th><th>Semester</th><th>Credits</th><th>Teacher</th><th>Actions</th></tr></thead>
<tbody>
{% for subject in subjects %}
<tr>
    <td><span class="badge bg-dark">{{ subject.code }}</span></td>
    <td><strong>{{ subject.name }}</strong></td>
    <td>{{ subject.department.code }}</td>
    <td>Sem {{ subject.semester }}</td>
    <td>{{ subject.credit_hours }}</td>
    <td>{% with t=subject.teacher %}{% if t %}{{ t.full_name }}{% else %}<span class="text-danger small"><i class="bi bi-exclamation-circle"></i> Not assigned</span>{% endif %}{% endwith %}</td>
    <td><div class="d-flex gap-1">
        <a href="{% url 'subject_edit' subject.pk %}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-pencil"></i></a>
        <a href="{% url 'subject_delete' subject.pk %}" class="btn btn-outline-danger btn-sm"><i class="bi bi-trash"></i></a>
    </div></td>
</tr>
{% empty %}<tr><td colspan="7"><div class="empty-state"><i class="bi bi-book"></i><h6>No subjects found</h6></div></td></tr>{% endfor %}
</tbody></table></div></div>
{% endblock %}
''')

# ── Student List ──
w('templates/academics/student_list.html', '''{% extends "base.html" %}
{% block title %}Students{% endblock %}
{% block content %}
<div class="page-header">
    <h4><i class="bi bi-people"></i> Students <small class="text-muted fw-normal ms-2">({{ total_students }})</small></h4>
    <a href="{% url 'student_create' %}" class="btn btn-primary btn-sm btn-icon"><i class="bi bi-plus-lg"></i> Add Student</a>
</div>
<div class="card mb-3"><div class="card-body py-2">
    <form method="get" class="d-flex gap-3 align-items-center">
        <select name="department" class="form-select form-select-sm" style="max-width:220px;" onchange="this.form.submit()">
            <option value="">All Departments</option>
            {% for dept in departments %}<option value="{{ dept.id }}" {% if selected_dept == dept.id|stringformat:"d" %}selected{% endif %}>{{ dept.code }} - {{ dept.name }}</option>{% endfor %}
        </select>
        <select name="semester" class="form-select form-select-sm" style="max-width:160px;" onchange="this.form.submit()">
            <option value="">All Semesters</option>
            <option value="1" {% if selected_sem == "1" %}selected{% endif %}>Sem 1</option>
            <option value="2" {% if selected_sem == "2" %}selected{% endif %}>Sem 2</option>
            <option value="3" {% if selected_sem == "3" %}selected{% endif %}>Sem 3</option>
            <option value="4" {% if selected_sem == "4" %}selected{% endif %}>Sem 4</option>
            <option value="5" {% if selected_sem == "5" %}selected{% endif %}>Sem 5</option>
            <option value="6" {% if selected_sem == "6" %}selected{% endif %}>Sem 6</option>
            <option value="7" {% if selected_sem == "7" %}selected{% endif %}>Sem 7</option>
            <option value="8" {% if selected_sem == "8" %}selected{% endif %}>Sem 8</option>
        </select>
        {% if selected_dept or selected_sem %}<a href="{% url 'student_list' %}" class="btn btn-outline-secondary btn-sm">Clear</a>{% endif %}
    </form>
</div></div>
<div class="card"><div class="card-body p-0">
<table class="table table-hover">
<thead><tr><th>#</th><th>Roll No</th><th>Name</th><th>Department</th><th>Semester</th><th>Face Enrolled</th><th>Actions</th></tr></thead>
<tbody>
{% for item in student_data %}
<tr>
    <td class="text-muted">{{ forloop.counter }}</td>
    <td><strong>{{ item.user.roll_no }}</strong></td>
    <td>{{ item.user.full_name }}</td>
    <td>{% if item.user.department %}<span class="badge bg-dark">{{ item.user.department.code }}</span>{% else %}-{% endif %}</td>
    <td>Sem {{ item.user.semester|default:"-" }}</td>
    <td>{% if item.has_embedding %}<span class="badge badge-present"><i class="bi bi-check-circle"></i> Enrolled</span>{% else %}<span class="badge badge-absent"><i class="bi bi-x-circle"></i> Not Enrolled</span>{% endif %}</td>
    <td><div class="d-flex gap-1">
        <a href="{% url 'student_edit' item.user.pk %}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-pencil"></i></a>
        <a href="{% url 'student_reset_password' item.user.pk %}" class="btn btn-outline-info btn-sm"><i class="bi bi-key"></i></a>
        <a href="{% url 'student_delete' item.user.pk %}" class="btn btn-outline-danger btn-sm"><i class="bi bi-trash"></i></a>
    </div></td>
</tr>
{% empty %}<tr><td colspan="7"><div class="empty-state"><i class="bi bi-people"></i><h6>No students found</h6></div></td></tr>{% endfor %}
</tbody></table></div></div>
{% endblock %}
''')

# ── Reset Password ──
w('templates/academics/reset_password.html', '''{% extends "base.html" %}
{% block title %}Reset Password{% endblock %}
{% block content %}
<div class="page-header"><h4><i class="bi bi-key"></i> Reset Password</h4></div>
<div class="row"><div class="col-md-5"><div class="card">
<div class="card-header"><h6>{{ target_user.full_name }}</h6></div>
<div class="card-body">
    <table class="table table-borderless mb-3">
        <tr><td class="text-muted">Username</td><td><code>{{ target_user.username }}</code></td></tr>
        <tr><td class="text-muted">Role</td><td>{% if target_user.role == 'hod' %}<span class="badge badge-hod">HOD</span>{% elif target_user.role == 'teacher' %}<span class="badge badge-teacher">Teacher</span>{% else %}<span class="badge badge-student">Student</span>{% endif %}</td></tr>
    </table>
    <form method="post">{% csrf_token %}
        <div class="mb-3"><label class="form-label">New Password</label>
        <input type="password" name="new_password" class="form-control" placeholder="Min 4 characters" required minlength="4"></div>
        <div class="d-flex gap-2">
            <button type="submit" class="btn btn-primary btn-icon"><i class="bi bi-check-lg"></i> Reset</button>
            <a href="{% url cancel_url %}" class="btn btn-outline-secondary">Cancel</a>
        </div>
    </form>
</div></div></div></div>
{% endblock %}
''')

# ── Confirm Delete ──
w('templates/academics/confirm_delete.html', '''{% extends "base.html" %}
{% block title %}Confirm Deactivation{% endblock %}
{% block content %}
<div class="page-header"><h4><i class="bi bi-exclamation-triangle text-warning"></i> Confirm</h4></div>
<div class="row"><div class="col-md-6"><div class="card"><div class="card-body">
    <div class="alert alert-warning"><i class="bi bi-exclamation-triangle"></i> Deactivate <strong>{{ obj_name }}</strong> ({{ obj_type }})?</div>
    <p class="text-muted small">This hides it from active lists. Data is preserved. Reactivate via Django Admin.</p>
    <form method="post">{% csrf_token %}
        <div class="d-flex gap-2">
            <button type="submit" class="btn btn-danger btn-icon"><i class="bi bi-x-circle"></i> Deactivate</button>
            <a href="{% url cancel_url %}" class="btn btn-outline-secondary">Cancel</a>
        </div>
    </form>
</div></div></div></div>
{% endblock %}
''')

# ── Admin Dashboard ──
w('templates/dashboards/admin_dashboard.html', '''{% extends "base.html" %}
{% block title %}Admin Dashboard{% endblock %}
{% block content %}
<div class="page-header">
    <h4><i class="bi bi-grid-1x2-fill"></i> Admin Dashboard</h4>
    <span class="text-muted">{% now "l, d M Y" %}</span>
</div>
<div class="row g-3 mb-4">
    <div class="col-md-3"><div class="stat-card stat-primary"><div class="card-body d-flex align-items-center gap-3">
        <div class="stat-icon"><i class="bi bi-building"></i></div><div><div class="stat-label">Departments</div><div class="stat-value">{{ total_departments }}</div></div>
    </div></div></div>
    <div class="col-md-3"><div class="stat-card stat-info"><div class="card-body d-flex align-items-center gap-3">
        <div class="stat-icon"><i class="bi bi-person-badge-fill"></i></div><div><div class="stat-label">Teachers</div><div class="stat-value">{{ total_teachers }}</div></div>
    </div></div></div>
    <div class="col-md-3"><div class="stat-card stat-success"><div class="card-body d-flex align-items-center gap-3">
        <div class="stat-icon"><i class="bi bi-people-fill"></i></div><div><div class="stat-label">Students</div><div class="stat-value">{{ total_students }}</div></div>
    </div></div></div>
    <div class="col-md-3"><div class="stat-card stat-warning"><div class="card-body d-flex align-items-center gap-3">
        <div class="stat-icon"><i class="bi bi-calendar-check"></i></div><div><div class="stat-label">Today</div><div class="stat-value">{{ today_sessions }}</div>
        {% if active_sessions > 0 %}<div class="stat-change text-success"><span class="session-active-pulse"></span> {{ active_sessions }} active</div>{% endif %}</div>
    </div></div></div>
</div>
<div class="card mb-4"><div class="card-header"><h6><i class="bi bi-lightning-fill"></i> Quick Actions</h6></div><div class="card-body">
    <div class="d-flex gap-2 flex-wrap">
        <a href="{% url 'department_create' %}" class="btn btn-primary btn-sm btn-icon"><i class="bi bi-plus-lg"></i> Department</a>
        <a href="{% url 'teacher_create' %}" class="btn btn-sm btn-icon" style="background:var(--info);color:#fff;border:none;"><i class="bi bi-plus-lg"></i> Teacher</a>
        <a href="{% url 'subject_create' %}" class="btn btn-success btn-sm btn-icon"><i class="bi bi-plus-lg"></i> Subject</a>
        <a href="{% url 'student_create' %}" class="btn btn-sm btn-icon" style="background:var(--success);color:#fff;border:none;"><i class="bi bi-plus-lg"></i> Student</a>
        <a href="{% url 'enroll_page' %}" class="btn btn-sm btn-icon" style="background:#6f42c1;color:#fff;border:none;"><i class="bi bi-camera-video"></i> Enroll Faces</a>
        <a href="{% url 'admin_all_sessions' %}" class="btn btn-outline-secondary btn-sm btn-icon"><i class="bi bi-calendar-check"></i> All Sessions</a>
    </div>
</div></div>
<div class="row g-4">
    <div class="col-md-7"><div class="card">
        <div class="card-header"><h6><i class="bi bi-building"></i> Departments</h6><a href="{% url 'department_list' %}" class="btn btn-outline-secondary btn-sm">Manage</a></div>
        <div class="card-body p-0"><table class="table table-hover">
        <thead><tr><th>Code</th><th>Name</th><th>HOD</th><th>Students</th><th>Subjects</th></tr></thead>
        <tbody>
            {% for item in dept_data %}
            <tr>
                <td><span class="badge bg-dark">{{ item.dept.code }}</span></td>
                <td><strong>{{ item.dept.name }}</strong></td>
                <td>{% if item.dept.hod %}{{ item.dept.hod.full_name }}{% else %}-{% endif %}</td>
                <td>{{ item.num_students }}</td>
                <td>{{ item.num_subjects }}</td>
            </tr>
            {% empty %}<tr><td colspan="5" class="text-center text-muted py-3">No departments yet</td></tr>{% endfor %}
        </tbody></table></div>
    </div></div>
    <div class="col-md-5"><div class="card">
        <div class="card-header"><h6><i class="bi bi-clock-history"></i> Recent Sessions</h6><a href="{% url 'admin_all_sessions' %}" class="btn btn-outline-secondary btn-sm">All</a></div>
        <div class="card-body p-0"><table class="table table-hover">
        <thead><tr><th>Date</th><th>Subject</th><th>Status</th><th>Rate</th></tr></thead>
        <tbody>
            {% for s in recent_sessions %}
            <tr>
                <td>{{ s.date|date:"d M" }}</td>
                <td><strong>{{ s.subject.code }}</strong><br><small class="text-muted">{{ s.teacher.full_name }}</small></td>
                <td><span class="badge badge-{{ s.status|lower }}">{% if s.status == 'ACTIVE' %}<span class="session-active-pulse"></span>{% endif %}{{ s.get_status_display }}</span></td>
                <td>{% if s.total_students > 0 %}<strong class="{% if s.attendance_rate >= 75 %}pct-good{% elif s.attendance_rate >= 60 %}pct-avg{% else %}pct-low{% endif %}">{{ s.attendance_rate }}%</strong>{% else %}-{% endif %}</td>
            </tr>
            {% empty %}<tr><td colspan="4" class="text-center text-muted py-3">No sessions yet</td></tr>{% endfor %}
        </tbody></table></div>
    </div></div>
</div>
{% endblock %}
''')

# ── Session Detail (with camera include) ──
w('templates/attendance/session_detail.html', '''{% extends "base.html" %}
{% block title %}Session - {{ session.subject.code }}{% endblock %}
{% block content %}
<div class="page-header">
    <div>
        <h4>{{ session.subject.name }}
            {% if session.status == 'ACTIVE' %}<span class="badge badge-active ms-2"><span class="session-active-pulse"></span> LIVE</span>
            {% elif session.status == 'COMPLETED' %}<span class="badge badge-completed ms-2">Completed</span>
            {% else %}<span class="badge badge-cancelled ms-2">Cancelled</span>{% endif %}
        </h4>
        <small class="text-muted">{{ session.date|date:"l, d M Y" }} | {{ session.start_time|time:"H:i" }}{% if session.end_time %} - {{ session.end_time|time:"H:i" }}{% endif %}</small>
    </div>
    <div class="d-flex gap-2">
        {% if session.status == 'ACTIVE' %}
        <form method="post" action="{% url 'end_session' session.id %}" onsubmit="return confirm('End session? Remaining students will be marked ABSENT.');">
            {% csrf_token %}<button type="submit" class="btn btn-danger btn-sm btn-icon"><i class="bi bi-stop-circle"></i> End Session</button>
        </form>
        {% endif %}
        <a href="{% url 'export_session_csv' session.id %}" class="btn btn-outline-secondary btn-sm btn-icon"><i class="bi bi-download"></i> CSV</a>
    </div>
</div>
<div class="row g-3 mb-4">
    <div class="col-md-3"><div class="stat-card stat-success"><div class="card-body d-flex align-items-center gap-3">
        <div class="stat-icon"><i class="bi bi-check-circle"></i></div><div><div class="stat-label">Present</div><div class="stat-value">{{ present_count }}</div></div>
    </div></div></div>
    <div class="col-md-3"><div class="stat-card stat-warning"><div class="card-body d-flex align-items-center gap-3">
        <div class="stat-icon"><i class="bi bi-clock"></i></div><div><div class="stat-label">Late</div><div class="stat-value">{{ late_count }}</div></div>
    </div></div></div>
    <div class="col-md-3"><div class="stat-card stat-danger"><div class="card-body d-flex align-items-center gap-3">
        <div class="stat-icon"><i class="bi bi-x-circle"></i></div><div><div class="stat-label">Absent</div><div class="stat-value">{{ absent_count }}</div></div>
    </div></div></div>
    <div class="col-md-3"><div class="stat-card stat-primary"><div class="card-body d-flex align-items-center gap-3">
        <div class="stat-icon"><i class="bi bi-people"></i></div><div><div class="stat-label">Total</div><div class="stat-value">{{ total_count }}</div></div>
    </div></div></div>
</div>

{% include "attendance/session_detail_camera.html" %}

<div class="card">
    <div class="card-header">
        <h6><i class="bi bi-list-check"></i> Attendance Roll</h6>
        {% if session.status == 'ACTIVE' %}<small class="text-muted">Click buttons to mark manually</small>{% endif %}
    </div>
    <div class="card-body p-0">
        <table class="table table-hover">
            <thead><tr><th style="width:50px">#</th><th>Roll No</th><th>Name</th><th>Status</th><th>Time</th><th>Confidence</th><th>Method</th>{% if session.status == 'ACTIVE' %}<th style="width:180px">Actions</th>{% endif %}</tr></thead>
            <tbody>
                {% for item in student_data %}
                <tr>
                    <td class="text-muted">{{ forloop.counter }}</td>
                    <td><strong>{{ item.student.roll_no }}</strong></td>
                    <td>{{ item.student.full_name }}</td>
                    <td>{% if item.status == 'PRESENT' %}<span class="badge badge-present"><i class="bi bi-check-circle"></i> Present</span>
                        {% elif item.status == 'LATE' %}<span class="badge badge-late"><i class="bi bi-clock"></i> Late</span>
                        {% elif item.status == 'ABSENT' %}<span class="badge badge-absent"><i class="bi bi-x-circle"></i> Absent</span>
                        {% else %}<span class="badge bg-light text-secondary">Not Marked</span>{% endif %}</td>
                    <td>{% if item.time_marked %}{{ item.time_marked|time:"H:i:s" }}{% else %}-{% endif %}</td>
                    <td>{% if item.confidence %}{{ item.confidence|floatformat:3 }}{% else %}-{% endif %}</td>
                    <td>{% if item.marked_by == 'auto' %}<small class="text-info"><i class="bi bi-camera-video"></i> Auto</small>
                        {% elif item.marked_by == 'manual' %}<small class="text-secondary"><i class="bi bi-hand-index"></i> Manual</small>
                        {% else %}-{% endif %}</td>
                    {% if session.status == 'ACTIVE' %}
                    <td><div class="d-flex gap-1">
                        <a href="{% url 'mark_manual' session.id item.student.id 'present' %}" class="btn btn-sm {% if item.status == 'PRESENT' %}btn-success{% else %}btn-outline-success{% endif %}"><i class="bi bi-check"></i></a>
                        <a href="{% url 'mark_manual' session.id item.student.id 'late' %}" class="btn btn-sm {% if item.status == 'LATE' %}btn-warning{% else %}btn-outline-warning{% endif %}"><i class="bi bi-clock"></i></a>
                        <a href="{% url 'mark_manual' session.id item.student.id 'absent' %}" class="btn btn-sm {% if item.status == 'ABSENT' %}btn-danger{% else %}btn-outline-danger{% endif %}"><i class="bi bi-x"></i></a>
                    </div></td>
                    {% endif %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
''')

# ── Student Dashboard ──
w('templates/dashboards/student_dashboard.html', '''{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<div class="page-header">
    <h4><i class="bi bi-grid-1x2-fill"></i> Dashboard</h4>
    <span class="text-muted">{% if request.user.department %}{{ request.user.department.name }}{% endif %}{% if request.user.semester %} | Semester {{ request.user.semester }}{% endif %}</span>
</div>
<div class="row g-3 mb-4">
    <div class="col-md-4"><div class="stat-card {% if overall_percentage >= 75 %}stat-success{% elif overall_percentage >= 60 %}stat-warning{% else %}stat-danger{% endif %}">
        <div class="card-body text-center">
            <div class="stat-label">Overall Attendance</div>
            <div class="stat-value" style="font-size:2.5rem">{{ overall_percentage }}%</div>
            <div class="progress mt-2" style="height:6px"><div class="progress-bar {% if overall_percentage >= 75 %}progress-good{% elif overall_percentage >= 60 %}progress-avg{% else %}progress-low{% endif %}" style="width:{{ overall_percentage }}%"></div></div>
            <div class="stat-change mt-1">{{ total_present }} / {{ total_sessions }} attended</div>
        </div>
    </div></div>
    <div class="col-md-4"><div class="stat-card stat-primary"><div class="card-body text-center">
        <div class="stat-label">Subjects</div><div class="stat-value">{{ subject_stats|length }}</div>
    </div></div></div>
    <div class="col-md-4"><div class="stat-card {% if overall_percentage >= 75 %}stat-success{% else %}stat-danger{% endif %}"><div class="card-body text-center">
        <div class="stat-label">Status</div>
        <div class="stat-value" style="font-size:1.5rem">{% if overall_percentage >= 75 %}<i class="bi bi-shield-check"></i> Safe{% elif overall_percentage >= 60 %}<i class="bi bi-exclamation-triangle"></i> Warning{% else %}<i class="bi bi-shield-x"></i> Critical{% endif %}</div>
        <div class="stat-change">Min required: 75%</div>
    </div></div></div>
</div>
<div class="card">
    <div class="card-header"><h6><i class="bi bi-book"></i> Subject-wise Attendance</h6><a href="{% url 'student_attendance' %}" class="btn btn-outline-secondary btn-sm">Detailed</a></div>
    <div class="card-body p-0"><table class="table table-hover">
    <thead><tr><th>Subject</th><th class="text-center">Present</th><th class="text-center">Late</th><th class="text-center">Absent</th><th class="text-center">Total</th><th style="width:220px">Percentage</th></tr></thead>
    <tbody>
        {% for stat in subject_stats %}
        <tr>
            <td><strong>{{ stat.subject.name }}</strong><br><small class="text-muted">{{ stat.subject.code }}</small></td>
            <td class="text-center"><span class="fw-bold text-success">{{ stat.present }}</span></td>
            <td class="text-center"><span class="fw-bold text-warning">{{ stat.late }}</span></td>
            <td class="text-center"><span class="fw-bold text-danger">{{ stat.absent }}</span></td>
            <td class="text-center">{{ stat.total }}</td>
            <td>
                <div class="d-flex align-items-center gap-2">
                    <div class="progress flex-grow-1" style="height:8px"><div class="progress-bar {% if stat.percentage >= 75 %}progress-good{% elif stat.percentage >= 60 %}progress-avg{% else %}progress-low{% endif %}" style="width:{{ stat.percentage }}%"></div></div>
                    <strong class="{% if stat.percentage >= 75 %}pct-good{% elif stat.percentage >= 60 %}pct-avg{% else %}pct-low{% endif %}" style="min-width:45px;text-align:right">{{ stat.percentage }}%</strong>
                </div>
                {% if stat.percentage < 75 and stat.total > 0 %}<small class="text-danger"><i class="bi bi-exclamation-triangle"></i> Below 75%</small>{% endif %}
            </td>
        </tr>
        {% empty %}<tr><td colspan="6"><div class="empty-state"><i class="bi bi-bar-chart"></i><h6>No records yet</h6></div></td></tr>{% endfor %}
    </tbody></table></div>
</div>
{% endblock %}
''')

print("\n" + "=" * 50)
print("  ALL FIXES APPLIED!")
print("=" * 50)
print("\n  Run: python manage.py runserver")
print("  Then test all pages.\n")