from datetime import timedelta
from django.utils import timezone
from celery import shared_task
from django.db.models import Q
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

from .models import ClassSession, NotificationLog, Assignment, Invoice
from .services.notify import notify_assignment_created, notify_session_reminder


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_assignment_created(self, assignment_id: int):
    a = Assignment.objects.select_related("group").get(id=assignment_id)
    notify_assignment_created(a)  # تستخدم لوجيكك الحالي للإرسال + NotificationLog


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_session_reminders_window(self):
    now = timezone.now()
    in_2h = now + timedelta(hours=2)
    qs = ClassSession.objects.select_related("group", "teacher").filter(
        Q(date=timezone.localdate()) | Q(date__lte=in_2h.date())
    )
    # فلترة بالوقت: بين الآن والـ +120 دقيقة
    sessions = [
        s
        for s in qs
        if timezone.make_aware(timezone.datetime.combine(s.date, s.start_time)) <= in_2h
        and timezone.make_aware(timezone.datetime.combine(s.date, s.start_time)) >= now
    ]
    for s in sessions:
        notify_session_reminder(s)  # تستخدم NotificationLog لمنع التكرار


@shared_task
def cleanup_expired_qr():
    from django.utils import timezone
    from .models import ClassSession

    ClassSession.objects.filter(qr_token_expires_at__lt=timezone.now()).update(
        qr_token="", qr_token_expires_at=None
    )


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def remind_overdue_invoices(self):
    today = timezone.localdate()
    overdue = Invoice.objects.filter(due_date__lt=today).exclude(status="PAID")
    for inv in overdue:
        ctx = {"invoice": inv}
        html = render_to_string("emails/invoice_overdue.html", ctx)
        msg = EmailMessage(
            subject=f"تذكير فاتورة {inv.month}/{inv.year}",
            body=html,
            to=[inv.parent.user.email] if inv.parent.user.email else [],
        )
        msg.content_subtype = "html"
        if msg.to:
            msg.send(fail_silently=True)
