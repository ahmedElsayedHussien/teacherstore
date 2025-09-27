from datetime import date
from django.db.models import Q, Sum, Case, When, IntegerField
from .models import Attendance


def attendance_window_q(date_from: date, date_to: date):
    q = Q()
    if date_from:
        q &= Q(session__date__gte=date_from)
    if date_to:
        q &= Q(session__date__lte=date_to)
    return q


def annotate_attendance_counts(qs):
    """يرجع QuerySet مع أعمدة إجمالية (present/absent/late/excused/total)."""
    return qs.values(
        "student_id", "student__first_name", "student__last_name"
    ).annotate(
        present=Sum(
            Case(
                When(status=Attendance.Status.PRESENT, then=1),
                default=0,
                output_field=IntegerField(),
            )
        ),
        absent=Sum(
            Case(
                When(status=Attendance.Status.ABSENT, then=1),
                default=0,
                output_field=IntegerField(),
            )
        ),
        late=Sum(
            Case(
                When(status=Attendance.Status.LATE, then=1),
                default=0,
                output_field=IntegerField(),
            )
        ),
        excused=Sum(
            Case(
                When(status=Attendance.Status.EXCUSED, then=1),
                default=0,
                output_field=IntegerField(),
            )
        ),
        total=Sum(
            Case(
                When(
                    status__in=[
                        Attendance.Status.PRESENT,
                        Attendance.Status.ABSENT,
                        Attendance.Status.LATE,
                        Attendance.Status.EXCUSED,
                    ],
                    then=1,
                ),
                default=0,
                output_field=IntegerField(),
            )
        ),
    )


def pct(num, den):
    if not den:
        return 0
    return round((num / den) * 100, 2)
