from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib.auth.models import User

from core.models import NotificationLog, Enrollment, HomeworkSubmission


def _send_email(to_user: User, subject: str, template: str, ctx: dict) -> bool:
    if not to_user.email:
        return False
    body = render_to_string(template, ctx)
    send_mail(
        subject, body, settings.DEFAULT_FROM_EMAIL, [to_user.email], fail_silently=True
    )
    return True


def _already_sent(event_type: str, object_id: int, user: User) -> bool:
    return NotificationLog.objects.filter(
        event_type=event_type, object_id=object_id, recipient=user
    ).exists()


def _mark_sent(event_type: str, object_id: int, user: User):
    NotificationLog.objects.get_or_create(
        event_type=event_type, object_id=object_id, recipient=user
    )


def parents_for_group(group):
    """رجّع Users لأولـياء أمور طلاب المجموعة (بدون تكرار)."""
    users = []
    seen = set()
    qs = Enrollment.objects.filter(group=group, is_active=True).select_related(
        "student__parent__user"
    )
    for e in qs:
        p = getattr(e.student.parent, "user", None)
        if p and p.id not in seen:
            users.append(
                (p, e.student)
            )  # نرجّع أول طالب للتخصيص، والباقي هنضيف أسماءهم في القالب لو حبيت
            seen.add(p.id)
    return users


# === إشعار إنشاء واجب ===
def notify_assignment_created(assignment):
    group = assignment.group
    pairs = parents_for_group(group)
    subject_obj = assignment.get_subject()
    subj_text = f" — {subject_obj.name}" if subject_obj else ""
    subject_line = f"واجب جديد{subj_text}: {assignment.title} — {assignment.group.name}"
    sent_count = 0
    for user, student in pairs:
        if _already_sent(NotificationLog.Event.ASSIGNMENT_CREATED, assignment.id, user):
            continue
        ctx = {
            "site_name": settings.SITE_NAME,
            "site_url": settings.SITE_URL,
            "assignment": assignment,
            "group": group,
            "student": student,
            "subject_obj": subject_obj,  # مجرد اسم لرسالة ألطف
        }
        subject = f"واجب جديد: {assignment.title} — {group.name}"
        if _send_email(user, subject, "emails/assignment_created.txt", ctx):
            _mark_sent(NotificationLog.Event.ASSIGNMENT_CREATED, assignment.id, user)
            sent_count += 1
    return sent_count


# === تذكير الحصة قبل ساعتين ===
def notify_session_reminder(session):
    group = session.group
    pairs = parents_for_group(group)
    sent = 0
    subject_obj = session.get_subject()
    subj_text = f" — {subject_obj.name}" if subject_obj else ""
    subject_line = f"تذكير حصة{subj_text}: {session.group.name} اليوم {session.date} الساعة {session.start_time}"

    for user, student in pairs:
        if _already_sent(NotificationLog.Event.SESSION_REMINDER, session.id, user):
            continue
        ctx = {
            "site_name": settings.SITE_NAME,
            "site_url": settings.SITE_URL,
            "session": session,
            "group": group,
            "student": student,
            "subject_obj": subject_obj,
        }
        subject = (
            f"تذكير حصة: {group.name} اليوم {session.date} الساعة {session.start_time}"
        )
        if _send_email(user, subject, "emails/session_reminder.txt", ctx):
            _mark_sent(NotificationLog.Event.SESSION_REMINDER, session.id, user)
            sent += 1
    return sent
