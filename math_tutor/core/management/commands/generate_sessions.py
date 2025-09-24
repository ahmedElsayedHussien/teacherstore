# core/management/commands/generate_sessions.py
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.services.scheduling import generate_sessions_for_range, generate_next_7_days
from core.models import TeacherProfile


class Command(BaseCommand):
    help = "توليد حصص (ClassSession) تلقائيًا من WeeklyScheduleBlock للأسبوع القادم أو لمدى محدد."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=7, help="عدد الأيام القادمة (افتراضي 7)."
        )
        parser.add_argument(
            "--from-today", action="store_true", help="ابدأ من اليوم بدل الغد."
        )
        parser.add_argument(
            "--teacher-username", type=str, help="فلترة على مدرّس محدد (username)."
        )
        parser.add_argument("--start", type=str, help="YYYY-MM-DD تاريخ بداية مخصص.")
        parser.add_argument("--end", type=str, help="YYYY-MM-DD تاريخ نهاية مخصص.")

    def handle(self, *args, **opts):
        teacher = None
        if opts.get("teacher_username"):
            try:
                teacher = TeacherProfile.objects.select_related("user").get(
                    user__username=opts["teacher_username"]
                )
            except TeacherProfile.DoesNotExist:
                self.stderr.write(self.style.ERROR("لم يتم العثور على المدرّس المطلوب."))
                return

        start = opts.get("start")
        end = opts.get("end")

        if start and end:
            from datetime import date

            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            created = generate_sessions_for_range(start_date, end_date, teacher=teacher)
        else:
            # الأيام القادمة
            days = max(1, int(opts["days"]))
            today = timezone.localdate()
            start_date = today if opts["from_today"] else (today + timedelta(days=1))
            end_date = start_date + timedelta(days=days - 1)
            created = generate_sessions_for_range(start_date, end_date, teacher=teacher)

        self.stdout.write(self.style.SUCCESS(f"تم إنشاء {created} حصة جديدة."))
