"""
Attendance Logger.

Handles:
  - Session lifecycle (create → mark attendance → end session)
  - Duplicate prevention (in-memory + DB constraint)
  - Absent marking at session end
  - CSV export per session
"""

import os
import sys
import csv
from datetime import datetime, date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import PROJECT_ROOT
from core.db_manager import (
    create_session, end_session, get_session,
    mark_present, mark_absent_remaining,
    get_attendance_by_session, is_already_marked,
    get_all_students
)


class AttendanceLogger:
    """
    Manages attendance for one session.

    Usage:
        logger = AttendanceLogger()
        session_id = logger.start_session("CSE301_Lecture", subject="OS")
        logger.mark(session_id, "780322", "Murari", confidence=0.85)
        logger.mark(session_id, "780306", "Arkrisha", confidence=0.91)
        summary = logger.end(session_id)
    """

    def __init__(self):
        # In-memory set for fast duplicate checking
        # (avoids DB query on every frame)
        # Key: (session_id, roll_no)
        self._marked_cache = set()
        self._session_counts = {}   # session_id → {'present': n, 'attempts': n}

    def start_session(self, session_name, subject=None, teacher=None):
        """
        Start a new attendance session.
        Returns session_id.
        """
        session_id = create_session(
            session_name=session_name,
            subject=subject,
            teacher=teacher
        )
        self._session_counts[session_id] = {'present': 0, 'attempts': 0, 'duplicates': 0}
        print(f"[ATTENDANCE] ✓ Session started: '{session_name}' (ID: {session_id})")
        print(f"[ATTENDANCE]   Subject: {subject or '—'} | Date: {date.today()}")
        return session_id

    def mark(self, session_id, roll_no, name, confidence):
        """
        Mark a student as PRESENT.

        Returns:
            'MARKED'    — successfully marked
            'DUPLICATE' — already marked this session (skipped)
        """
        self._session_counts.setdefault(
            session_id, {'present': 0, 'attempts': 0, 'duplicates': 0}
        )
        self._session_counts[session_id]['attempts'] += 1

        # Fast in-memory duplicate check
        cache_key = (session_id, roll_no)
        if cache_key in self._marked_cache:
            self._session_counts[session_id]['duplicates'] += 1
            return 'DUPLICATE'

        # Write to database (DB also has UNIQUE constraint as backup)
        success = mark_present(
            session_id=session_id,
            roll_no=roll_no,
            name=name,
            confidence=confidence
        )

        if success:
            self._marked_cache.add(cache_key)
            self._session_counts[session_id]['present'] += 1
            print(f"[ATTENDANCE] ✓ PRESENT: {roll_no} ({name}) "
                  f"| conf={confidence:.3f} "
                  f"| time={datetime.now().strftime('%H:%M:%S')}")
            return 'MARKED'
        else:
            # DB said duplicate (shouldn't happen if cache works, but safety)
            self._marked_cache.add(cache_key)
            self._session_counts[session_id]['duplicates'] += 1
            return 'DUPLICATE'

    def is_marked(self, session_id, roll_no):
        """Quick check if student already marked (from cache)."""
        return (session_id, roll_no) in self._marked_cache

    def end(self, session_id, export_csv=True):
        """
        End the session:
          1. Mark all unmarked students as ABSENT
          2. Update session status in DB
          3. Export CSV if requested
          4. Print summary

        Returns: summary dict
        """
        print(f"\n[ATTENDANCE] Ending session {session_id}...")

        # Mark absent
        absent_count = mark_absent_remaining(session_id)
        print(f"[ATTENDANCE]   Marked {absent_count} students as ABSENT")

        # End session in DB
        end_session(session_id)

        # Get full attendance
        records = get_attendance_by_session(session_id)
        session = get_session(session_id)

        present = sum(1 for r in records if r['status'] == 'PRESENT')
        absent = sum(1 for r in records if r['status'] == 'ABSENT')
        total = present + absent

        counts = self._session_counts.get(session_id, {})

        summary = {
            'session_id': session_id,
            'session_name': session['session_name'] if session else '—',
            'date': str(session['date']) if session else str(date.today()),
            'total_students': total,
            'present': present,
            'absent': absent,
            'attendance_rate': round(present / total * 100, 1) if total > 0 else 0,
            'total_recognition_attempts': counts.get('attempts', 0),
            'duplicate_detections': counts.get('duplicates', 0),
        }

        # Print summary
        print(f"\n{'═' * 55}")
        print(f"  SESSION SUMMARY")
        print(f"{'═' * 55}")
        print(f"  Session:    {summary['session_name']}")
        print(f"  Date:       {summary['date']}")
        print(f"  Present:    {present}/{total} ({summary['attendance_rate']}%)")
        print(f"  Absent:     {absent}/{total}")
        print(f"  Recognition attempts: {summary['total_recognition_attempts']}")
        print(f"  Duplicate detections: {summary['duplicate_detections']}")
        print(f"{'─' * 55}")

        # Print roll call
        print(f"\n  {'Roll':<10} {'Name':<15} {'Status':<10} {'Time':<10} {'Confidence'}")
        print(f"  {'─'*10} {'─'*15} {'─'*10} {'─'*10} {'─'*10}")
        for r in records:
            time_str = str(r['time_marked'])[:8] if r['time_marked'] else '—'
            conf_str = f"{r['confidence']:.3f}" if r['confidence'] else '—'
            status_icon = "✓" if r['status'] == 'PRESENT' else "✗"
            print(f"  {r['roll_no']:<10} {r['name']:<15} {status_icon} {r['status']:<8} "
                  f"{time_str:<10} {conf_str}")

        # CSV export
        if export_csv:
            csv_path = self.export_csv(session_id, records, session)
            if csv_path:
                summary['csv_path'] = csv_path
                print(f"\n  ✓ CSV exported: {csv_path}")

        print(f"{'═' * 55}")

        # Cleanup cache for this session
        self._marked_cache = {k for k in self._marked_cache if k[0] != session_id}

        return summary

    def export_csv(self, session_id, records=None, session=None):
        """Export attendance for a session as CSV."""
        if records is None:
            records = get_attendance_by_session(session_id)
        if session is None:
            session = get_session(session_id)

        if not records:
            return None

        # Create export directory
        export_dir = os.path.join(PROJECT_ROOT, "data", "attendance_exports")
        os.makedirs(export_dir, exist_ok=True)

        # Filename: date_sessionname.csv
        session_name = session['session_name'] if session else f"session_{session_id}"
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in session_name)
        date_str = str(session['date']) if session else str(date.today())
        filename = f"{date_str}_{safe_name}.csv"
        csv_path = os.path.join(export_dir, filename)

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date', 'Session', 'Subject', 'Roll No', 'Name',
                'Status', 'Time Marked', 'Confidence'
            ])
            for r in records:
                writer.writerow([
                    r['date'],
                    session_name,
                    session.get('subject', '') if session else '',
                    r['roll_no'],
                    r['name'],
                    r['status'],
                    str(r['time_marked'])[:8] if r['time_marked'] else '',
                    f"{r['confidence']:.4f}" if r['confidence'] else '',
                ])

        return csv_path

    def get_live_stats(self, session_id):
        """Get real-time stats for display overlay."""
        counts = self._session_counts.get(session_id, {})
        total_enrolled = len(get_all_students())
        present = counts.get('present', 0)
        return {
            'present': present,
            'total': total_enrolled,
            'remaining': total_enrolled - present,
            'rate': round(present / total_enrolled * 100, 1) if total_enrolled > 0 else 0,
        }