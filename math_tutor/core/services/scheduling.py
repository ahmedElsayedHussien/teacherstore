# core/services/scheduling.py
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from core.models import WeeklyScheduleBlock, ClassSession, Group


def _daterange(start_date, end_date):
    cur = start_date
    while cur <= end_date:
        yield cur
        cur += timedelta(days=1)


def generate_sessions_for_range(start_date, end_date, teacher=None):
    """
    يولّد ClassSession من WeeklyScheduleBlock ضمن مدى تواريخ محدد.
    - يحترم academic_year (ضمن المدة ومفعّل).
    - يتجنب التكرار (unique_together على group/date/start_time).
    - ينسخ is_online/location/meeting_link من البلوك.
    - لو teacher محدد: يفلتر على مجموعات هذا المدرّس فقط.
    يرجّع عدد الحصص المنشأة.
    """
    created_count = 0
    # weekday: 1=Mon..7=Sun في الموديل، و weekday() في بايثون: Mon=0..Sun=6
    weekday_map = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7}

    # فلترة المجموعات (اختياريًا على المدرّس)
    groups_qs = Group.objects.all()
    if teacher is not None:
        groups_qs = groups_qs.filter(teacher=teacher)

    # نحضّر بلوكات الجداول لهذه المجموعات فقط
    blocks = WeeklyScheduleBlock.objects.filter(group__in=groups_qs).select_related(
        "group", "group__academic_year"
    )

    # نشتغل على كل يوم ونسقطه على البلوكات المطابقة
    for d in _daterange(start_date, end_date):
        weekday_val = weekday_map[d.weekday()]

        # بلوكات نفس اليوم
        day_blocks = [b for b in blocks if b.weekday == weekday_val]

        for b in day_blocks:
            ay = b.group.academic_year
            # تحقّق أن التاريخ داخل السنة ومفعّلة
            if not ay.is_active or not (ay.start_date <= d <= ay.end_date):
                continue

            defaults = {
                "teacher": b.group.teacher,
                "start_time": b.start_time,
                "end_time": b.end_time,
                "is_online": b.is_online,
                "meeting_link": b.meeting_link,
                "topic": "",  # يقدر يضيف لاحقًا
                "notes": "",
            }
            # إنشاء أو تخطّي إن موجود
            with transaction.atomic():
                obj, created = ClassSession.objects.get_or_create(
                    group=b.group, date=d, start_time=b.start_time, defaults=defaults
                )
            if created:
                created_count += 1

    return created_count


def generate_next_7_days(teacher=None, from_today=False):
    """
    يولّد للأيام السبعة القادمة.
    - from_today=True: يبدأ من اليوم، وإلا من الغد.
    """
    today = timezone.localdate()
    start = today if from_today else (today + timedelta(days=1))
    end = start + timedelta(days=6)
    return generate_sessions_for_range(start, end, teacher=teacher)
