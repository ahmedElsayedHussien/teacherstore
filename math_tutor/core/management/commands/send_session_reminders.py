# core/management/commands/send_session_reminders.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from core.models import ClassSession
from core.services.notify import notify_session_reminder


class Command(BaseCommand):
    help = "يرسل تذكير إيميل للحصص التي ستبدأ خلال الساعتين القادمتين."

    def add_arguments(self, parser):
        parser.add_argument(
            "--window", type=int, default=15, help="نافذة دقائق للتحقّق (افتراضي 15)."
        )

    def handle(self, *args, **opts):
        now = timezone.localtime()
        # هدفنا الحصص اللي تبدأ بعد ساعتين (± نافذة)
        target_start_min = now + timedelta(hours=2) - timedelta(minutes=opts["window"])
        target_start_max = now + timedelta(hours=2) + timedelta(minutes=opts["window"])

        # دمج date + time إلى datetime في التصفية
        # ما في حقل datetime مباشر، فنفلتر تقريبيًا ثم نتحقق يدويًا
        sessions = ClassSession.objects.filter(
            date__gte=target_start_min.date(),
            date__lte=target_start_max.date(),
        ).select_related("group")

        sent_total = 0
        for s in sessions:
            start_dt = timezone.make_aware(
                datetime.combine(s.date, s.start_time), now.tzinfo
            )
            if target_start_min <= start_dt <= target_start_max:
                sent_total += notify_session_reminder(s)

        self.stdout.write(self.style.SUCCESS(f"تم إرسال {sent_total} تذكير/تذكيرات."))
