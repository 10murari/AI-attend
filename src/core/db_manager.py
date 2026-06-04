"""
PostgreSQL Database Manager for Attendance System.

Handles:
  - Connection management
  - Table creation (students, sessions, attendance)
  - CRUD operations for all tables
  - Embedding serialization (numpy ↔ PostgreSQL BYTEA)

Tables:
  students   — enrolled students + face embeddings
  sessions   — attendance sessions (per class/lecture)
  attendance — per-student attendance records
"""

import psycopg2
import psycopg2.extras
import numpy as np
from datetime import datetime, date
from contextlib import contextmanager

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import DB_CONFIG


# ==============================================================
# CONNECTION MANAGEMENT
# ==============================================================

def get_connection():
    """Create a new database connection."""
    return psycopg2.connect(**DB_CONFIG)


@contextmanager
def get_cursor(commit=True):
    """
    Context manager for database operations.
    Auto-commits on success, rolls back on error.

    Usage:
        with get_cursor() as cur:
            cur.execute("INSERT INTO ...")
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ==============================================================
# TABLE CREATION
# ==============================================================

def create_tables():
    """
    Create all tables for the attendance system.
    Safe to call multiple times (IF NOT EXISTS).
    """
    with get_cursor() as cur:

        # --- Students Table ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS students (
                roll_no         VARCHAR(20) PRIMARY KEY,
                name            VARCHAR(100) NOT NULL,
                department      VARCHAR(100),
                semester        INTEGER,

                -- Face embedding data
                embedding       BYTEA NOT NULL,
                embedding_dim   INTEGER NOT NULL DEFAULT 512,
                num_samples     INTEGER,
                intra_sim_mean  REAL,
                intra_sim_min   REAL,
                intra_sim_std   REAL,

                -- Reference photo (best aligned crop)
                photo_path      TEXT,

                -- Timestamps
                enrolled_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # --- Sessions Table ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id              SERIAL PRIMARY KEY,
                session_name    VARCHAR(200) NOT NULL,
                date            DATE NOT NULL,
                start_time      TIME,
                end_time        TIME,
                subject         VARCHAR(200),
                teacher         VARCHAR(100),
                status          VARCHAR(20) DEFAULT 'ACTIVE'
                                CHECK (status IN ('ACTIVE', 'COMPLETED', 'CANCELLED')),
                total_present   INTEGER DEFAULT 0,
                total_absent    INTEGER DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # --- Attendance Table ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id              SERIAL PRIMARY KEY,
                date            DATE NOT NULL,
                session_id      INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                roll_no         VARCHAR(20) REFERENCES students(roll_no) ON DELETE CASCADE,
                name            VARCHAR(100) NOT NULL,
                status          VARCHAR(10) NOT NULL
                                CHECK (status IN ('PRESENT', 'ABSENT')),
                time_marked     TIME,
                confidence      REAL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Prevent duplicate attendance per student per session
                UNIQUE(date, session_id, roll_no)
            );
        """)

        # --- Indexes for fast queries ---
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_attendance_date
                ON attendance(date);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_attendance_session
                ON attendance(session_id);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_attendance_roll
                ON attendance(roll_no);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_date
                ON sessions(date);
        """)

    print("[DB] ✓ All tables and indexes created successfully")


# ==============================================================
# EMBEDDING SERIALIZATION
# ==============================================================

def embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """Convert numpy embedding (512-D float32) → bytes for PostgreSQL BYTEA."""
    return embedding.astype(np.float32).tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """Convert PostgreSQL BYTEA → numpy embedding (512-D float32)."""
    return np.frombuffer(data, dtype=np.float32).copy()


# ==============================================================
# STUDENT OPERATIONS
# ==============================================================

def insert_student(roll_no, name, department, semester, embedding,
                   num_samples=None, intra_sim_mean=None,
                   intra_sim_min=None, intra_sim_std=None,
                   photo_path=None):
    """Insert a new student into the database."""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO students
                (roll_no, name, department, semester, embedding, embedding_dim,
                 num_samples, intra_sim_mean, intra_sim_min, intra_sim_std, photo_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (roll_no) DO UPDATE SET
                name = EXCLUDED.name,
                department = EXCLUDED.department,
                semester = EXCLUDED.semester,
                embedding = EXCLUDED.embedding,
                num_samples = EXCLUDED.num_samples,
                intra_sim_mean = EXCLUDED.intra_sim_mean,
                intra_sim_min = EXCLUDED.intra_sim_min,
                intra_sim_std = EXCLUDED.intra_sim_std,
                photo_path = EXCLUDED.photo_path,
                updated_at = CURRENT_TIMESTAMP
        """, (
            roll_no, name, department, semester,
            psycopg2.Binary(embedding_to_bytes(embedding)),
            len(embedding),
            num_samples, intra_sim_mean, intra_sim_min, intra_sim_std,
            photo_path,
        ))
    return roll_no


