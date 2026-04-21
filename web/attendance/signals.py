from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from attendance.models import Attendance, Session

@receiver(post_save, sender=Session)
def send_notifications_on_session_complete(sender, instance, created, **kwargs):
    """
    Send absence notifications when session is marked as complete
    """
    if instance.status == Session.Status.COMPLETED and not instance.notification_sent:
        if getattr(settings, 'AUTO_SEND_ABSENCE_NOTIFICATIONS', True):
            instance.send_absence_notifications()


@receiver(post_save, sender=Attendance)
def update_session_counts(sender, instance, created, **kwargs):
    """
    Update session attendance counts when attendance is modified
    """
    session = instance.session
    
    session.total_present = session.records.filter(
        status=Attendance.Status.PRESENT
    ).count()
    session.total_late = session.records.filter(
        status=Attendance.Status.LATE
    ).count()
    session.total_absent = session.records.filter(
        status=Attendance.Status.ABSENT
    ).count()
    
    session.save()

