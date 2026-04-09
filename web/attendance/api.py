import json
import base64
import cv2
import numpy as np
import logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Session, Attendance

logger = logging.getLogger(__name__)


def current_local_time():
    return timezone.localtime(timezone.now()).time().replace(microsecond=0)


@login_required
@require_POST
def recognize_frame(request, session_id):
    """
    Receive a frame from the webcam, detect & recognize faces,
    and auto-mark attendance.

    Expects JSON:
    {
        "frame": "base64_jpg_data"
    }

    Returns:
    {
        "faces_detected": 2,
        "recognized": [
            {"roll_no": "780322", "name": "Murari", "similarity": 0.87, "status": "MARKED"},
            {"roll_no": "780306", "name": "Arkrisha", "similarity": 0.82, "status": "ALREADY_MARKED"}
        ],
        "unknown": 0
    }
    """
    session = get_object_or_404(Session, pk=session_id, status='ACTIVE')

    if session.teacher != request.user and request.user.role not in ('admin', 'hod'):
        return JsonResponse({'error': 'Not your session'}, status=403)

    try:
        data = json.loads(request.body)
        b64 = data.get('frame', '')

        if not b64:
            return JsonResponse({'error': 'No frame'}, status=400)

        # Decode
        img_bytes = base64.b64decode(b64.split(',')[-1] if ',' in b64 else b64)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if frame is None:
            return JsonResponse({'error': 'Invalid frame'}, status=400)

        from ai_service import ai_service

        # Load gallery (only students for this session's dept + semester)
        gallery = ai_service.load_gallery()

        # Filter gallery to only students in this session's class
        from accounts.models import CustomUser
        class_student_qs = CustomUser.objects.filter(
            role='student',
            department=session.department,
            semester=session.semester,
            is_active=True,
        )
        if session.batch_id:
            class_student_qs = class_student_qs.filter(batch_id=session.batch_id)

        class_students = set(class_student_qs.values_list('id', flat=True))
        session_gallery = {uid: data for uid, data in gallery.items() if uid in class_students}

        # Detect faces
        faces = ai_service.detect_faces(frame)

        recognized = []
        unknown_count = 0
        already_marked = set(
            session.records.values_list('student_id', flat=True)
        )

        for face in faces:
            emb = ai_service.get_embedding(face)
            match = ai_service.recognize(emb, session_gallery, threshold=0.45)

            if match:
                if match['user_id'] in already_marked:
                    recognized.append({
                        'roll_no': match['roll_no'],
                        'name': match['name'],
                        'similarity': match['similarity'],
                        'status': 'ALREADY_MARKED',
                    })
                else:
                    # Mark present
                    Attendance.objects.create(
                        session=session,
                        student_id=match['user_id'],
                        status='PRESENT',
                        time_marked=current_local_time(),
                        confidence=match['similarity'],
                        marked_by='auto',
                    )
                    already_marked.add(match['user_id'])
                    recognized.append({
                        'roll_no': match['roll_no'],
                        'name': match['name'],
                        'similarity': match['similarity'],
                        'status': 'MARKED',
                    })
            else:
                unknown_count += 1

        return JsonResponse({
            'faces_detected': len(faces),
            'recognized': recognized,
            'unknown': unknown_count,
            'total_marked': len(already_marked),
            'total_students': len(class_students),
        })

    except Exception as e:
        logger.exception("Recognition error")
        return JsonResponse({'error': str(e)}, status=500)