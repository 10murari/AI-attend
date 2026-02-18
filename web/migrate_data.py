"""
Migrate existing data from old PostgreSQL tables → new Django models.

Run AFTER Django migrations:
    python manage.py shell < migrate_data.py

Or:
    python manage.py runscript migrate_data  (if django-extensions installed)
"""

import os
import sys
import django
import numpy as np

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_project.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from accounts.models import CustomUser
from academics.models import Department, Subject, SubjectTeacher
from enrollment.models import FaceEmbedding

# Your student data from the old system
STUDENT_DATA = {
    "780306": {"name": "Arkrisha",   "semester": 8},
    "780309": {"name": "Chitra",     "semester": 8},
    "780312": {"name": "Dibyam",     "semester": 8},
    "780314": {"name": "Jayadev",    "semester": 8},
    "780315": {"name": "Jina",       "semester": 8},
    "780317": {"name": "Kripesh",    "semester": 8},
    "780322": {"name": "Murari",     "semester": 8},
    "780324": {"name": "Nimesh",     "semester": 8},
    "780328": {"name": "Pratik",     "semester": 8},
    "780339": {"name": "Sanjib",     "semester": 8},
    "780340": {"name": "Saurav",     "semester": 8},
    "780341": {"name": "Subekshya",  "semester": 8},
    "780343": {"name": "Sumit",      "semester": 8},
    "780349": {"name": "Kiran",      "semester": 8},
}

GALLERY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'dataset', 'enrollment', 'gallery'
)
EMBEDDINGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'dataset', 'enrollment', 'embeddings'
)
FACES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'dataset', 'enrollment', 'faces_aligned'
)


def migrate():
    print("=" * 60)
    print("  DATA MIGRATION → Django Models")
    print("=" * 60)

    # --- 1. Create Department ---
    dept, created = Department.objects.get_or_create(
        code='COMP',
        defaults={'name': 'Computer Engineering'}
    )
    print(f"\n[1] Department: {dept} ({'created' if created else 'exists'})")

    # --- 2. Create Admin User ---
    admin_user, created = CustomUser.objects.get_or_create(
        username='admin',
        defaults={
            'role': 'admin',
            'full_name': 'System Admin',
            'is_staff': True,
            'is_superuser': True,
        }
    )
    if created:
        admin_user.set_password('admin123')
        admin_user.save()
        print(f"[2] Admin user created (username: admin, password: admin123)")
    else:
        print(f"[2] Admin user exists")

    # --- 3. Create Students ---
    print(f"\n[3] Migrating {len(STUDENT_DATA)} students...")
    print(f"    {'Roll':<10} {'Name':<15} {'Status'}")
    print(f"    {'─'*10} {'─'*15} {'─'*10}")

    for roll_no, info in STUDENT_DATA.items():
        user, created = CustomUser.objects.get_or_create(
            username=roll_no,
            defaults={
                'role': 'student',
                'full_name': info['name'],
                'roll_no': roll_no,
                'department': dept,
                'semester': info['semester'],
            }
        )
        if created:
            user.set_password(roll_no)  # Default password = roll number
            user.save()

        print(f"    {roll_no:<10} {info['name']:<15} "
              f"{'created' if created else 'exists'}")

    # --- 4. Migrate Face Embeddings ---
    print(f"\n[4] Migrating face embeddings...")

    success = 0
    for roll_no in STUDENT_DATA:
        npz_path = os.path.join(GALLERY_DIR, f"{roll_no}_gallery.npz")
        if not os.path.exists(npz_path):
            print(f"    ⚠ No gallery file for {roll_no}")
            continue

        user = CustomUser.objects.get(username=roll_no)
        data = np.load(npz_path)
        centroid = data['centroid']

        # Normalize
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm

        # Load metadata
        meta = {}
        import json
        meta_path = os.path.join(EMBEDDINGS_DIR, roll_no, f"{roll_no}_metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)

        # Find photo
        photo_path = ''
        face_dir = os.path.join(FACES_DIR, roll_no)
        if os.path.exists(face_dir):
            crops = sorted([f for f in os.listdir(face_dir) if f.endswith('.jpg')])
            if crops:
                det_scores = meta.get('det_scores', [])
                if det_scores and len(det_scores) == len(crops):
                    best_idx = int(np.argmax(det_scores))
                else:
                    best_idx = len(crops) // 2
                photo_path = os.path.join(face_dir, crops[best_idx])

        # Create or update
        embedding_obj, created = FaceEmbedding.objects.update_or_create(
            user=user,
            defaults={
                'embedding': centroid.astype(np.float32).tobytes(),
                'embedding_dim': 512,
                'num_samples': meta.get('num_faces', data['embeddings'].shape[0]),
                'intra_sim_mean': meta.get('intra_similarity_mean'),
                'intra_sim_min': meta.get('intra_similarity_min'),
                'intra_sim_std': meta.get('intra_similarity_std'),
                'photo_path': photo_path,
                'is_active': True,
            }
        )

        # Verify
        loaded = embedding_obj.get_embedding()
        sim = float(np.dot(centroid, loaded))
        status = "✓" if sim > 0.9999 else "⚠"
        print(f"    {roll_no}: {status} sim={sim:.6f} | "
              f"{meta.get('num_faces', '?')} faces | "
              f"{'created' if created else 'updated'}")
        success += 1

    # --- 5. Summary ---
    print(f"\n{'=' * 60}")
    print(f"  MIGRATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Department:  {Department.objects.count()}")
    print(f"  Users:       {CustomUser.objects.count()}")
    print(f"    Admin:     {CustomUser.objects.filter(role='admin').count()}")
    print(f"    Students:  {CustomUser.objects.filter(role='student').count()}")
    print(f"  Embeddings:  {FaceEmbedding.objects.count()}")
    print(f"")
    print(f"  Login credentials:")
    print(f"    Admin:   username=admin, password=admin123")
    print(f"    Students: username=<roll_no>, password=<roll_no>")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    migrate()