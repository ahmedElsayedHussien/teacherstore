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


# tasks.py
from datetime import datetime, timedelta
from django.db.models import Q
from django.utils import timezone
from celery import shared_task
from django.core.cache import cache  # لقفل بسيط (اختياري)
from core.models import ClassSession
from core.services.notify import notify_session_reminder


def _send_window_logic(window_minutes=120, teacher_id=None):
    """
    نفس منطقك بالضبط، مع إضافة اختيار teacher_id لتقييد الحصص.
    """
    lock_key = "send_session_reminders_window_lock"
    # قفل بسيط يمنع التشغيل المتوازي (مثلاً نصف زمن النافذة أو 60ث على الأقل)
    got_lock = cache.add(lock_key, "1", timeout=(window_minutes * 60 // 2) or 60)
    if not got_lock:
        return 0  # تنفيذ جارٍ بالفعل

    sent_total = 0
    try:
        from core.services.notify import (
            notify_session_reminder,
        )  # import محلي لتفادي الدوران

        tz = timezone.get_current_timezone()
        now = timezone.now()
        window_end = now + timedelta(minutes=window_minutes)

        start_date = timezone.localdate(now)
        end_date = timezone.localdate(window_end)
        start_time = timezone.localtime(now).timetz()
        end_time = timezone.localtime(window_end).timetz()

        cond_today = Q(date=start_date, start_time__gte=start_time)
        cond_between = Q(date__gt=start_date, date__lt=end_date)
        cond_endday = Q(date=end_date, start_time__lte=end_time)

        if start_date == end_date:
            q_date = Q(
                date=start_date, start_time__gte=start_time, start_time__lte=end_time
            )
        else:
            q_date = cond_today | cond_between | cond_endday

        qs = (
            ClassSession.objects.select_related("group", "teacher", "subject")
            .filter(q_date)
            .order_by("date", "start_time")
        )
        if teacher_id:
            qs = qs.filter(group__teacher_id=teacher_id)

        def start_dt(sess: ClassSession):
            naive = datetime.combine(sess.date, sess.start_time)
            return timezone.make_aware(naive, tz)

        sessions = [s for s in qs if now <= start_dt(s) <= window_end]

        # الإرسال (notify_session_reminder نفسه مسؤول يمنع التكرار بـ NotificationLog)
        for s in sessions:
            sent_total += notify_session_reminder(s) or 0

        return sent_total
    finally:
        cache.delete(lock_key)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
    ignore_result=True,
)

def send_session_reminders_window_task(self, window_minutes=120, teacher_id=None):
    """
    تاسك Celery الحقيقي الذي يمكنك استدعاؤه بـ .delay(window_minutes, teacher_id)
    """
    return _send_window_logic(window_minutes=window_minutes, teacher_id=teacher_id)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
    ignore_result=True,
)

def send_session_reminders_window(self, window_minutes=120):
    """
    ابعت تذكيرات للحصص اللي هتبدأ خلال النافذة الزمنية القادمة (افتراضي: 120 دقيقة).
    - يدعم عبور منتصف الليل.
    - يقلل نتائج DB قدر الإمكان.
    - قفل بسيط لمنع التنفيذ المتوازي.
    """
    # قفل بسيط لمدة النافذة + هامش صغير (ثواني)
    lock_key = "send_session_reminders_window_lock"
    got_lock = cache.add(lock_key, "1", timeout=window_minutes * 60 // 2 or 60)
    if not got_lock:
        # في تنفيذ آخر جارٍ — تخطَّ
        return

    try:
        tz = timezone.get_current_timezone()
        now = timezone.now()
        window_end = now + timedelta(minutes=window_minutes)

        # هنحوّل النافذة لثلاث حالات لتغطية عبور اليوم:
        start_date = timezone.localdate(now)
        end_date = timezone.localdate(window_end)
        start_time = timezone.localtime(now).timetz()
        end_time = timezone.localtime(window_end).timetz()

        # فلترة أدق:
        # 1) نفس يوم البداية: وقت الحصة >= الآن
        cond_today = Q(date=start_date, start_time__gte=start_time)
        # 2) الأيام الوسط (لو النافذة عدّت يوم): أي تاريخ ما بين اليومين
        cond_between = Q(date__gt=start_date, date__lt=end_date)
        # 3) يوم النهاية (لو مختلف): وقت الحصة <= نهاية النافذة
        cond_endday = Q(date=end_date, start_time__lte=end_time)

        if start_date == end_date:
            # النافذة داخل نفس اليوم
            q_date = Q(
                date=start_date, start_time__gte=start_time, start_time__lte=end_time
            )
        else:
            # النافذة عابرة لمنتصف الليل
            q_date = cond_today | cond_between | cond_endday

        qs = (
            ClassSession.objects.select_related("group", "teacher", "subject")
            .filter(q_date)
            .order_by("date", "start_time")
        )

        # تحقّق دقيق نهائي لبداية الحصة داخل النافذة (بالـ datetime aware)
        def start_dt(sess: ClassSession):
            naive = datetime.combine(sess.date, sess.start_time)
            return timezone.make_aware(naive, tz)

        sessions = [s for s in qs if now <= start_dt(s) <= window_end]

        # إبعت لكل جلسة (يعتمد على notify_session_reminder إنه يمنع التكرار عبر NotificationLog)
        for s in sessions:
            notify_session_reminder(s)

    finally:
        # فك القفل
        cache.delete(lock_key)


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