def get_student(roll_no):
    """Get a single student by roll number."""
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM students WHERE roll_no = %s", (roll_no,))
        row = cur.fetchone()
        if row:
            row = dict(row)
            row['embedding'] = bytes_to_embedding(bytes(row['embedding']))
        return row


def get_all_students():
    """Get all enrolled students (without embeddings, for listing)."""
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT roll_no, name, department, semester, num_samples,
                   intra_sim_mean, enrolled_at
            FROM students
            ORDER BY roll_no
        """)
        return [dict(row) for row in cur.fetchall()]


def get_all_embeddings():
    """
    Load all student embeddings for recognition.
    Returns: dict {roll_no: {'name': str, 'embedding': np.ndarray}}
    """
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT roll_no, name, embedding FROM students ORDER BY roll_no")
        result = {}
        for row in cur.fetchall():
            row = dict(row)
            result[row['roll_no']] = {
                'name': row['name'],
                'embedding': bytes_to_embedding(bytes(row['embedding'])),
            }
        return result


def get_enrolled_count():
    """Get total number of enrolled students."""
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT COUNT(*) as count FROM students")
        return cur.fetchone()['count']


def delete_student(roll_no):
    """Delete a student (cascades to their attendance records)."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM students WHERE roll_no = %s RETURNING roll_no", (roll_no,))
        return cur.fetchone() is not None


# ==============================================================
# DUPLICATE FACE CHECK
# ==============================================================

def check_duplicate_face(embedding, exclude_roll=None, threshold=0.45):
    """
    Check if a face embedding matches any already-enrolled student.

    This prevents the same person from enrolling under multiple roll numbers.

    Args:
        embedding:    512-D numpy array (L2-normalized centroid)
        exclude_roll: roll_no to skip (for re-enrollment of same student)
        threshold:    cosine similarity above this = same person

    Returns:
        None if no match found, otherwise:
        {
            'roll_no': '780322',
            'name': 'Murari',
            'similarity': 0.87,
        }
    """
    gallery = get_all_embeddings()
    if not gallery:
        return None

    embedding = embedding.astype(np.float32)
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    best_match = None
    best_sim = -1

    for roll_no, data in gallery.items():
        # Skip the student's own entry (for re-enrollment)
        if exclude_roll and roll_no == exclude_roll:
            continue

        other_emb = data['embedding']
        sim = float(np.dot(embedding, other_emb))

        if sim > best_sim:
            best_sim = sim
            best_match = {
                'roll_no': roll_no,
                'name': data['name'],
                'similarity': round(sim, 4),
            }

    if best_match and best_match['similarity'] >= threshold:
        return best_match

    return None


# ==============================================================
# SESSION OPERATIONS
# ==============================================================

def create_session(session_name, session_date=None, subject=None, teacher=None):
    """
    Create a new attendance session.
    Returns the session ID.
    """
    if session_date is None:
        session_date = date.today()

    start_time = datetime.now().time()

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO sessions (session_name, date, start_time, subject, teacher, status)
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE')
            RETURNING id
        """, (session_name, session_date, start_time, subject, teacher))
        return cur.fetchone()['id']


def end_session(session_id):
    """
    Mark a session as completed. Sets end_time and updates counts.
    """
    with get_cursor() as cur:
        # Set end time
        cur.execute("""
            UPDATE sessions
            SET status = 'COMPLETED', end_time = %s
            WHERE id = %s
        """, (datetime.now().time(), session_id))

        # Update counts
        cur.execute("""
            UPDATE sessions SET
                total_present = (
                    SELECT COUNT(*) FROM attendance
                    WHERE session_id = %s AND status = 'PRESENT'
                ),
                total_absent = (
                    SELECT COUNT(*) FROM attendance
                    WHERE session_id = %s AND status = 'ABSENT'
                )
            WHERE id = %s
        """, (session_id, session_id, session_id))


def get_session(session_id):
    """Get a session by ID."""
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_active_sessions():
    """Get all currently active sessions."""
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT * FROM sessions
            WHERE status = 'ACTIVE'
            ORDER BY created_at DESC
        """)
        return [dict(row) for row in cur.fetchall()]


