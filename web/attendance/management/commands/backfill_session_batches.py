"""This code is needed if iyou ever import old session data"""


# c:/Final_Project/venv/Scripts/python.exe manage.py backfill_session_batches --fallback-single-dept-batch
# c:/Final_Project/venv/Scripts/python.exe manage.py backfill_session_batches --apply --fallback-single-dept-batch


from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from academics.models import Batch
from attendance.models import Attendance, Session


class Command(BaseCommand):
    help = (
        "Backfill Session.batch for legacy sessions. "
        "Inference priority: attendance student batches -> single active department batch fallback."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Persist changes. Default is dry-run.',
        )
        parser.add_argument(
            '--fallback-single-dept-batch',
            action='store_true',
            help='If a session has no attendance rows, assign when department has exactly one active batch.',
        )

    def _infer_batch_from_attendance(self, session):
        batch_ids = list(
            Attendance.objects.filter(session=session)
            .exclude(student__batch_id__isnull=True)
            .values_list('student__batch_id', flat=True)
        )
        if not batch_ids:
            return None, 'no-attendance-batch-data'

        counts = Counter(batch_ids)
        if len(counts) == 1:
            selected_batch_id = next(iter(counts))
            return selected_batch_id, 'attendance-single-batch'

        top_batch_id, top_count = counts.most_common(1)[0]
        if list(counts.values()).count(top_count) > 1:
            return None, f'attendance-tie-{dict(counts)}'

        return top_batch_id, f'attendance-majority-{dict(counts)}'

    def handle(self, *args, **options):
        apply_changes = options['apply']
        fallback_single_dept_batch = options['fallback_single_dept_batch']

        mode = 'APPLY' if apply_changes else 'DRY-RUN'
        self.stdout.write(self.style.WARNING(f'Running backfill_session_batches in {mode} mode'))

        sessions = Session.objects.filter(batch__isnull=True).select_related('department').order_by('id')

        stats = {
            'processed': 0,
            'updated': 0,
            'skipped_no_inference': 0,
            'skipped_cross_department': 0,
            'skipped_missing_batch_row': 0,
            'fallback_updates': 0,
        }

        with transaction.atomic():
            for session in sessions:
                stats['processed'] += 1

                inferred_batch_id, reason = self._infer_batch_from_attendance(session)

                if inferred_batch_id is None and fallback_single_dept_batch:
                    dept_batches = Batch.objects.filter(
                        department_id=session.department_id,
                        is_active=True,
                    ).order_by('-year')
                    if dept_batches.count() == 1:
                        inferred_batch_id = dept_batches.first().id
                        reason = 'fallback-single-active-dept-batch'

                if inferred_batch_id is None:
                    stats['skipped_no_inference'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"SKIP session={session.id} dept={session.department.code} sem={session.semester}: {reason}"
                        )
                    )
                    continue

                batch = Batch.objects.filter(id=inferred_batch_id).first()
                if not batch:
                    stats['skipped_missing_batch_row'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"SKIP session={session.id}: inferred batch_id={inferred_batch_id} not found"
                        )
                    )
                    continue

                if batch.department_id != session.department_id:
                    stats['skipped_cross_department'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"SKIP session={session.id}: inferred batch dept mismatch ({batch.department.code} != {session.department.code})"
                        )
                    )
                    continue

                if apply_changes:
                    session.batch = batch
                    session.save(update_fields=['batch'])

                stats['updated'] += 1
                if reason.startswith('fallback-'):
                    stats['fallback_updates'] += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"{'UPDATE' if apply_changes else 'PLAN'} session={session.id} -> batch={batch.department.code}-{batch.year} ({reason})"
                    )
                )

            if not apply_changes:
                transaction.set_rollback(True)

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Backfill summary'))
        for key, value in stats.items():
            self.stdout.write(f'- {key}: {value}')

        if not apply_changes:
            self.stdout.write(self.style.WARNING('Dry-run complete. Re-run with --apply to persist changes.'))
