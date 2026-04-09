from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, F, Q

from academics.models import Department
from accounts.models import CustomUser


class Command(BaseCommand):
    help = (
        "Validate student batch fields before enforcing non-null constraints "
        "for batch migration hardening."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-issues',
            action='store_true',
            help='Exit with error if any readiness issue is detected.',
        )

    def handle(self, *args, **options):
        fail_on_issues = options['fail_on_issues']

        students = CustomUser.objects.filter(role='student')
        total_students = students.count()

        missing_batch = students.filter(batch__isnull=True)
        missing_sequence = students.filter(batch_sequence__isnull=True)
        missing_department = students.filter(department__isnull=True)
        non_positive_sequence = students.filter(batch_sequence__isnull=False, batch_sequence__lte=0)

        batch_department_mismatch = students.filter(
            batch__isnull=False,
            department__isnull=False,
        ).exclude(batch__department_id=F('department_id'))

        duplicate_sequences = students.filter(
            batch__isnull=False,
            batch_sequence__isnull=False,
        ).values('batch_id', 'batch_sequence').annotate(c=Count('id')).filter(c__gt=1)

        departments_missing_roll_code = Department.objects.filter(
            users__role='student',
        ).filter(
            Q(roll_code__isnull=True) | Q(roll_code='')
        ).distinct()

        issues = {
            'missing_batch': missing_batch.count(),
            'missing_batch_sequence': missing_sequence.count(),
            'missing_department': missing_department.count(),
            'non_positive_sequence': non_positive_sequence.count(),
            'batch_department_mismatch': batch_department_mismatch.count(),
            'duplicate_batch_sequence': duplicate_sequences.count(),
            'departments_missing_roll_code': departments_missing_roll_code.count(),
        }

        self.stdout.write(self.style.MIGRATE_HEADING('Batch migration readiness report'))
        self.stdout.write(f'- total_students: {total_students}')
        for key, value in issues.items():
            self.stdout.write(f'- {key}: {value}')

        has_issues = any(value > 0 for value in issues.values())

        if departments_missing_roll_code.exists():
            codes = ', '.join(departments_missing_roll_code.values_list('code', flat=True))
            self.stdout.write(self.style.WARNING(f'Departments missing roll_code: {codes}'))

        if has_issues:
            self.stdout.write(self.style.WARNING(
                'Readiness check found issues. Run backfill and fix conflicts before non-null migration.'
            ))
            self.stdout.write(
                "Suggested: python manage.py backfill_student_batches --apply --auto-set-department-roll-code"
            )
            if fail_on_issues:
                raise CommandError('Batch migration readiness check failed.')
        else:
            self.stdout.write(self.style.SUCCESS('Readiness check passed. Safe to proceed with hardening migration.'))
