import json
import base64
import cv2
import numpy as np
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from accounts.models import CustomUser
from .models import FaceEmbedding

logger = logging.getLogger(__name__)


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != 'admin':
            messages.error(request, 'Admin access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ==============================================================
# ENROLLMENT PAGE (webcam UI)
# ==============================================================

@login_required
@admin_required
def enroll_page(request):
    """Page with webcam for face enrollment."""
    students = CustomUser.objects.filter(
        role='student', is_active=True
    ).select_related('department').order_by('roll_no')

    # Check who already has embeddings
    enrolled_ids = set(
        FaceEmbedding.objects.filter(is_active=True).values_list('user_id', flat=True)
    )

    student_data = []
    for s in students:
        student_data.append({
            'id': s.id,
            'roll_no': s.roll_no,
            'name': s.full_name,
            'department': s.department.code if s.department else '—',
            'semester': s.semester or '—',
            'enrolled': s.id in enrolled_ids,
        })

    return render(request, 'enrollment/enroll_page.html', {
        'students': student_data,
    })


# ==============================================================
# API: Process enrollment frames
# ==============================================================

@login_required
@require_POST
def enroll_process(request):
    """
    Receive captured frames, detect faces, compute embedding.

    Expects JSON:
    {
        "student_id": 123,
        "frames": ["base64_jpg_1", "base64_jpg_2", ...]
    }
    """
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        frames_b64 = data.get('frames', [])

        if not student_id or not frames_b64:
            return JsonResponse({'error': 'Missing student_id or frames'}, status=400)

        student = get_object_or_404(CustomUser, pk=student_id, role='student')

        if len(frames_b64) < 3:
            return JsonResponse({'error': 'Need at least 3 frames'}, status=400)

        # Import AI service
        from ai_service import ai_service

        embeddings = []
        det_scores = []
        best_face_img = None
        best_det_score = 0

        for i, b64 in enumerate(frames_b64):
            # Decode base64 → image
            try:
                img_bytes = base64.b64decode(b64.split(',')[-1] if ',' in b64 else b64)
                img_array = np.frombuffer(img_bytes, dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            except Exception as e:
                logger.warning(f"Frame {i} decode error: {e}")
                continue

            if frame is None:
                continue

            # Detect faces
            faces = ai_service.detect_faces(frame)

            if len(faces) == 0:
                continue
            if len(faces) > 1:
                # Multiple faces — skip this frame
                continue

            face = faces[0]
            emb = ai_service.get_embedding(face)
            embeddings.append(emb)
            det_scores.append(float(face.det_score))

            # Track best face for reference photo
            if face.det_score > best_det_score:
                best_det_score = face.det_score
                # Crop aligned face
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                # Add padding
                h, w = frame.shape[:2]
                pad = 20
                x1 = max(0, x1 - pad)
                y1 = max(0, y1 - pad)
                x2 = min(w, x2 + pad)
                y2 = min(h, y2 + pad)
                best_face_img = frame[y1:y2, x1:x2]

        if len(embeddings) < 3:
            return JsonResponse({
                'error': f'Only {len(embeddings)} valid face(s) detected from {len(frames_b64)} frames. '
                         f'Need at least 3. Make sure only one face is visible.'
            }, status=400)

        # Check for duplicate face (different person)
        gallery = ai_service.load_gallery()
        # Exclude current student from duplicate check
        gallery_check = {uid: data for uid, data in gallery.items() if uid != student.id}

        test_emb = embeddings[0]
        dup_match = ai_service.recognize(test_emb, gallery_check, threshold=0.45)
        if dup_match:
            return JsonResponse({
                'error': f'This face matches existing student: '
                         f'{dup_match["roll_no"]} — {dup_match["name"]} '
                         f'(similarity: {dup_match["similarity"]}). '
                         f'Same person cannot enroll under different roll numbers.'
            }, status=400)

        # Compute centroid
        result = ai_service.compute_centroid(embeddings)

        # Save reference photo
        photo_path = ''
        if best_face_img is not None:
            import os
            from django.conf import settings
            photo_dir = os.path.join(settings.MEDIA_ROOT, 'faces', student.roll_no)
            os.makedirs(photo_dir, exist_ok=True)
            photo_filename = f'{student.roll_no}_ref.jpg'
            photo_full_path = os.path.join(photo_dir, photo_filename)
            cv2.imwrite(photo_full_path, best_face_img)
            photo_path = f'faces/{student.roll_no}/{photo_filename}'

        # Save to DB
        fe, created = FaceEmbedding.objects.update_or_create(
            user=student,
            defaults={
                'embedding': result['centroid'].astype(np.float32).tobytes(),
                'embedding_dim': 512,
                'num_samples': result['num_samples'],
                'intra_sim_mean': result['intra_sim_mean'],
                'intra_sim_min': result['intra_sim_min'],
                'intra_sim_std': result['intra_sim_std'],
                'photo_path': photo_path,
                'is_active': True,
            }
        )

        return JsonResponse({
            'success': True,
            'message': f'Enrolled {student.full_name} ({student.roll_no})',
            'details': {
                'num_samples': result['num_samples'],
                'quality_mean': round(result['intra_sim_mean'], 4),
                'quality_min': round(result['intra_sim_min'], 4),
                'created': created,
            }
        })

    except Exception as e:
        logger.exception("Enrollment error")
        return JsonResponse({'error': str(e)}, status=500)


# ==============================================================
# API: Delete enrollment
# ==============================================================

@login_required
@require_POST
def enroll_delete(request, student_id):
    """Remove face embedding for a student."""
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Admin only'}, status=403)

    student = get_object_or_404(CustomUser, pk=student_id, role='student')
    deleted = FaceEmbedding.objects.filter(user=student).delete()

    return JsonResponse({
        'success': True,
        'message': f'Enrollment removed for {student.full_name} ({student.roll_no})',
    })