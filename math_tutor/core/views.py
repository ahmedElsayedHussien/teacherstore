# core/views.py
# ===== قياسية من بايثون =====
import os
import csv
from io import BytesIO
from datetime import date, timedelta
from core.tasks import notify_assignment_created
import base64, qrcode
from io import BytesIO
from urllib.parse import urlencode

# ===== طرف ثالث =====
from xhtml2pdf import pisa
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# ===== Django =====
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import (
    FileResponse,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST
from django.forms import modelformset_factory

# ===== مشروعك (local apps) =====
from .decorators import student_required
from .forms import AssignmentQuickForm, HomeworkBulkGradeForm, StudentSubmissionForm
from .models import (
    ParentProfile,
    Student,
    Enrollment,
    Group,
    Subject,
    WeeklyScheduleBlock,
    ClassSession,
    Assignment,
    HomeworkSubmission,
    MonthlyReport,
    Attendance,
    TeacherProfile,
    Invoice,
    Payment,
    NotificationLog,
)
from .services.notify import notify_session_reminder
from .services.scheduling import generate_next_7_days
from .forms import GroupForm, BulkStudentsForm, AddExistingStudentsForm

@login_required
def download_submission(request, submission_id: int):
    sub = get_object_or_404(HomeworkSubmission, id=submission_id)

    # تحقّق صلاحيات: معلّم المجموعة أو الطالب صاحب التسليم أو موظّف
    if not (_is_teacher_of_submission(request.user, sub) or _is_owner_student(request.user, sub)):
        return HttpResponseForbidden("غير مصرّح لك بتنزيل هذا التسليم.")

    # 1) لو في ملف مرفوع → نزّله مباشرة
    if sub.file:
        filename = os.path.basename(sub.file.name)
        f = sub.file.open("rb")
        resp = FileResponse(f, as_attachment=True, filename=filename)
        return resp

    # 2) لو التسليم عبارة عن رابط → حوّل المستخدم للرابط
    if sub.link:
        return HttpResponseRedirect(sub.link)

    # 3) لو الإجابة نص فقط → أنشئ ملف نصّي للتنزيل
    if sub.answer_text and sub.answer_text.strip():
        content = sub.answer_text
        resp = HttpResponse(content, content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="submission_{sub.id}.txt"'
        return resp

    # لا يوجد أي محتوى صالح للتنزيل
    return HttpResponse("لا يوجد ملف/رابط/نص في هذا التسليم.", status=404)
from django.shortcuts import render, redirect, get_object_or_404

from .models import Resource, Group, ClassSession, Subject

from .models import  ClassSession, Enrollment,Assignment, Group, Subject
import base64
from django.db.models import Sum, Q

def _get_parent(user):
    try:
        return ParentProfile.objects.get(user=user)
    except ParentProfile.DoesNotExist:
        return None


def _require_group_owner(request, group: Group):
    # المدرّس المالك فقط
    try:
        tp = request.user.teacherprofile
    except TeacherProfile.DoesNotExist:
        messages.error(request, "هذا الإجراء للمدرّسين فقط.")
        return False
    if group.teacher_id != tp.id:
        messages.error(request, "غير مصرح لك بإدارة هذه المجموعة.")
        return False
    return True


def _get_teacher(user):
    try:
        return TeacherProfile.objects.get(user=user)
    except TeacherProfile.DoesNotExist:
        return None


def _is_teacher_of_submission(user, sub: HomeworkSubmission) -> bool:
    # يسمح لمعلّم المجموعة مالك الواجب، أو staff/superuser
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    try:
        teacher = user.teacherprofile  # لو عندك اسم مختلف عدِّله
    except TeacherProfile.DoesNotExist:
        return False
    return sub.assignment.group.teacher_id == teacher.id


def _is_owner_student(user, sub: HomeworkSubmission) -> bool:
    # يسمح للطالب صاحب التسليم أيضًا (مفيد لو استدعيت اللينك من بوابة الطالب)
    try:
        student = user.student_profile.student
    except Exception:
        return False
    return sub.student_id == student.id


def parent_required(view_func):
    @login_required
    def _wrapped(request, *args, **kwargs):
        parent = _get_parent(request.user)
        if not parent:
            # لو حساب مو وليّ أمر، رجّعه للّوجين/أدمن
            return redirect("/accounts/login/")
        request.parent = parent
        return view_func(request, *args, **kwargs)

    return _wrapped


@parent_required
def parent_dashboard(request):
    parent = request.parent  # حسب الديكوريتر اللي عندنا
    today = timezone.localdate()
    next_week = today + timezone.timedelta(days=7)

    kids = Student.objects.filter(parent=parent).order_by("first_name", "last_name")

    # الحصص القادمة لأبناء وليّ الأمر خلال أسبوع
    upcoming_sessions = (
        ClassSession.objects.filter(
            group__enrollments__student__in=kids,
            date__range=(today, next_week),
        )
        .select_related("group", "subject")
        .order_by("date", "start_time")
        .distinct()[:50]
    )

    # واجبات مفتوحة (موعد نهائي بالمستقبل أو بدون موعد نهائي)
    now = timezone.now()
    open_assignments = (
        Assignment.objects.filter(group__enrollments__student__in=kids)
        .filter(Q(due_at__gte=now) | Q(due_at__isnull=True))
        .select_related("group", "subject")
        .order_by("-assigned_at")
        .distinct()[:50]
    )

    # أحدث تسليمات الأبناء
    recent_submissions = (
        HomeworkSubmission.objects.filter(student__in=kids)
        .select_related("student", "assignment", "assignment__group")
        .order_by("-submitted_at")[:50]
    )

    # أحدث تقرير لكل طالب
    last_reports_pairs = []
    for s in kids:
        rep = (
            MonthlyReport.objects.filter(student=s).order_by("-year", "-month").first()
        )
        if rep:
            last_reports_pairs.append((s, rep))

    # فواتير ومدفوعات
    recent_invoices = (
        Invoice.objects.filter(parent=parent)
        .select_related("student", "group")
        .order_by("-issued_at")[:10]
    )
    recent_payments = (
        Payment.objects.filter(invoice__parent=parent)
        .select_related("invoice", "invoice__student")
        .order_by("-received_at")[:10]
    )

    # ملخص فوترة
    # إجمالي المتبقي على كل الفواتير المفتوحة/المتأخرة (remaining = amount - sum(payments))
    # بما إن remaining property موجود في الموديل، نجيبها Python-side:
    parent_invoices_all = Invoice.objects.filter(parent=parent)
    total_due = sum((inv.remaining for inv in parent_invoices_all), Decimal("0.00"))

    total_overdue = sum(
        (
            inv.remaining
            for inv in parent_invoices_all.filter(status=Invoice.Status.OVERDUE)
        ),
        Decimal("0.00"),
    )

    month_start = today.replace(day=1)
    month_paid = Payment.objects.filter(
        invoice__parent=parent, received_at__date__gte=month_start
    ).aggregate(s=Sum("amount_egp"))["s"] or Decimal("0.00")

    open_count = parent_invoices_all.exclude(status=Invoice.Status.PAID).count()

    ctx = {
        "kids": kids,
        "today": today,
        "next_week": next_week,
        "upcoming_sessions": upcoming_sessions,
        "open_assignments": open_assignments,
        "recent_submissions": recent_submissions,
        "last_reports_pairs": last_reports_pairs,
        # فوترة
        "recent_invoices": recent_invoices,
        "recent_payments": recent_payments,
        "billing": {
            "total_due": total_due,
            "total_overdue": total_overdue,
            "month_paid": month_paid,
            "open_count": open_count,
        },
    }
    return render(request, "core/parent_dashboard.html", ctx)


@parent_required
def parent_report_view(request, student_id: int, year: int, month: int):
    """عرض تقرير شهري (HTML بسيط الآن، تقدر تحوّله PDF لاحقًا)."""
    parent = request.parent
    student = get_object_or_404(
        Student, id=student_id, parent=parent
    )  # أمان: لازم يكون ابنه
    report = get_object_or_404(MonthlyReport, student=student, year=year, month=month)

    # لو مركّب WeasyPrint لاحقًا، حوّل هذا العرض إلى PDF
    return render(
        request, "core/parent_report.html", {"student": student, "report": report}
    )


def teacher_required(view_func):
    @login_required
    def _wrapped(request, *args, **kwargs):
        teacher = _get_teacher(request.user)
        if not teacher:
            # لو المستخدم مش مدرس—ودّه للأدمن أو صفحة مناسبة
            return redirect("/admin/")
        request.teacher = teacher
        return view_func(request, *args, **kwargs)

    return _wrapped


# core/views.py (داخل نفس الفيو)
from django.db.models.functions import TruncDate, TruncMonth


@teacher_required
def teacher_dashboard(request):
    tz_today = timezone.localdate()
    tz_now = timezone.localtime()

    # فلاتر بسيطة من الكويري سترنغ
    q_group = request.GET.get("group")
    q_subject = request.GET.get("subject")
    q_status = request.GET.get("status")  # لمهام/تسليمات/فواتير… حسب القسم
    q_month = int(request.GET.get("month") or tz_today.month)
    q_year = int(request.GET.get("year") or tz_today.year)

    groups = Group.objects.filter(teacher=request.teacher).select_related(
        "academic_year", "subject"
    )
    if q_group:
        groups = groups.filter(id=q_group)

    # إحصائيات علوية
    total_groups = groups.count()
    total_students = Enrollment.objects.filter(group__in=groups, is_active=True).count()
    upcoming_count = ClassSession.objects.filter(
        group__in=groups, date__gte=tz_today
    ).count()
    due_invoices = Invoice.objects.filter(
        group__in=groups, year=q_year, month=q_month, status__in=["DUE", "OVERDUE"]
    ).count()

    # حصص قادمة (Top 10)
    sessions = (
        ClassSession.objects.filter(group__in=groups, date__gte=tz_today)
        .select_related("group", "subject")
        .order_by("date", "start_time")[:10]
    )

    # واجبات حديثة (آخر 10)
    assignments = (
        Assignment.objects.filter(group__in=groups)
        .select_related("group", "subject")
        .order_by("-assigned_at")[:10]
    )

    # تسليمات تحتاج تصحيح (آخر 10)
    subs = (
        HomeworkSubmission.objects.filter(assignment__group__in=groups)
        .select_related("student", "assignment__group", "assignment__subject")
        .order_by("-submitted_at")[:10]
    )

    # مجموعاتك مع أعداد سريعة
    group_ids = list(groups.values_list("id", flat=True))
    enroll_counts = dict(
        Enrollment.objects.filter(group_id__in=group_ids, is_active=True)
        .values("group_id")
        .annotate(c=Count("id"))
        .values_list("group_id", "c")
    )
    sess_counts = dict(
        ClassSession.objects.filter(group_id__in=group_ids, date__gte=tz_today)
        .values("group_id")
        .annotate(c=Count("id"))
        .values_list("group_id", "c")
    )

    # فواتير الشهر (مختصر)
    invoices = (
        Invoice.objects.filter(group__in=groups, year=q_year, month=q_month)
        .select_related("student", "group")
        .order_by("-status", "student__last_name")[:10]
    )

    # المواد لفلترة/عرض
    subjects = Subject.objects.filter(is_active=True).order_by("name")

    ctx = dict(
        groups=groups,
        enroll_counts=enroll_counts,
        sess_counts=sess_counts,
        sessions=sessions,
        assignments=assignments,
        subs=subs,
        invoices=invoices,
        subjects=subjects,
        q_group=q_group,
        q_subject=q_subject,
        q_status=q_status,
        q_year=q_year,
        q_month=q_month,
        total_groups=total_groups,
        total_students=total_students,
        upcoming_count=upcoming_count,
        due_invoices=due_invoices,
    )
    return render(request, "core/teacher_dashboard.html", ctx)


@teacher_required
def create_assignment(request):
    teacher = request.teacher
    if request.method != "POST":
        return redirect(reverse("core:dashboard"))

    form = AssignmentQuickForm(request.POST, request.FILES, teacher=teacher)
    if form.is_valid():
        assignment = form.save()
        transaction.on_commit(lambda: notify_assignment_created.delay(assignment.id))

        messages.success(
            request,
            f"تم إنشاء الواجب «{assignment.title}» للمجموعة «{assignment.group.name}».",
        )
        return redirect("core:assignments_list", group_id=assignment.group_id)
    else:
        # لو في أخطاء، نرجّع نفس الداشبورد ومعاه الفورم بالأخطاء
        # لازم نعيد بقية سياق الداشبورد المختصر عالأقل عشان يعرض الصفحة بدون مشاكل
        today = timezone.localdate()
        groups = Group.objects.filter(teacher=teacher).select_related("academic_year")
        total_students = (
            Enrollment.objects.filter(group__in=groups, is_active=True)
            .values("student_id")
            .distinct()
            .count()
        )
        total_groups = groups.count()
        upcoming_sessions = (
            ClassSession.objects.filter(teacher=teacher, date__gte=today)
            .select_related("group")
            .order_by("date", "start_time")[:10]
        )
        latest_assignments = (
            Assignment.objects.filter(group__in=groups)
            .annotate(submissions_count=Count("submissions"))
            .order_by("-assigned_at")[:5]
        )
        recent_ungraded_submissions = (
            HomeworkSubmission.objects.filter(
                assignment__group__in=groups, status=HomeworkSubmission.Status.SUBMITTED
            )
            .select_related("assignment", "student")
            .order_by("-submitted_at")[:8]
        )

        # قيَم سريعة ضرورية للعرض:
        today_att_qs = Attendance.objects.filter(
            session__teacher=teacher, session__date=today
        )
        today_total_att = today_att_qs.count()
        today_present = today_att_qs.filter(status=Attendance.Status.PRESENT).count()
        today_att_pct = (
            round((today_present / today_total_att) * 100, 2) if today_total_att else 0
        )

        context = {
            "teacher": teacher,
            "total_students": total_students,
            "total_groups": total_groups,
            "to_grade_count": HomeworkSubmission.objects.filter(
                assignment__group__in=groups, status=HomeworkSubmission.Status.SUBMITTED
            ).count(),
            "today_att_pct": today_att_pct,
            "today_total_att": today_total_att,
            "month_avg_grade": 0,  # ممكن تحسبها لو تحب، مو ضروري هنا
            "upcoming_sessions": upcoming_sessions,
            "latest_assignments": latest_assignments,
            "recent_ungraded_submissions": recent_ungraded_submissions,
            "today": today,
            "next_week": today + timedelta(days=7),
            "form": form,  # بالأخطاء
            # لو مركّب الرسوم البيانية، رجّع بياناتها هنا أيضًا (اختياري)
        }
        messages.error(request, "تعذّر إنشاء الواجب—فضلاً صحّح الأخطاء أسفل النموذج.")
        return render(request, "core/dashboard.html", context)


@teacher_required
@require_POST
def dashboard_generate_next_week(request):
    teacher = request.teacher

    # تحقّق سريع: عنده بلوكات جدول أساساً؟
    has_blocks = WeeklyScheduleBlock.objects.filter(group__teacher=teacher).exists()
    if not has_blocks:
        messages.warning(
            request,
            "لا توجد بلوكات جدول أسبوعية لمجموعاتك — أضفها أولًا من لوحة الإدارة.",
        )
        return redirect(reverse("core:dashboard"))

    # تنفيذ التوليد (7 أيام من بكرة)
    created = generate_next_7_days(teacher=teacher, from_today=False)
    if created:
        messages.success(request, f"تم إنشاء {created} حصة للأسبوع القادم لمجموعاتك.")
    else:
        messages.info(
            request,
            "لا توجد حصص جديدة لإضافتها (يبدو أنها مضافة مسبقًا أو لا يوجد مواعيد في هذا المدى).",
        )
    return redirect(reverse("core:dashboard"))


@teacher_required
@require_http_methods(["GET", "POST"])
def bulk_grade(request):
    teacher = request.teacher

    # نجيب تسليمات مواد المدرّس غير المصحّحة (وأيضًا المـتأخرة لو تحب تعدّلها)
    base_qs = (
        HomeworkSubmission.objects.filter(
            assignment__group__teacher=teacher,
            status__in=[
                HomeworkSubmission.Status.SUBMITTED,
                HomeworkSubmission.Status.LATE,
            ],
        )
        .select_related("assignment", "student", "assignment__group")
        .order_by("-submitted_at")
    )
    status = request.GET.get("status")  # "SUBMITTED" | "LATE" | ""
    if status in [HomeworkSubmission.Status.SUBMITTED, HomeworkSubmission.Status.LATE]:
        base_qs = base_qs.filter(status=status)

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        d = parse_date(date_from)
        if d:
            base_qs = base_qs.filter(submitted_at__date__gte=d)
    if date_to:
        d = parse_date(date_to)
        if d:
            base_qs = base_qs.filter(submitted_at__date__lte=d)
    # فلتر اختياري بالمجموعة عبر ?group=<id>
    group_id = request.GET.get("group")
    if group_id:
        base_qs = base_qs.filter(assignment__group_id=group_id)

    # حجم الدفعة (لتقليل طول الصفحة)
    limit = int(request.GET.get("limit", "50"))
    qs = base_qs[: max(1, min(limit, 200))]

    FormSet = modelformset_factory(
        HomeworkSubmission, form=HomeworkBulkGradeForm, extra=0, can_delete=False
    )
    if request.method == "POST":
        formset = FormSet(request.POST, queryset=qs)
        if formset.is_valid():
            saved = 0
            for form in formset:
                if form.cleaned_data.get("select"):
                    form.save()
                    saved += 1
            if saved:
                messages.success(request, f"تم حفظ {saved} تسليم/تسليمات بنجاح ✅")
            else:
                messages.info(request, "لم يتم اختيار أي صف للحفظ.")
            # الرجوع للصفحة نفسها مع نفس الفلاتر
            return redirect(request.get_full_path())
        else:
            messages.error(request, "فضلاً صحّح الأخطاء في الحقول المظللة.")
    else:
        formset = FormSet(queryset=qs)

    # قائمة مجموعات المدرّس للفِلتر
    groups = Group.objects.filter(teacher=teacher).order_by("name")
    context = {
        "formset": formset,
        "groups": groups,
        "active_group": int(group_id) if group_id else None,
        "limit": limit,
        "total_pending": base_qs.count(),
        "status": status or "",
        "date_from": date_from or "",
        "date_to": date_to or "",
    }
    return render(request, "core/bulk_grade.html", context)


def _filtered_submissions_qs(request, teacher):
    # نفس منطق الفلاتر المستخدم في bulk_grade:
    base_qs = (
        HomeworkSubmission.objects.filter(
            assignment__group__teacher=teacher,
            status__in=[
                HomeworkSubmission.Status.SUBMITTED,
                HomeworkSubmission.Status.LATE,
            ],
        )
        .select_related("assignment", "student", "assignment__group")
        .order_by("-submitted_at")
    )

    status = request.GET.get("status")
    if status in [HomeworkSubmission.Status.SUBMITTED, HomeworkSubmission.Status.LATE]:
        base_qs = base_qs.filter(status=status)

    from django.utils.dateparse import parse_date

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        d = parse_date(date_from)
        if d:
            base_qs = base_qs.filter(submitted_at__date__gte=d)
    if date_to:
        d = parse_date(date_to)
        if d:
            base_qs = base_qs.filter(submitted_at__date__lte=d)

    group_id = request.GET.get("group")
    if group_id:
        base_qs = base_qs.filter(assignment__group_id=group_id)

    limit = int(request.GET.get("limit", "50"))
    return base_qs[: max(1, min(limit, 200))]


@teacher_required
def bulk_grade_export(request):
    teacher = request.teacher
    qs = _filtered_submissions_qs(request, teacher)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="submissions_export.csv"'
    w = csv.writer(resp)
    # أعمدة: id أساسي للتحديث
    w.writerow(
        [
            "id",
            "student",
            "assignment",
            "group",
            "current_status",
            "current_grade",
            "submitted_at",
            "link",
            "file_url",
            "current_feedback",
        ]
    )
    for r in qs:
        w.writerow(
            [
                r.id,
                f"{r.student.first_name} {r.student.last_name}",
                r.assignment.title,
                r.assignment.group.name,
                r.status,
                r.grade if r.grade is not None else "",
                r.submitted_at.strftime("%Y-%m-%d %H:%M"),
                r.link or "",
                (r.file.url if r.file else ""),
                (r.feedback or "").replace("\n", " ").strip()[:500],
            ]
        )
    return resp


@teacher_required
@require_POST
def bulk_grade_import(request):
    teacher = request.teacher
    file = request.FILES.get("file")
    if not file:
        messages.error(request, "أرفق ملف CSV أولًا.")
        return redirect(
            reverse("core:bulk_grade") + "?" + (request.META.get("QUERY_STRING") or "")
        )

    import io, csv

    try:
        text = io.TextIOWrapper(file.file, encoding="utf-8", errors="ignore")
    except Exception:
        messages.error(request, "تعذّر قراءة الملف. تأكّد أنه ترميز UTF-8.")
        return redirect(reverse("core:bulk_grade"))

    reader = csv.DictReader(text)
    required = {"id", "grade", "status", "feedback"}
    missing = required - set(
        h.lower() for h in [c.strip().lower() for c in reader.fieldnames or []]
    )
    if missing:
        messages.error(request, f"الأعمدة المطلوبة مفقودة: {', '.join(missing)}")
        return redirect(
            reverse("core:bulk_grade") + "?" + (request.META.get("QUERY_STRING") or "")
        )

    # سماح بالحالات
    allowed_status = {
        HomeworkSubmission.Status.SUBMITTED,
        HomeworkSubmission.Status.GRADED,
        HomeworkSubmission.Status.LATE,
    }
    updated = 0
    skipped = 0
    errors = 0

    with transaction.atomic():
        for row in reader:
            try:
                sid = int(row.get("id") or row.get("ID") or 0)
            except Exception:
                errors += 1
                continue
            try:
                sub = HomeworkSubmission.objects.select_related(
                    "assignment__group", "assignment"
                ).get(id=sid, assignment__group__teacher=teacher)
            except HomeworkSubmission.DoesNotExist:
                skipped += 1
                continue

            # قراءة القيم
            status = (row.get("status") or row.get("STATUS") or "").strip().upper()
            if status and status not in allowed_status:
                errors += 1
                continue

            grade_raw = (row.get("grade") or row.get("GRADE") or "").strip()
            feedback = (row.get("feedback") or row.get("FEEDBACK") or "").strip()

            # تحديث
            changed = False
            if grade_raw != "":
                try:
                    grade_val = float(grade_raw)
                    if sub.grade != grade_val:
                        sub.grade = grade_val
                        changed = True
                except ValueError:
                    errors += 1
                    continue
            if status:
                if sub.status != status:
                    sub.status = status
                    changed = True
            if feedback != "":
                if sub.feedback != feedback:
                    sub.feedback = feedback
                    changed = True

            if changed:
                sub.save()
                updated += 1

    messages.success(request, f"تم تحديث {updated} و تخطّي {skipped} و أخطاء {errors}.")
    return redirect(
        reverse("core:bulk_grade") + "?" + (request.META.get("QUERY_STRING") or "")
    )


@login_required
def post_login_redirect(request):
    # احترم ?next= لو جاي من صفحة محمية
    next_url = request.GET.get("next") or request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        return redirect(next_url)

    user = request.user
    # مدرّس؟
    if hasattr(user, "teacherprofile"):
        return redirect("core:dashboard")
    # وليّ أمر؟
    if hasattr(user, "parent_profile"):
        return redirect("core:parent_dashboard")
    # ستاف/أدمن؟
    if user.is_staff:
        return redirect("/admin/")
    if hasattr(user, "student_profile"):
        return redirect("core:student_dashboard")
    # افتراضي: ارجعه لصفحة الدخول
    return redirect(settings.LOGOUT_REDIRECT_URL)


@parent_required
def parent_report_pdf(request, student_id: int, year: int, month: int):
    student = get_object_or_404(Student, id=student_id, parent=request.parent)
    report = get_object_or_404(MonthlyReport, student=student, year=year, month=month)

    # 1) سجّل الخط مباشرة عند ReportLab (بدون @font-face)
    font_path = finders.find(
        "fonts/NotoNaskhArabic-Regular.ttf"
    )  # أو Amiri-Regular.ttf
    if not font_path:
        # fallback احتياطي: جرّب Amiri لو موجود
        font_path = finders.find("fonts/Amiri-Regular.ttf")

    if font_path:
        try:
            pdfmetrics.getFont("NotoNaskh")
        except KeyError:
            pdfmetrics.registerFont(TTFont("NotoNaskh", font_path))
            # مو لازم يكون عندك Bold/Italic؛ نربط العائلة لنفس الخط
            registerFontFamily(
                "NotoNaskh",
                normal="NotoNaskh",
                bold="NotoNaskh",
                italic="NotoNaskh",
                boldItalic="NotoNaskh",
            )

    html_str = render_to_string(
        "core/parent_report_pdf.html",
        {
            "student": student,
            "report": report,
            "STATIC_URL": settings.STATIC_URL,
        },
    )

    pdf_io = BytesIO()
    pisa_status = pisa.CreatePDF(
        src=html_str,
        dest=pdf_io,
        encoding="utf-8",
        # خليه موجود لو عندك صور/لوجو بستايتك؛ للخط ما عاد نحتاجه
        link_callback=lambda uri, rel: (
            (finders.find(uri.replace(settings.STATIC_URL, "", 1)) or uri)
            if uri.startswith(settings.STATIC_URL)
            else uri
        ),
    )

    if pisa_status.err:
        return HttpResponse("تعذّر توليد PDF بواسطة xhtml2pdf.", status=500)

    filename = f"report_{student.first_name}_{student.last_name}_{year}_{month}.pdf"
    resp = HttpResponse(pdf_io.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _link_callback(uri, rel):
    """
    xhtml2pdf يحتاج مسار ملف حقيقي للـ @font-face والصور.
    نحول STATIC_URL إلى مسار فعلي باستخدام staticfiles finders.
    """
    if uri.startswith(settings.STATIC_URL):
        relative_path = uri.replace(settings.STATIC_URL, "", 1)
        absolute_path = finders.find(relative_path)
        if absolute_path:
            # finders.find قد يرجّع list في بعض الحالات
            if isinstance(absolute_path, (list, tuple)):
                absolute_path = absolute_path[0]
            return absolute_path
        # لو عملت collectstatic
        if settings.STATIC_ROOT:
            import os

            return os.path.join(settings.STATIC_ROOT, relative_path)
    # اسمح بروابط http(s) كما هي
    return uri


@teacher_required
@require_POST
def send_session_reminder_now(request, session_id: int):
    session = get_object_or_404(
        ClassSession.objects.select_related("group__teacher"),
        id=session_id,
        group__teacher=request.teacher,
    )
    force = request.POST.get("force") == "1"

    # منع تكرار الإرسال لنفس المستلمين (إلا لو force)
    if not force:
        already = NotificationLog.objects.filter(
            event_type=NotificationLog.Event.SESSION_REMINDER, object_id=session.id
        ).exists()
        if already:
            messages.info(
                request,
                "سبق إرسال التذكير لهذه الحصة. فعّل (إجبار) لو تريد إعادة الإرسال.",
            )
            return redirect(reverse("core:dashboard"))

    sent = notify_session_reminder(session)
    if sent:
        messages.success(request, f"تم إرسال {sent} تذكير بنجاح ✅")
    else:
        messages.warning(
            request,
            "لم يتم إرسال أي تذكير (ربما لا يوجد أولياء أمور أو لا توجد إيميلات).",
        )
    return redirect(reverse("core:dashboard"))
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.conf import settings
from io import BytesIO

from django.contrib.auth.decorators import login_required

from .models import Invoice


@login_required
def parent_invoices(request):
    parent = getattr(request.user, "parent_profile", None)
    if not parent:
        return HttpResponseForbidden("هذا الحساب ليس له ملف وليّ أمر.")

    invoices = (
        Invoice.objects.filter(parent=parent)
        .select_related("student", "group")
        .prefetch_related("payments")
    )

    return render(request, "core/parent_invoices.html", {"invoices": invoices})


def _render_pdf(html_str):
    pdf_io = BytesIO()
    pisa.CreatePDF(html_str, dest=pdf_io, encoding="utf-8")
    return pdf_io.getvalue()


@parent_required
def invoice_pdf(request, invoice_id: int):
    inv = get_object_or_404(
        Invoice.objects.select_related("student", "group"),
        id=invoice_id,
        parent=request.parent,
    )
    html = render(
        request,
        "core/invoice_pdf.html",
        {
            "inv": inv,
            "SITE_NAME": getattr(settings, "SITE_NAME", ""),
            "SITE_URL": getattr(settings, "SITE_URL", ""),
        },
    ).content.decode("utf-8")
    pdf_bytes = _render_pdf(html)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    filename = f"invoice_{inv.student.id}_{inv.year}_{inv.month}.pdf"
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import redirect
from decimal import Decimal
from django.utils import timezone
from .models import Invoice, Student, Group


@teacher_required
@require_POST
def create_invoice_quick(request, student_id: int, group_id: int):
    student = get_object_or_404(Student, id=student_id)
    group = get_object_or_404(Group, id=group_id, teacher=request.teacher)
    amount = Decimal(request.POST.get("amount") or "350")
    today = timezone.localdate()
    inv, created = Invoice.objects.get_or_create(
        parent=student.parent,
        student=student,
        group=group,
        year=today.year,
        month=today.month,
        defaults={"amount_egp": amount, "due_date": today.replace(day=10)},
    )
    if not created:
        messages.info(request, "الفاتورة موجودة مسبقًا لهذا الشهر.")
    else:
        messages.success(request, "تم إنشاء الفاتورة.")
    return redirect("core:dashboard")


@teacher_required
def teacher_groups(request):
    today = timezone.localdate()

    groups = (
        Group.objects.filter(teacher=request.teacher)
        .select_related("academic_year", "subject")
        .order_by("-academic_year__is_active", "name")
    )

    # نحسب الأعداد بشكل فعّال
    group_ids = list(groups.values_list("id", flat=True))

    # عدد الطلاب النشطين
    counts_students = (
        Enrollment.objects.filter(group_id__in=group_ids, is_active=True)
        .values("group_id")
        .annotate(c=Count("id"))
    )
    students_map = {row["group_id"]: row["c"] for row in counts_students}

    # عدد الحصص القادمة (من اليوم فصاعدًا)
    counts_sessions = (
        ClassSession.objects.filter(group_id__in=group_ids, date__gte=today)
        .values("group_id")
        .annotate(c=Count("id"))
    )
    sessions_map = {row["group_id"]: row["c"] for row in counts_sessions}

    # فواتير هذا الشهر “غير مدفوعة/متأخرة” لهذي المجموعة (اختياري)
    counts_due = (
        Invoice.objects.filter(group_id__in=group_ids)
        .filter(year=today.year, month=today.month, status__in=["DUE", "OVERDUE"])
        .values("group_id")
        .annotate(c=Count("id"))
    )
    due_map = {row["group_id"]: row["c"] for row in counts_due}

    # جهّز صفوف العرض
    rows = []
    for g in groups:
        rows.append(
            {
                "obj": g,
                "students": students_map.get(g.id, 0),
                "upcoming": sessions_map.get(g.id, 0),
                "due_invoices": due_map.get(g.id, 0),
            }
        )

    return render(request, "core/teacher_groups.html", {"rows": rows})


@teacher_required
def group_students(request, group_id: int):
    g = get_object_or_404(
        Group.objects.select_related("teacher", "academic_year", "subject"),
        id=group_id,
        teacher=request.teacher,
    )
    enrolls = (
        Enrollment.objects.filter(group=g, is_active=True)
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    return render(request, "core/group_students.html", {"group": g, "enrolls": enrolls})


@teacher_required
def sessions_list(request, group_id: int):
    g = get_object_or_404(
        Group.objects.select_related("teacher", "subject"),
        id=group_id,
        teacher=request.teacher,
    )
    sessions = (
        ClassSession.objects.filter(group=g)
        .select_related("subject")
        .order_by("date", "start_time")
    )
    return render(
        request, "core/sessions_list.html", {"group": g, "sessions": sessions}
    )


@teacher_required
def assignments_list(request, group_id: int):
    g = get_object_or_404(
        Group.objects.select_related("teacher", "subject"),
        id=group_id,
        teacher=request.teacher,
    )
    assignments = (
        Assignment.objects.filter(group=g)
        .select_related("subject")
        .order_by("-assigned_at")
    )
    return render(
        request, "core/assignments_list.html", {"group": g, "assignments": assignments}
    )


class AssignmentQuickForm(forms.Form):
    group = forms.ModelChoiceField(
        label="المجموعة", queryset=Group.objects.none(), required=True
    )
    subject = forms.ModelChoiceField(
        label="المادة (اختياري)", queryset=Subject.objects.all(), required=False
    )
    title = forms.CharField(label="عنوان الواجب", max_length=200)
    description = forms.CharField(
        label="وصف مختصر", widget=forms.Textarea, required=False
    )
    due_at = forms.DateTimeField(
        label="الحدّ النهائي (تاريخ ووقت)",
        required=False,
        help_text="اختياري. مثال: 2025-09-25 18:00",
    )

    def clean_due_at(self):
        val = self.cleaned_data.get("due_at")
        if val and val < timezone.now():
            raise forms.ValidationError("الحدّ النهائي لا يصحّ يكون في الماضي.")
        return val


@teacher_required
def assignment_quick_create(request):
    # نقيّد المجموعات بمعلّم الجلسة
    teacher_groups = Group.objects.filter(teacher=request.teacher).order_by("name")

    if request.method == "POST":
        form = AssignmentQuickForm(request.POST)
        form.fields["group"].queryset = teacher_groups
        if form.is_valid():
            g = form.cleaned_data["group"]
            # أمان: تأكد إن المجموعة تابعة للمدرّس حتى لو عدّل الـ POST
            g = get_object_or_404(teacher_groups, id=g.id)

            a = Assignment.objects.create(
                group=g,
                subject=form.cleaned_data.get("subject") or None,
                title=form.cleaned_data["title"],
                description=form.cleaned_data.get("description", ""),
                due_at=form.cleaned_data.get("due_at"),
            )
            messages.success(request, f"تم إنشاء الواجب: {a.title} ✅")
            return redirect("core:dashboard")
    else:
        form = AssignmentQuickForm()
        form.fields["group"].queryset = teacher_groups

    return render(request, "core/assignment_quick_create.html", {"form": form})


def _collect_parent_emails(group):
    # يجيب إيميلات أولياء الأمور للطلاب المفعّلين بالمجموعة
    emails = []
    qs = Enrollment.objects.filter(group=group, is_active=True).select_related(
        "student__parent__user"
    )
    for e in qs:
        parent = getattr(e.student, "parent", None)
        user = getattr(parent, "user", None)
        email = getattr(user, "email", "") if user else ""
        if email:
            emails.append(email)
    # إزالة التكرارات والمحافظة على الترتيب
    return list(dict.fromkeys(emails))


@teacher_required
@require_POST
def notify_assignment_now(request, assignment_id: int):
    a = get_object_or_404(
        Assignment.objects.select_related("group", "subject", "group__teacher"),
        id=assignment_id,
        group__teacher=request.teacher,
    )
    recipients = _collect_parent_emails(a.group)
    if not recipients:
        messages.warning(request, "ماكو إيميلات لأولياء الأمور في هذي المجموعة.")
        return redirect("core:dashboard")

    subj_name = (
        a.subject.name
        if getattr(a, "subject", None)
        else (a.group.subject.name if getattr(a.group, "subject", None) else None)
    )
    subject_line = (
        f"واجب جديد{' — ' + subj_name if subj_name else ''}: {a.title} — {a.group.name}"
    )

    due_text = (
        timezone.localtime(a.due_at).strftime("%Y-%m-%d %H:%M") if a.due_at else "—"
    )
    body = (
        f"السلام عليكم\n\n"
        f"تم إضافة واجب جديد للطالب في مجموعة: {a.group.name}\n"
        f"العنوان: {a.title}\n"
        f"المادة: {subj_name or '—'}\n"
        f"الحدّ النهائي: {due_text}\n\n"
        f"الوصف:\n{(a.description or '').strip()}\n\n"
        f"مع التحية."
    )

    msg = EmailMessage(
        subject=subject_line,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        bcc=recipients,  # BCC حتى ما تظهر الإيميلات لبعض
    )
    sent = msg.send(fail_silently=True)
    messages.success(request, f"تم إرسال إشعار الواجب إلى {len(recipients)} وليّ أمر.")
    return redirect("core:dashboard")


@teacher_required
@require_POST
def send_session_reminder_now(request, session_id: int):
    s = get_object_or_404(
        ClassSession.objects.select_related("group", "subject", "group__teacher"),
        id=session_id,
        group__teacher=request.teacher,
    )
    recipients = _collect_parent_emails(s.group)
    if not recipients:
        messages.warning(request, "ماكو إيميلات لأولياء الأمور في هذي المجموعة.")
        return redirect("core:dashboard")

    subj_name = (
        s.subject.name
        if getattr(s, "subject", None)
        else (s.group.subject.name if getattr(s.group, "subject", None) else None)
    )
    subject_line = f"تذكير حصة{' — ' + subj_name if subj_name else ''}: {s.group.name} اليوم {s.date} الساعة {s.start_time}"

    online_note = ""
    # لو عندك حقل رابط أونلاين بالحصة سمّه حسب موديلك (مثلاً meeting_link)
    link = getattr(s, "meeting_link", "") or getattr(s, "online_link", "")
    if s.is_online and link:
        online_note = f"\nرابط الحضور: {link}"

    body = (
        f"السلام عليكم\n\n"
        f"تذكير بموعد الحصة:\n"
        f"المجموعة: {s.group.name}\n"
        f"المادة: {subj_name or '—'}\n"
        f"التاريخ: {s.date} — الوقت: {s.start_time} إلى {s.end_time}\n"
        f"النمط: {'أونلاين' if s.is_online else 'حضوري'}{online_note}\n\n"
        f"مع التحية."
    )

    msg = EmailMessage(
        subject=subject_line,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        bcc=recipients,
    )
    msg.send(fail_silently=True)
    messages.success(request, f"تم إرسال تذكير الحصة إلى {len(recipients)} وليّ أمر.")
    return redirect("core:dashboard")


class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ["kind", "title", "subject", "group", "session", "url", "file"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "url": forms.URLInput(
                attrs={"class": "form-control", "placeholder": "https://..."}
            ),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "kind": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.Select(attrs={"class": "form-select"}),
            "group": forms.Select(attrs={"class": "form-select"}),
            "session": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "kind": "نوع المورد",
            "title": "العنوان",
            "subject": "المادة (اختياري)",
            "group": "المجموعة",
            "session": "الحصة (اختياري)",
            "url": "الرابط",
            "file": "الملف",
        }

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        url = cleaned.get("url")
        file = cleaned.get("file")

        # لازم واحد من url/file
        if not url and not file:
            raise forms.ValidationError("يرجى تزويد رابط أو رفع ملف.")

        if kind in ["VIDEO", "LINK"] and not url:
            raise forms.ValidationError("لهذا النوع، (الرابط) مطلوب.")
        if kind == "FILE" and not file:
            raise forms.ValidationError("لنـوع (ملف)، لازم ترفع ملف.")
        # لازم يرتبط بمجموعة أو حصة
        if not cleaned.get("group") and not cleaned.get("session"):
            raise forms.ValidationError("أرفق المورد بحصة أو مجموعة.")
        return cleaned


@teacher_required
def resource_create(request):
    # نقيّد الاختيارات بمجموعات وحصص المدرّس
    teacher_groups = Group.objects.filter(teacher=request.teacher).order_by("name")
    teacher_sessions = ClassSession.objects.filter(
        group__teacher=request.teacher
    ).order_by("-date", "start_time")

    if request.method == "POST":
        form = ResourceForm(request.POST, request.FILES)
        form.fields["group"].queryset = teacher_groups
        form.fields["session"].queryset = teacher_sessions
        form.fields["subject"].queryset = Subject.objects.all().order_by("name")
        if form.is_valid():
            res: Resource = form.save(commit=False)
            # أمان: تأكد أن المجموعة/الحصة فعليًا للمدرّس
            if res.group and not teacher_groups.filter(id=res.group_id).exists():
                form.add_error("group", "مجموعة غير مسموح بها.")
            elif (
                res.session and not teacher_sessions.filter(id=res.session_id).exists()
            ):
                form.add_error("session", "حصة غير مسموح بها.")
            else:
                res.save()
                messages.success(request, "تم إضافة المورد بنجاح ✅")
                return redirect("core:dashboard")
    else:
        form = ResourceForm()
        form.fields["group"].queryset = teacher_groups
        form.fields["session"].queryset = teacher_sessions
        form.fields["subject"].queryset = Subject.objects.all().order_by("name")

    return render(request, "core/resource_create.html", {"form": form})


def _build_scan_url(request, session):
    # رابط صفحة المسح اللي راح ينقرأ من QR
    # مثال: http://127.0.0.1:8000/attendance/scan/12/?token=xxxxx
    return request.build_absolute_uri(
        f"/attendance/scan/{session.id}/?token={session.qr_token}"
    )


def _make_qr_data_url(text: str):
    """يحاول يولّد QR كصورة base64. إذا مكتبة qrcode غير منصّبة، يرجّع None."""
    try:
        import qrcode
        from PIL import Image  # qrcode يعتمد عليها
        import io

        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


@teacher_required
def session_qr_screen(request, session_id: int):
    """شاشة تعرض QR للحضور + زر تحديث التوكن."""
    s = get_object_or_404(
        ClassSession.objects.select_related("group", "group__teacher"),
        id=session_id,
        group__teacher=request.teacher,
    )
    # لو ماكو توكن أو منتهي، جدّد واحد لمدة 60 ثانية
    if (
        not s.qr_token
        or not s.qr_token_expires_at
        or timezone.now() >= s.qr_token_expires_at
    ):
        s.refresh_qr_token(ttl_seconds=60)

    scan_url = _build_scan_url(request, s)
    qr_data_url = _make_qr_data_url(scan_url)  # ممكن ترجع None

    ctx = {
        "session": s,
        "scan_url": scan_url,
        "qr_data_url": qr_data_url,
        "expires_at": s.qr_token_expires_at,
        "seconds_left": (
            max(0, int((s.qr_token_expires_at - timezone.now()).total_seconds()))
            if s.qr_token_expires_at
            else 0
        ),
    }
    return render(request, "core/session_qr_screen.html", ctx)


@login_required
@require_POST
def session_qr_refresh(request, session_id):
    session = get_object_or_404(ClassSession, pk=session_id)

    # (اختياري) لو عندك صلاحيات مدرس: تأكد إن المستخدم صاحب الحصة
    # if not TeacherProfile.objects.filter(user=request.user, groups=session.group).exists():
    #     return HttpResponseForbidden("غير مصرح")

    # جدّد التوكن لمدة 60 ثانية
    session.refresh_qr_token(ttl_seconds=600)

    # ابنِ رابط المسح مع التوكن
    # بدلاً من attendance_scan
    base_scan_url = reverse("core:student_self_checkin", args=[session.id])
    query = urlencode({"token": session.qr_token})
    full_url = request.build_absolute_uri(f"{base_scan_url}?{query}")
    # استخدم full_url في توليد الـ QR كما هو عندك


    # ولّد صورة QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(full_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # رجّعها Base64
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return JsonResponse(
        {
            "png_base64": png_b64,
            "expires_at": session.qr_token_expires_at.isoformat(),
            # "scan_url": full_url,  # لو حابب تستخدمه في القالب
        }
    )


def attendance_scan(request, session_id: int):
    """
    صفحة المسح (تُفتح من الموبايل):
    - تستلم token بالكويري سترنغ
    - POST: code (checkin_code) للطالب
    """
    s = get_object_or_404(ClassSession.objects.select_related("group"), id=session_id)
    token = request.GET.get("token") or request.POST.get("token") or ""

    # تحقّق صلاحية التوكن
    if not s.qr_token_valid(token):
        if request.method == "POST":
            return HttpResponseBadRequest(
                "رمز غير صالح أو منتهي. اطلب من المعلم تحديث QR."
            )
        # GET: بس اعرض رسالة وتخلي فورم يظهر لكن disabled
        expired = True
    else:
        expired = False

    if request.method == "POST" and not expired:
        code = (request.POST.get("code") or "").strip()
        if not code:
            messages.error(request, "رجاءً أدخل كود الطالب.")
            return redirect(request.path + f"?token={token}")

        # نجيب الطالب حسب كود الحضور ومتسجّل في هذي المجموعة
        student = Student.objects.filter(checkin_code=code).first()
        if not student:
            messages.error(request, "كود غير صحيح.")
            return redirect(request.path + f"?token={token}")

        active_in_group = Enrollment.objects.filter(
            student=student, group=s.group, is_active=True
        ).exists()
        if not active_in_group:
            messages.error(request, "الطالب مو مسجّل بهذي المجموعة.")
            return redirect(request.path + f"?token={token}")

        # سجّل حضور (أو حدّث)
        att, _ = Attendance.objects.update_or_create(
            session=s, student=student, defaults={"status": Attendance.Status.PRESENT}
        )
        messages.success(
            request, f"تم تسجيل حضور: {student.first_name} {student.last_name}"
        )
        return redirect(request.path + f"?token={token}")

    # GET: اعرض فورم إدخال الكود
    return render(
        request,
        "core/attendance_scan.html",
        {
            "session": s,
            "token": token,
            "expired": expired,
        },
    )


@require_http_methods(["GET", "POST"])
def logout_now(request):
    logout(request)
    return redirect("core:login")


@student_required
def student_dashboard(request):
    s = request.user.student_profile.student

    # مجموعات الطالب النشطة
    group_ids = list(
        Enrollment.objects.filter(student=s, is_active=True).values_list(
            "group_id", flat=True
        )
    )

    # واجبات مفتوحة (أحدث 50)
    open_assignments = (
        Assignment.objects.filter(group_id__in=group_ids)
        .select_related("group", "subject", "group__subject")
        .order_by("-assigned_at")[:50]
    )

    # آخر تسليم لكل واجب
    subs = {
        sub.assignment_id: sub
        for sub in HomeworkSubmission.objects.filter(
            student=s, assignment_id__in=[a.id for a in open_assignments]
        )
    }

    # حصص الأسبوع القادم
    today = timezone.localdate()
    next_week = today + timezone.timedelta(days=7)
    upcoming_sessions = (
        ClassSession.objects.filter(
            group_id__in=group_ids, date__range=(today, next_week)
        )
        .select_related("group", "subject", "group__subject")
        .order_by("date", "start_time")[:30]
    )

    # تسليمات أخيرة
    recent_submissions = (
        HomeworkSubmission.objects.filter(student=s)
        .select_related("assignment", "assignment__group")
        .order_by("-submitted_at")[:50]
    )

    # موارد حديثة + تفاصيل
    recent_resources = (
        Resource.objects.filter(
            Q(group_id__in=group_ids) | Q(session__group_id__in=group_ids)
        )
        .select_related("group", "session", "session__group", "subject")
        .order_by("-created_at")[:30]
    )

    ctx = {
        "student": s,
        "open_assignments": open_assignments,
        "subs_map": subs,
        "upcoming_sessions": upcoming_sessions,
        "recent_submissions": recent_submissions,
        "recent_resources": recent_resources,
        "today": today,
        "next_week": next_week,
        "now_ts": int(timezone.now().timestamp()),  # ← مهم للتمپليت
    }
    return render(request, "core/student_dashboard.html", ctx)


@student_required
def student_submit_homework(request, assignment_id: int):
    s = request.user.student_profile.student
    assignment = get_object_or_404(Assignment, id=assignment_id)

    # يتحقق أن الطالب ضمن مجموعة الواجب
    if not Enrollment.objects.filter(
        student=s, group=assignment.group, is_active=True
    ).exists():
        messages.error(request, "غير مسموح لك بتسليم هذا الواجب.")
        return redirect("core:student_dashboard")

    if request.method == "POST":
        answer_text = (request.POST.get("answer_text") or "").strip()
        link = (request.POST.get("link") or "").strip()
        file_obj = request.FILES.get("file")

        # لو فيه تسليم سابق، نحدّثه بدل ما نكسّر unique_together
        sub, _created = HomeworkSubmission.objects.get_or_create(
            assignment=assignment,
            student=s,
            defaults={"answer_text": answer_text, "link": link},
        )

        # حدّث الحقول اللي انبعتت
        updated = False
        if answer_text:
            sub.answer_text = answer_text
            updated = True
        if link:
            sub.link = link
            updated = True
        if file_obj:
            sub.file = file_obj
            updated = True

        if not (sub.file or sub.link or (sub.answer_text and sub.answer_text.strip())):
            messages.error(request, "يرجى رفع ملف أو إدخال رابط أو كتابة إجابة.")
            return redirect("core:student_dashboard")

        # إذا كان مصحّح وبدّل إجابة، رجّع الحالة SUBMITTED
        if sub.status == HomeworkSubmission.Status.GRADED and updated:
            sub.status = HomeworkSubmission.Status.SUBMITTED
            sub.grade = None
            sub.feedback = ""

        sub.save()
        messages.success(request, "تم تسليم واجبك بنجاح ✨")
        return redirect("core:student_submission_view", submission_id=sub.id)

    return redirect("core:student_dashboard")


@student_required
def student_submission_view(request, submission_id: int):
    s = request.user.student_profile.student
    sub = get_object_or_404(
        HomeworkSubmission.objects.select_related("assignment", "assignment__group"),
        id=submission_id,
        student=s,
    )
    return render(request, "core/student_submission.html", {"sub": sub})


def _get_student_from_user(user):
    # يجيب الطالب المرتبط بالمستخدم
    # يفضَّل تكون عامل StudentProfile؛ ده الأكثر وضوحًا
    try:
        return user.student_profile.student
    except Exception:
        # احتياط: لو مفيش Profile
        # جرّب تربط حسب الإيميل لو عندك ستودنت بنفس الإيميل
        return Student.objects.filter(email=user.email).first()


@login_required
def student_assignment_submit(request, assignment_id):
    student = _get_student_from_user(request.user)
    if not student:
        messages.error(request, "الحساب غير مرتبط بملف طالب.")
        return redirect("core:student_dashboard")

    assignment = get_object_or_404(Assignment, id=assignment_id)

    # تأكد إن الطالب مسجّل في مجموعة الواجب
    enrolled = Enrollment.objects.filter(
        student=student, group=assignment.group, is_active=True
    ).exists()
    if not enrolled:
        messages.error(request, "غير مسموح لك بتسليم هذا الواجب.")
        return redirect("core:student_dashboard")

    # موجود تسليم سابق؟ هنحدّثه بدل ما نكسر unique_together
    mysub = HomeworkSubmission.objects.filter(
        assignment=assignment, student=student
    ).first()

    if request.method == "POST":
        form = StudentSubmissionForm(request.POST, request.FILES, instance=mysub)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.assignment = assignment
            sub.student = student
            # حالة التأخير
            if assignment.due_at and timezone.now() > assignment.due_at:
                sub.status = HomeworkSubmission.Status.LATE
            else:
                sub.status = HomeworkSubmission.Status.SUBMITTED
            sub.submitted_at = timezone.now()
            sub.save()
            messages.success(request, "تم تسليم الواجب بنجاح.")
            return redirect("core:student_dashboard")
    else:
        form = StudentSubmissionForm(instance=mysub)

    ctx = {
        "student": student,
        "assignment": assignment,
        "form": form,
        "mysub": mysub,
    }
    return render(request, "core/student_submit.html", ctx)


@login_required
def student_submission_view(request, submission_id):
    student = _get_student_from_user(request.user)
    sub = get_object_or_404(HomeworkSubmission, id=submission_id, student=student)
    return render(
        request, "core/student_submission_view.html", {"student": student, "sub": sub}
    )


@login_required
def download_submission(request, submission_id: int):
    sub = get_object_or_404(HomeworkSubmission, id=submission_id)

    # تحقّق صلاحيات: معلّم المجموعة أو الطالب صاحب التسليم أو موظّف
    if not (
        _is_teacher_of_submission(request.user, sub)
        or _is_owner_student(request.user, sub)
    ):
        return HttpResponseForbidden("غير مصرّح لك بتنزيل هذا التسليم.")

    # 1) لو في ملف مرفوع → نزّله مباشرة
    if sub.file:
        filename = os.path.basename(sub.file.name)
        f = sub.file.open("rb")
        resp = FileResponse(f, as_attachment=True, filename=filename)
        return resp

    # 2) لو التسليم عبارة عن رابط → حوّل المستخدم للرابط
    if sub.link:
        return HttpResponseRedirect(sub.link)

    # 3) لو الإجابة نص فقط → أنشئ ملف نصّي للتنزيل
    if sub.answer_text and sub.answer_text.strip():
        content = sub.answer_text
        resp = HttpResponse(content, content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="submission_{sub.id}.txt"'
        return resp

    # لا يوجد أي محتوى صالح للتنزيل
    return HttpResponse("لا يوجد ملف/رابط/نص في هذا التسليم.", status=404)


@login_required
def group_create(request):
    # يختار المدرس فقط
    try:
        tp = request.user.teacherprofile
    except TeacherProfile.DoesNotExist:
        messages.error(request, "هذا الإجراء للمدرّسين فقط.")
        return redirect("core:dashboard")

    if request.method == "POST":
        form = GroupForm(request.POST)
        if form.is_valid():
            g = form.save(commit=False)
            g.teacher = tp
            g.save()
            messages.success(request, "تم إنشاء المجموعة.")
            return redirect("core:teacher_groups")
    else:
        form = GroupForm()
    return render(
        request, "core/group_form.html", {"form": form, "title": "إنشاء مجموعة"}
    )


@login_required
def group_edit(request, group_id):
    g = get_object_or_404(Group, id=group_id)
    if not _require_group_owner(request, g):
        return redirect("core:teacher_groups")

    if request.method == "POST":
        form = GroupForm(request.POST, instance=g)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث بيانات المجموعة.")
            return redirect("core:teacher_groups")
    else:
        form = GroupForm(instance=g)
    return render(
        request, "core/group_form.html", {"form": form, "title": f"تعديل: {g.name}"}
    )


@login_required
@transaction.atomic
def group_students_manage(request, group_id):
    g = get_object_or_404(Group, id=group_id)
    if not _require_group_owner(request, g):
        return redirect("core:teacher_groups")

    bulk_form = BulkStudentsForm(request.POST or None)
    add_form = AddExistingStudentsForm(request.POST or None)

    # إزالة طالب
    if (
        request.method == "POST"
        and request.POST.get("action") == "remove"
        and request.POST.get("enrollment_id")
    ):
        enr = get_object_or_404(Enrollment, id=request.POST["enrollment_id"], group=g)
        enr.delete()
        messages.success(request, "تم إزالة الطالب من المجموعة.")
        return redirect("core:group_students_manage", group_id=g.id)

    # إضافة IDs موجودة
    if request.method == "POST" and request.POST.get("action") == "add_existing":
        if add_form.is_valid():
            raw = add_form.cleaned_data.get("student_ids") or ""
            ids = [s.strip() for s in raw.split(",") if s.strip()]
            added = 0
            for sid in ids:
                try:
                    st = Student.objects.get(id=int(sid))
                except (Student.DoesNotExist, ValueError):
                    continue
                Enrollment.objects.get_or_create(
                    student=st, group=g, defaults={"is_active": True}
                )
                added += 1
            messages.success(request, f"تمت إضافة {added} طالب/طلاب موجودين.")
            return redirect("core:group_students_manage", group_id=g.id)

    # إضافة Bulk نصية
    if request.method == "POST" and request.POST.get("action") == "bulk_create":
        if bulk_form.is_valid():
            lines = bulk_form.cleaned_data.get("lines") or ""
            added = 0
            for line in lines.splitlines():
                line = line.strip()
                if not line:
                    continue
                # parse: name[, phone][, email]
                parts = [p.strip() for p in line.split(",")]
                name = parts[0]
                phone = parts[1] if len(parts) > 1 else ""
                email = parts[2] if len(parts) > 2 else ""

                # حاول نفصل الاسم لأول وآخر (ببساطة)
                name_parts = name.split()
                first = name_parts[0]
                last = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

                st = Student.objects.create(
                    first_name=first, last_name=last, phone=phone, email=email
                )
                Enrollment.objects.create(student=st, group=g, is_active=True)
                added += 1
            messages.success(request, f"تم إنشاء/إضافة {added} طالب/طلاب.")
            return redirect("core:group_students_manage", group_id=g.id)

    # قائمة الأعضاء الحاليين
    members = (
        Enrollment.objects.select_related("student")
        .filter(group=g)
        .order_by("student__first_name", "student__last_name")
    )

    return render(
        request,
        "core/group_students_manage.html",
        {
            "group": g,
            "members": members,
            "bulk_form": bulk_form,
            "add_form": add_form,
        },
    )


@login_required
@student_required
def student_self_checkin(request, session_id):
    token = request.GET.get("token", "")
    session = get_object_or_404(ClassSession, pk=session_id)

    # تحقّق صلاحية التوكن (غير منتهي ومطابق)
    if not session.qr_token_valid(token):
        messages.error(request, "رمز الحضور غير صالح أو منتهي.")
        return redirect("core:student_dashboard")

    # تحقّق أن الطالب ضمن المجموعة
    student = request.user.student_profile.student
    is_enrolled = Enrollment.objects.filter(
        student=student, group=session.group, is_active=True
    ).exists()
    if not is_enrolled:
        return HttpResponseForbidden("أنت غير مسجّل في هذه المجموعة.")

    # سجّل الحضور (أنشئ/حدّث)
    with transaction.atomic():
        att, _created = Attendance.objects.get_or_create(
            session=session,
            student=student,
            defaults={"status": Attendance.Status.PRESENT, "note": ""},
        )
        # لو كان غائب وعدّل نفسه إلى حاضر نسمح
        if att.status != Attendance.Status.PRESENT:
            att.status = Attendance.Status.PRESENT
            att.save(update_fields=["status"])

    messages.success(request, "تم تسجيل حضورك بنجاح ✅")
    return redirect("core:student_dashboard")