def get_sessions_by_date(session_date=None):
    """Get all sessions for a given date."""
    if session_date is None:
        session_date = date.today()

    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT * FROM sessions
            WHERE date = %s
            ORDER BY start_time
        """, (session_date,))
        return [dict(row) for row in cur.fetchall()]


# ==============================================================
# ATTENDANCE OPERATIONS
# ==============================================================

def mark_present(session_id, roll_no, name, confidence, session_date=None):
    """
    Mark a student as PRESENT for a session.
    Returns True if marked, False if already marked (duplicate).
    """
    if session_date is None:
        session_date = date.today()

    time_marked = datetime.now().time()

    with get_cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO attendance (date, session_id, roll_no, name, status, time_marked, confidence)
                VALUES (%s, %s, %s, %s, 'PRESENT', %s, %s)
            """, (session_date, session_id, roll_no, name, time_marked, confidence))
            return True
        except psycopg2.errors.UniqueViolation:
            # Already marked for this session — not an error
            return False


def mark_absent_remaining(session_id, session_date=None):
    """
    Mark all students who are NOT yet marked as ABSENT for this session.
    Called when session ends.
    Returns count of students marked absent.
    """
    if session_date is None:
        session_date = date.today()

    with get_cursor() as cur:
        # Get all enrolled students
        cur.execute("SELECT roll_no, name FROM students ORDER BY roll_no")
        all_students = cur.fetchall()

        # Get already-marked students for this session
        cur.execute("""
            SELECT roll_no FROM attendance
            WHERE session_id = %s AND date = %s
        """, (session_id, session_date))
        marked = {row['roll_no'] for row in cur.fetchall()}

        absent_count = 0
        for student in all_students:
            student = dict(student)
            if student['roll_no'] not in marked:
                cur.execute("""
                    INSERT INTO attendance (date, session_id, roll_no, name, status)
                    VALUES (%s, %s, %s, %s, 'ABSENT')
                    ON CONFLICT (date, session_id, roll_no) DO NOTHING
                """, (session_date, session_id, student['roll_no'], student['name']))
                absent_count += 1

        return absent_count


def get_attendance_by_session(session_id):
    """Get all attendance records for a session."""
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT a.*, s.session_name, s.subject
            FROM attendance a
            JOIN sessions s ON s.id = a.session_id
            WHERE a.session_id = %s
            ORDER BY a.status DESC, a.roll_no
        """, (session_id,))
        return [dict(row) for row in cur.fetchall()]


def get_attendance_by_date(session_date=None):
    """Get all attendance records for a date."""
    if session_date is None:
        session_date = date.today()

    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT a.*, s.session_name, s.subject
            FROM attendance a
            JOIN sessions s ON s.id = a.session_id
            WHERE a.date = %s
            ORDER BY s.session_name, a.status DESC, a.roll_no
        """, (session_date,))
        return [dict(row) for row in cur.fetchall()]


def get_student_attendance(roll_no, limit=50):
    """Get attendance history for a specific student."""
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT a.date, a.status, a.time_marked, a.confidence,
                   s.session_name, s.subject
            FROM attendance a
            JOIN sessions s ON s.id = a.session_id
            WHERE a.roll_no = %s
            ORDER BY a.date DESC, s.start_time DESC
            LIMIT %s
        """, (roll_no, limit))
        return [dict(row) for row in cur.fetchall()]


def get_student_attendance_summary(roll_no):
    """Get attendance percentage summary for a student."""
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total_sessions,
                COUNT(*) FILTER (WHERE status = 'PRESENT') as present_count,
                COUNT(*) FILTER (WHERE status = 'ABSENT') as absent_count
            FROM attendance
            WHERE roll_no = %s
        """, (roll_no,))
        row = dict(cur.fetchone())
        total = row['total_sessions']
        row['attendance_percentage'] = round(
            (row['present_count'] / total * 100) if total > 0 else 0, 2
        )
        return row


def is_already_marked(session_id, roll_no, session_date=None):
    """Check if a student is already marked for a session."""
    if session_date is None:
        session_date = date.today()

    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT id FROM attendance
            WHERE session_id = %s AND roll_no = %s AND date = %s
        """, (session_id, roll_no, session_date))
        return cur.fetchone() is not None


# ==============================================================
# INITIALIZATION — Run this to set up everything
# ==============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("  DATABASE SETUP")
    print("=" * 55)

    # Test connection
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        print(f"\n[DB] ✓ Connected to PostgreSQL")
        print(f"[DB]   {version[:60]}...")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"\n[DB] ✗ Connection failed: {e}")
        print(f"\nMake sure:")
        print(f"  1. PostgreSQL is running")
        print(f"  2. Database 'attendance_system' exists")
        print(f"  3. Credentials in settings.py are correct")
        sys.exit(1)

    # Create tables
    create_tables()

    # Verify
    print(f"\n[DB] Verifying tables...")
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = [row['table_name'] for row in cur.fetchall()]
        for t in tables:
            cur.execute(f"SELECT COUNT(*) as count FROM {t}")
            count = cur.fetchone()['count']
            print(f"  ✓ {t}: {count} rows")

    print(f"\n[DB] ✓ Database ready!")
    print(f"{'=' * 55}")