import re

from django.core.management.base import BaseCommand
from django.db import transaction

from academics.models import Batch, Department
from accounts.models import CustomUser


ROLL_PATTERN = re.compile(r'^(?P<batch_code>\d{2})(?P<dept_code>\d{2})(?P<seq>\d{2,3})$')


class Command(BaseCommand):
    help = (
        "Backfill student batch and batch_sequence from roll numbers. "
        "Expected roll format: YYDDSS (or YYDDSSS)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Persist changes. Default mode is dry-run.',
        )
        parser.add_argument(
            '--year-prefix',
            type=int,
            default=2000,
            help='Year prefix used to infer batch year from 2-digit batch code. Default: 2000',
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Update students even if batch and batch_sequence are already set.',
        )
        parser.add_argument(
            '--student-ids',
            nargs='*',
            type=int,
            help='Optional list of specific student IDs to process.',
        )
        parser.add_argument(
            '--auto-set-department-roll-code',
            action='store_true',
            help='If department roll_code is missing, set it from roll number code when safe.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        year_prefix = options['year_prefix']
        force_update = options['force_update']
        auto_set_department_roll_code = options['auto_set_department_roll_code']
        student_ids = options.get('student_ids')

        queryset = CustomUser.objects.filter(role='student').select_related('department', 'batch').order_by('id')
        if student_ids:
            queryset = queryset.filter(id__in=student_ids)

        stats = {
            'processed': 0,
            'updated': 0,
            'skipped_already_set': 0,
            'skipped_invalid_roll': 0,
            'skipped_missing_department': 0,
            'skipped_department_mismatch': 0,
            'skipped_missing_department_code': 0,
            'skipped_collision': 0,
            'errors': 0,
        }

        used_roll_codes = set(
            Department.objects.exclude(roll_code__isnull=True)
            .exclude(roll_code='')
            .values_list('roll_code', flat=True)
        )
        planned_department_codes = {}

        mode = 'APPLY' if apply_changes else 'DRY-RUN'
        self.stdout.write(self.style.WARNING(f'Running backfill in {mode} mode'))

        with transaction.atomic():
            for student in queryset:
                stats['processed'] += 1
                roll_no = (student.roll_no or '').strip()
                match = ROLL_PATTERN.match(roll_no)

                if not match:
                    stats['skipped_invalid_roll'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"SKIP student={student.id} roll='{roll_no}': invalid roll format"
                        )
                    )
                    continue

                if student.batch_id and student.batch_sequence and not force_update:
                    stats['skipped_already_set'] += 1
                    continue

                batch_code = match.group('batch_code')
                dept_code = match.group('dept_code')
                seq_raw = match.group('seq')
                sequence = int(seq_raw)
                inferred_year = year_prefix + int(batch_code)

                department = student.department
                if not department:
                    department = Department.objects.filter(roll_code=dept_code).first()
                    if not department:
                        stats['skipped_missing_department'] += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"SKIP student={student.id} roll='{roll_no}': no department and code {dept_code} not found"
                            )
                        )
                        continue

                effective_department_roll_code = department.roll_code or planned_department_codes.get(department.id)

                if not effective_department_roll_code:
                    if auto_set_department_roll_code:
                        if dept_code in used_roll_codes:
                            stats['skipped_department_mismatch'] += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f"SKIP student={student.id} roll='{roll_no}': dept code {dept_code} already used by another department"
                                )
                            )
                            continue

                        if apply_changes:
                            department.roll_code = dept_code
                            department.save(update_fields=['roll_code'])
                        else:
                            planned_department_codes[department.id] = dept_code
                        used_roll_codes.add(dept_code)
                        effective_department_roll_code = dept_code
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"{'UPDATE' if apply_changes else 'PLAN'} department={department.code} roll_code -> {dept_code}"
                            )
                        )
                    else:
                        stats['skipped_missing_department_code'] += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"SKIP student={student.id} roll='{roll_no}': department {department.code} has no roll_code"
                            )
                        )
                        continue

                if effective_department_roll_code != dept_code:
                    stats['skipped_department_mismatch'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"SKIP student={student.id} roll='{roll_no}': dept roll_code mismatch ({effective_department_roll_code} != {dept_code})"
                        )
                    )
                    continue

                batch = Batch.objects.filter(department=department, code=batch_code).first()
                if not batch:
                    batch = Batch.objects.filter(department=department, year=inferred_year).first()

                if not batch and apply_changes:
                    batch = Batch.objects.create(
                        department=department,
                        year=inferred_year,
                        code=batch_code,
                        is_active=True,
                    )
                elif not batch and not apply_changes:
                    self.stdout.write(
                        f"PLAN create batch department={department.code} year={inferred_year} code={batch_code}"
                    )

                if batch:
                    collision_qs = CustomUser.objects.filter(
                        role='student',
                        batch=batch,
                        batch_sequence=sequence,
                    ).exclude(id=student.id)
                    if collision_qs.exists():
                        stats['skipped_collision'] += 1
                        owner = collision_qs.first()
                        self.stdout.write(
                            self.style.ERROR(
                                f"SKIP student={student.id} roll='{roll_no}': sequence collision with student={owner.id}"
                            )
                        )
                        continue

                if apply_changes:
                    student.batch = batch
                    student.batch_sequence = sequence
                    if not student.department_id:
                        student.department = department
                    student.save(update_fields=['batch', 'batch_sequence', 'department'])

                stats['updated'] += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{'UPDATE' if apply_changes else 'PLAN'} student={student.id} roll='{roll_no}' "
                        f"-> batch={batch_code} dept={dept_code} seq={sequence}"
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
