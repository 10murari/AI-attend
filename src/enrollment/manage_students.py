"""
Student management utility.

Usage:
    python -m src.enrollment.manage_students
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.db_manager import (
    get_all_students, get_student, delete_student,
    get_enrolled_count, get_student_attendance_summary
)


def list_students():
    """List all enrolled students."""
    students = get_all_students()
    if not students:
        print("  No students enrolled.")
        return

    print(f"\n  {'Roll':<10} {'Name':<15} {'Dept':<12} {'Sem':<5} "
          f"{'Faces':<8} {'Intra Sim':<12} {'Enrolled'}")
    print(f"  {'─'*10} {'─'*15} {'─'*12} {'─'*5} {'─'*8} {'─'*12} {'─'*20}")

    for s in students:
        intra = f"{s['intra_sim_mean']:.4f}" if s.get('intra_sim_mean') else "—"
        enrolled = str(s.get('enrolled_at', ''))[:19]
        print(f"  {s['roll_no']:<10} {s['name']:<15} {s.get('department','—'):<12} "
              f"{s.get('semester','—'):<5} {s.get('num_samples','—'):<8} "
              f"{intra:<12} {enrolled}")

    print(f"\n  Total: {len(students)} students")


def student_detail(roll_no):
    """Show detailed info for one student."""
    s = get_student(roll_no)
    if not s:
        print(f"  Student {roll_no} not found.")
        return

    print(f"\n  {'═' * 45}")
    print(f"  Roll:       {s['roll_no']}")
    print(f"  Name:       {s['name']}")
    print(f"  Department: {s.get('department', '—')}")
    print(f"  Semester:   {s.get('semester', '—')}")
    print(f"  Faces:      {s.get('num_samples', '—')}")
    print(f"  Intra-sim:  mean={s.get('intra_sim_mean','—')} | "
          f"min={s.get('intra_sim_min','—')}")
    print(f"  Enrolled:   {s.get('enrolled_at', '—')}")
    print(f"  Photo:      {s.get('photo_path', '—')}")
    print(f"  Embedding:  {s['embedding'].shape} "
          f"(norm={float(np.linalg.norm(s['embedding'])):.4f})")

    # Attendance summary
    summary = get_student_attendance_summary(roll_no)
    if summary['total_sessions'] > 0:
        print(f"\n  Attendance:")
        print(f"    Sessions:  {summary['total_sessions']}")
        print(f"    Present:   {summary['present_count']}")
        print(f"    Absent:    {summary['absent_count']}")
        print(f"    Rate:      {summary['attendance_percentage']}%")
    else:
        print(f"\n  Attendance: No records yet")
    print(f"  {'═' * 45}")


def remove_student():
    """Delete a student."""
    roll_no = input("  Roll number to delete: ").strip()
    s = get_student(roll_no)
    if not s:
        print(f"  Student {roll_no} not found.")
        return

    print(f"  Deleting: {s['name']} ({roll_no})")
    print(f"  ⚠ This will also delete all their attendance records!")
    confirm = input("  Confirm? (y/n): ").strip().lower()
    if confirm == 'y':
        delete_student(roll_no)
        print(f"  ✓ Deleted {roll_no}")
    else:
        print("  Cancelled.")


def main():
    print("=" * 55)
    print("  STUDENT MANAGEMENT")
    print("=" * 55)
    print(f"  Enrolled: {get_enrolled_count()} students\n")

    while True:
        print("\n  Options:")
        print("    1. List all students")
        print("    2. Student detail")
        print("    3. Delete student")
        print("    4. Exit")

        choice = input("\n  Choice (1-4): ").strip()

        if choice == '1':
            list_students()
        elif choice == '2':
            roll = input("  Roll number: ").strip()
            student_detail(roll)
        elif choice == '3':
            remove_student()
        elif choice == '4':
            break
        else:
            print("  Invalid choice")


if __name__ == "__main__":
    main()