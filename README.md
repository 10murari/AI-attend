# AI-Attend: Face Recognition Attendance System

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/Django-5.2-green.svg)](https://www.djangoproject.com/)
[![InsightFace](https://img.shields.io/badge/InsightFace-buffalo__l-orange.svg)](https://github.com/deepinsight/insightface)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-13+-blue.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Project Structure](#-project-structure)
- [Django Apps](#-django-apps)
- [Database Models](#-database-models)
- [AI Pipeline](#-ai-pipeline)
- [Role-Based Access](#-role-based-access)
- [URL Routes](#-url-routes)
- [Requirements](#-requirements)
- [Installation & Setup](#-installation--setup)
- [Running the Project](#-running-the-project)
- [Colab Notebooks](#-colab-notebooks)
- [Configuration](#-configuration)
- [Troubleshooting](#-troubleshooting)
- [Future Enhancements](#-future-enhancements)

---

## 🎯 Overview

**AI-Attend** is a full-stack web application for automated student attendance tracking using real-time face recognition. It is built on **Django 5.2**, backed by **PostgreSQL**, and powered by the **InsightFace `buffalo_l` model** (ArcFace-based) for accurate 512-D face embeddings.

The system follows a two-phase workflow:

1. **Enrollment** — An admin uses a webcam to capture multiple face frames per student. These are processed into a 512-D centroid embedding and stored in the database.
2. **Live Attendance** — A teacher starts a session. The webcam streams frames to the backend API, which detects and recognizes faces in real time and automatically marks students present.

Teachers can also **manually override** attendance, **export session data as CSV**, and view historical sessions. Students can view their own attendance. HODs have department-level oversight. Admins manage all data.

---

## ✨ Key Features

| Feature | Details |
|--------|---------|
| 🔍 **Face Detection** | InsightFace `buffalo_l` — RetinaFace-based detector (`det_size=640×640`, `thresh=0.5`) |
| 🎭 **Face Recognition** | ArcFace 512-D L2-normalized embeddings, cosine similarity matching (`threshold=0.45`) |
| 📹 **Live Webcam API** | Browser streams base64 JPEG frames → Django JSON API → marks attendance in DB |
| 👤 **Webcam Enrollment** | Admin captures ≥3 frames per student → centroid embedding stored as binary in PostgreSQL |
| 🏫 **Role-Based Access** | Admin / HOD / Teacher / Student — each with scoped dashboards and permissions |
| 📊 **Session Management** | Teachers start/end sessions; ACTIVE → COMPLETED with present/absent/late counts |
| ✏️ **Manual Override** | Teachers can manually mark any student as PRESENT / ABSENT / LATE |
| 📥 **CSV Export** | Per-session attendance export (roll no, name, status, time, confidence, method) |
| 🗄️ **PostgreSQL Backend** | All embeddings, sessions, attendance, users stored in PostgreSQL |
| 🖥️ **Django Admin** | Full admin panel for managing all models |
| 📓 **Colab Notebooks** | Data preparation notebooks for face extraction and enrollment dataset building |

---

## 🏗️ System Architecture

```
Browser (Webcam)
       │
       │  base64 JPEG frames (POST /attendance/api/recognize/<session_id>/)
       ▼
┌─────────────────────────────────────────────┐
│              Django Web Server               │
│                                             │
│  ┌─────────────┐    ┌──────────────────┐   │
│  │  attendance │    │   enrollment     │   │
│  │   api.py    │    │   views.py       │   │
│  └──────┬──────┘    └────────┬─────────┘   │
│         │                    │             │
│         ▼                    ▼             │
│  ┌──────────────────────────────────────┐  │
│  │           AIService (Singleton)      │  │
│  │   web/ai_service.py                  │  │
│  │                                      │  │
│  │  detect_faces()  → InsightFace app   │  │
│  │  get_embedding() → 512-D ArcFace     │  │
│  │  recognize()     → cosine similarity │  │
│  │  compute_centroid() → enrollment     │  │
│  │  load_gallery()  → DB → numpy arrays │  │
│  └──────────────┬───────────────────────┘  │
│                 │                           │
│         ┌───────▼────────┐                 │
│         │  InsightFace   │                 │
│         │  buffalo_l     │                 │
│         │  (CUDA / CPU)  │                 │
│         └────────────────┘                 │
└─────────────────────────────────────────────┘
       │
       ▼
┌──────────────────┐
│   PostgreSQL DB  │
│                  │
│  CustomUser      │
│  Department      │
│  Subject         │
│  SubjectTeacher  │
│  Session         │
│  Attendance      │
│  FaceEmbedding   │
└──────────────────┘
```

---

## 📁 Project Structure

```
AI-attend/
│
├── Colab Notebooks/                    # Jupyter notebooks for data preparation
│   ├── extract_faces_enrollment.ipynb  # Extract & align faces from videos for enrollment
│   └── face_extraction.ipynb           # General face extraction utilities
│
├── data/                               # Raw dataset directory (videos, images)
│
├── src/                                # Standalone Python scripts / research code
│
└── web/                                # Django project root
    ├── manage.py
    ├── ai_service.py                   # Thread-safe InsightFace singleton
    ├── fix_all.py                      # Database migration/fix utility script
    ├── migrate_data.py                 # Data migration helper
    │
    ├── attendance_project/             # Django project settings
    │   ├── settings.py
    │   ├── urls.py
    │   ├── wsgi.py
    │   └── asgi.py
    │
    ├── accounts/                       # User management app
    │   ├── models.py       (CustomUser)
    │   ├── views.py        (login, logout, dashboard, profile)
    │   ├── forms.py
    │   ├── urls.py
    │   └── admin.py
    │
    ├── academics/                      # Academic structure app
    │   ├── models.py       (Department, Subject, SubjectTeacher)
    │   ├── views.py        (CRUD for depts, teachers, subjects, students)
    │   ├── forms.py
    │   ├── urls.py
    │   └── admin.py
    │
    ├── attendance/                     # Attendance session app
    │   ├── models.py       (Session, Attendance)
    │   ├── views.py        (teacher session management, HOD/student views)
    │   ├── api.py          (recognize_frame — real-time face recognition API)
    │   ├── urls.py
    │   └── admin.py
    │
    ├── enrollment/                     # Face enrollment app
    │   ├── models.py       (FaceEmbedding)
    │   ├── views.py        (enroll_page, enroll_process, enroll_delete)
    │   ├── urls.py
    │   └── admin.py
    │
    ├── static/                         # CSS, JS, images
    ├── templates/                      # HTML templates (Bootstrap 5)
    └── media/                          # Uploaded media / face crops
```

---

## 🧩 Django Apps

### `accounts` — User Management

Extends Django's `AbstractUser` with a **role-based system**:

```python
class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        ADMIN   = 'admin',   'Admin'
        HOD     = 'hod',     'HOD'
        TEACHER = 'teacher', 'Teacher'
        STUDENT = 'student', 'Student'

    role       = CharField(choices=Role.choices)
    full_name  = CharField(max_length=150)
    department = ForeignKey('academics.Department')
    roll_no    = CharField(unique=True)   # Students only
    semester   = PositiveIntegerField()   # Students only (1–8)
    phone      = CharField()
```

**URLs:**
| Route | View | Name |
|-------|------|------|
| `/accounts/login/` | `login_view` | `login` |
| `/accounts/logout/` | `logout_view` | `logout` |
| `/dashboard/` | `dashboard_view` | `dashboard` |
| `/profile/` | `profile_view` | `profile` |
| `/change-password/` | `change_password_view` | `change_password` |

---

### `academics` — Academic Structure

Manages the academic hierarchy: Departments → Subjects → Subject-Teacher assignments.

**Models:**
- `Department` — name, code, HOD (FK to CustomUser), is_active
- `Subject` — name, code, department, semester (1–8), credit_hours, is_active
- `SubjectTeacher` — links one teacher to one subject (one-to-one per subject)

**URLs (Admin-only CRUD):**

| Route | Description |
|-------|-------------|
| `/academics/departments/` | List departments |
| `/academics/departments/create/` | Add department |
| `/academics/departments/<pk>/edit/` | Edit department |
| `/academics/teachers/` | List teachers |
| `/academics/teachers/create/` | Add teacher |
| `/academics/teachers/<pk>/promote-hod/` | Promote to HOD |
| `/academics/subjects/` | List subjects |
| `/academics/subjects/create/` | Add subject |
| `/academics/students/` | List students |
| `/academics/students/create/` | Add student |
| `/academics/all-sessions/` | Admin view of all sessions |

---

### `attendance` — Session & Attendance Management

**Models:**

```python
class Session(models.Model):
    subject      = ForeignKey(Subject)
    teacher      = ForeignKey(CustomUser)
    department   = ForeignKey(Department)
    semester     = PositiveIntegerField()
    date         = DateField()
    start_time   = TimeField()
    end_time     = TimeField()
    status       = CharField(choices=['ACTIVE', 'COMPLETED', 'CANCELLED'])
    total_present / total_absent / total_late = PositiveIntegerField()

class Attendance(models.Model):
    session    = ForeignKey(Session)
    student    = ForeignKey(CustomUser)
    status     = CharField(choices=['PRESENT', 'ABSENT', 'LATE'])
    time_marked = TimeField()
    confidence  = FloatField()   # Face recognition cosine similarity
    marked_by   = CharField(choices=['auto', 'manual'])
```

**URLs:**

| Route | Description | Role |
|-------|-------------|------|
| `/attendance/my-subjects/` | Teacher's assigned subjects | Teacher/HOD |
| `/attendance/start-session/<subject_id>/` | Start an attendance session | Teacher/HOD |
| `/attendance/session/<session_id>/` | Live session view (webcam) | Teacher/HOD |
| `/attendance/session/<session_id>/end/` | End session, mark absents | Teacher/HOD |
| `/attendance/session/<session_id>/mark/<student_id>/<status>/` | Manual mark | Teacher/HOD |
| `/attendance/session/<session_id>/export/` | Export CSV | Teacher/HOD |
| `/attendance/session-history/` | Past sessions | Teacher/HOD |
| `/attendance/my-attendance/` | Student's own records | Student |
| `/attendance/dept-overview/` | Department attendance summary | HOD |
| `/attendance/dept-students/` | Department student list | HOD |
| `/attendance/api/recognize/<session_id>/` | **Real-time face recognition API** | Teacher/HOD |

#### Real-Time Recognition API

`POST /attendance/api/recognize/<session_id>/`

**Request:**
```json
{
  "frame": "<base64_jpg_string>"
}
```

**Response:**
```json
{
  "faces_detected": 2,
  "recognized": [
    {"roll_no": "780322", "name": "Murari", "similarity": 0.87, "status": "MARKED"},
    {"roll_no": "780306", "name": "Arkrisha", "similarity": 0.82, "status": "ALREADY_MARKED"}
  ],
  "unknown": 0
}
```

The API:
1. Decodes the base64 frame
2. Loads the gallery **filtered to only students in that session's department + semester**
3. Detects faces using InsightFace
4. Matches each face against the gallery (cosine similarity ≥ 0.45)
5. Creates an `Attendance` record with `marked_by='auto'` and stores the confidence score
6. Returns results to the browser for live UI updates

---

### `enrollment` — Face Enrollment

**Model:**

```python
class FaceEmbedding(models.Model):
    user           = OneToOneField(CustomUser)   # Student only
    embedding      = BinaryField()               # 512-D float32 (2048 bytes)
    embedding_dim  = PositiveIntegerField(default=512)
    num_samples    = PositiveIntegerField()       # Frames used
    intra_sim_mean = FloatField()                 # Quality: mean cosine similarity
    intra_sim_min  = FloatField()
    intra_sim_std  = FloatField()
    photo_path     = CharField()                  # Best face crop path
    is_active      = BooleanField(default=True)
```

**Quality Labels:**
- `Good` → `intra_sim_mean >= 0.7`
- `Fair` → `intra_sim_mean >= 0.5`
- `Poor` → `intra_sim_mean < 0.5`

**URLs:**

| Route | Description | Role |
|-------|-------------|------|
| `/enrollment/` | Webcam enrollment page | Admin |
| `/enrollment/process/` | Process captured frames API | Admin |
| `/enrollment/delete/<student_id>/` | Delete student embedding | Admin |

**Enrollment Process:**
1. Admin selects a student from the list
2. Webcam captures ≥3 frames (single face only per frame)
3. Each frame → InsightFace detection → ArcFace 512-D embedding
4. Centroid is computed and L2-normalized
5. Stored as binary in `FaceEmbedding.embedding`

---

## 🗄️ Database Models

```
CustomUser (accounts)
    │
    ├── department → Department (academics)
    │
    └── face_embedding → FaceEmbedding (enrollment)

Department (academics)
    ├── hod → CustomUser
    ├── subjects → Subject[]
    └── sessions → Session[]

Subject (academics)
    ├── department → Department
    └── teacher_assignments → SubjectTeacher[]

SubjectTeacher (academics)
    ├── teacher → CustomUser
    └── subject → Subject

Session (attendance)
    ├── subject → Subject
    ├── teacher → CustomUser
    ├── department → Department
    └── records → Attendance[]

Attendance (attendance)
    ├── session → Session
    └── student → CustomUser

FaceEmbedding (enrollment)
    └── user → CustomUser
```

---

## 🤖 AI Pipeline

### `AIService` — Thread-Safe Singleton (`web/ai_service.py`)

The `AIService` class wraps InsightFace and is instantiated **once** at startup (lazy-loaded on first use). It uses a `threading.Lock` to be safe under concurrent Django requests.

```python
from ai_service import ai_service   # Global singleton

# Detect faces in a BGR frame
faces = ai_service.detect_faces(frame)          # → list of Face objects

# Get 512-D L2-normalized ArcFace embedding
emb = ai_service.get_embedding(face)            # → np.ndarray (512,) float32

# Compute centroid from multiple embeddings (enrollment)
result = ai_service.compute_centroid(embeddings)
# → {'centroid': np.ndarray, 'num_samples': int,
#    'intra_sim_mean': float, 'intra_sim_min': float, 'intra_sim_std': float}

# Match against gallery
match = ai_service.recognize(embedding, gallery, threshold=0.45)
# gallery format: {user_id: {'embedding': np.ndarray, 'roll_no': str, 'name': str}}
# → None | {'user_id': int, 'roll_no': str, 'name': str, 'similarity': float}

# Load all active embeddings from DB
gallery = ai_service.load_gallery()
```

**InsightFace Configuration:**
```python
FaceAnalysis(
    name='buffalo_l',
    providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
)
app.prepare(ctx_id=0, det_size=(640, 640), det_thresh=0.5)
```

---

## 👥 Role-Based Access

| Role | Permissions |
|------|------------|
| **Admin** | Full access: manage departments, teachers, subjects, students; enroll faces; view all sessions |
| **HOD** | Department-level: view department sessions, students, attendance overview |
| **Teacher** | Subject-level: start/end sessions, live recognition, manual marks, export CSV |
| **Student** | Self-only: view own attendance records |

Each role gets a dedicated dashboard template:
- `dashboards/admin_dashboard.html`
- `dashboards/hod_dashboard.html`
- `dashboards/teacher_dashboard.html`
- `dashboards/student_dashboard.html`

---

## 📋 Requirements

```
python>=3.8
django>=5.2
insightface>=0.7
opencv-python>=4.5
numpy>=1.19
psycopg2-binary          # PostgreSQL adapter
django-crispy-forms
crispy-bootstrap5
```

> **Note:** The InsightFace `buffalo_l` model will be automatically downloaded on first use.

---

## ⚙️ Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/10murari/AI-attend.git
cd AI-attend
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install django insightface opencv-python numpy psycopg2-binary \
            django-crispy-forms crispy-bootstrap5
```

### 4. Set up PostgreSQL

Create a PostgreSQL database and user matching the settings:

```sql
CREATE DATABASE attendance_system;
CREATE USER attendance_admin WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE attendance_system TO attendance_admin;
```

Update `web/attendance_project/settings.py`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'attendance_system',
        'USER': 'attendance_admin',
        'PASSWORD': 'your_password',   # ← Change this
        'HOST': 'localhost',
        'PORT': '5433',                # ← Change to 5432 if needed
    }
}
```

### 5. Run migrations

```bash
cd web
python manage.py migrate
```

### 6. Create a superuser (Admin)

```bash
python manage.py createsuperuser
```

Then go to `/admin/` and set the user's `role` to `admin`.

### 7. Pre-download InsightFace model (optional)

```python
import insightface
from insightface.app import FaceAnalysis
app = FaceAnalysis(name='buffalo_l')
app.prepare(ctx_id=0, det_size=(640, 640))
```

---

## 🚀 Running the Project

```bash
cd web
python manage.py runserver
```

The application will be available at **http://127.0.0.1:8000/**

**Default route:** `/` → redirects to `/dashboard/` → redirects to `/accounts/login/`

---

## 📓 Colab Notebooks

Located in `Colab Notebooks/`, these are used for **offline data preparation** before the web app is used:

| Notebook | Purpose |
|----------|---------|
| `face_extraction.ipynb` | Extract and align face images from raw video footage using InsightFace |
| `extract_faces_enrollment.ipynb` | Build an enrollment dataset — extract face images per student from phone/CCTV videos, organize into per-student folders |

These notebooks are useful when you have pre-recorded videos (phone videos, CCTV footage) and want to:
- Prepare a training/enrollment dataset offline
- Validate InsightFace detection quality before deploying the web system

---

## 🔧 Configuration

All configurable settings are in `web/attendance_project/settings.py`:

```python
# Face Recognition
RECOGNITION_THRESHOLD = 0.45    # Cosine similarity threshold for a match
INSIGHTFACE_MODEL     = 'buffalo_l'
DET_SIZE              = (640, 640)
DET_THRESH            = 0.5

# Enrollment Data
ENROLLMENT_DATA_DIR = PROJECT_ROOT / 'dataset' / 'enrollment'
FACES_DIR           = ENROLLMENT_DATA_DIR / 'faces_aligned'
GALLERY_DIR         = ENROLLMENT_DATA_DIR / 'gallery'

# Timezone
TIME_ZONE = 'Asia/Kathmandu'
```

---

## 🛠️ Troubleshooting

### GPU not detected / CUDA error
The `AIService` falls back to CPU automatically:
```python
providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
```
To force CPU:
```python
# In web/ai_service.py, change to:
providers=['CPUExecutionProvider']
```

### InsightFace model not found
Run the pre-download step (see Installation step 7) or ensure you have internet access on first run.

### Low recognition accuracy
Check enrollment quality in Django Admin → `FaceEmbedding`:
- `quality_label` should be **Good** (intra_sim_mean ≥ 0.7)
- Re-enroll students with `quality_label = Poor` under better lighting

### PostgreSQL connection refused
- Verify PostgreSQL is running
- Check that `PORT` in `settings.py` matches your PostgreSQL installation (default is `5432`, not `5433`)

### "No face detected" during enrollment
- Ensure only **one face** is in frame during enrollment (multi-face frames are skipped)
- Improve lighting and camera angle
- Minimum **3 valid frames** required to compute a centroid

### Static files not loading
```bash
python manage.py collectstatic
```

---

## 🔮 Future Enhancements

- [ ] Real-time WebSocket-based frame streaming (Django Channels)
- [ ] Email/SMS notifications for low attendance
- [ ] Attendance report generation (PDF)
- [ ] Multi-camera support
- [ ] REST API with DRF for mobile app integration
- [ ] Fine-grained permission management
- [ ] Late threshold configuration per session
- [ ] Bulk student import via CSV

---

## 🙏 Acknowledgments

- [InsightFace](https://github.com/deepinsight/insightface) — `buffalo_l` model (RetinaFace + ArcFace)
- [Django](https://www.djangoproject.com/) — Web framework
- [OpenCV](https://opencv.org/) — Image/video processing
- [Bootstrap 5](https://getbootstrap.com/) — Frontend UI

---

**Repository:** [10murari/AI-attend](https://github.com/10murari/AI-attend)  
**Last Updated:** February 2026