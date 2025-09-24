# core/export_views.py
import csv
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .views import _get_teacher
from .models import Attendance, HomeworkSubmission, Group


@login_required
def export_today_attendance(request):
    teacher = _get_teacher(request.user)
    if not teacher:
        return HttpResponse("Unauthorized", status=401)

    today = timezone.localdate()
    qs = Attendance.objects.filter(
        session__teacher=teacher, session__date=today
    ).select_related("session", "student", "session__group")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="attendance_{today}.csv"'
    writer = csv.writer(response)
    writer.writerow(["التاريخ", "الوقت", "المجموعة", "الطالب", "الحالة", "ملاحظة"])
    for r in qs:
        writer.writerow(
            [
                r.session.date,
                f"{r.session.start_time}-{r.session.end_time}",
                r.session.group.name,
                f"{r.student.first_name} {r.student.last_name}",
                r.get_status_display(),
                r.note or "",
            ]
        )
    return response


@login_required
def export_ungraded_submissions(request):
    teacher = _get_teacher(request.user)
    if not teacher:
        return HttpResponse("Unauthorized", status=401)

    groups = Group.objects.filter(teacher=teacher)
    qs = HomeworkSubmission.objects.filter(
        assignment__group__in=groups, status=HomeworkSubmission.Status.SUBMITTED
    ).select_related("assignment", "student", "assignment__group")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="ungraded_submissions.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ["الواجب", "المجموعة", "الطالب", "وقت التسليم", "رابط", "ملف", "نص الإجابة"]
    )
    for r in qs:
        writer.writerow(
            [
                r.assignment.title,
                r.assignment.group.name,
                f"{r.student.first_name} {r.student.last_name}",
                timezone.localtime(r.submitted_at).strftime("%Y-%m-%d %H:%M"),
                r.link or "",
                (r.file.url if r.file else ""),
                (r.answer_text[:100].replace("\n", " ") if r.answer_text else ""),
            ]
        )
    return response
