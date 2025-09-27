# core/admin.py
from decimal import Decimal
from django.db import models
from django.urls import path
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Sum, F, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from .models import (
    Subject,
    TeacherProfile,
    ParentProfile,
    AcademicYear,
    Group,
    Student,
    Enrollment,
    WeeklyScheduleBlock,
    ClassSession,
    Resource,
    Assignment,
    HomeworkSubmission,
    Attendance,
    MonthlyReport,
    NotificationLog,
    Invoice,
    Payment,
    StudentProfile,
)

# ----------------- Inlines -----------------


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    can_delete = True
    extra = 0
    verbose_name = _("ملف الطالب")
    verbose_name_plural = _("ملف الطالب")
    fk_name = "user"


class TeacherProfileInline(admin.StackedInline):
    model = TeacherProfile
    can_delete = True
    extra = 0
    verbose_name = _("ملف المدرّس")
    verbose_name_plural = _("ملف المدرّس")


class ParentProfileInline(admin.StackedInline):
    model = ParentProfile
    can_delete = True
    extra = 0
    verbose_name = _("وليّ الأمر")
    verbose_name_plural = _("أولياء الأمور")


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    verbose_name = _("تسجيل")
    verbose_name_plural = _("تسجيلات")
    autocomplete_fields = ("student", "group")
    show_change_link = True


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    verbose_name = _("سداد")
    verbose_name_plural = _("مدفوعات")


# ----------------- User Admin -----------------


class UserAdmin(BaseUserAdmin):
    inlines = [StudentProfileInline, TeacherProfileInline, ParentProfileInline]
    list_display = (
        "username",
        "first_name",
        "last_name",
        "email",
        "is_staff",
        "is_active",
    )
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")


admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# ----------------- Custom forms / validation -----------------


class EnrollmentAdminForm(admin.ModelAdmin):
    """
    نضيف تحقق يمنع قيد طالب بأكثر من مجموعة لنفس المادة وهو نشِط.
    """

    def save_model(self, request, obj, form, change):
        # تحقق الأعمال: ممنوع تكرار الطالب في مادة نفسها وهو نشط
        subject = obj.group.subject if obj.group_id else None
        if subject:
            conflict_qs = Enrollment.objects.filter(
                student=obj.student, is_active=True, group__subject=subject
            ).exclude(pk=obj.pk if obj.pk else None)
            if conflict_qs.exists():
                raise ValidationError(
                    _("هذا الطالب مسجّل بالفعل في مجموعة أخرى لنفس المادة.")
                )
        super().save_model(request, obj, form, change)


# ----------------- Subject -----------------


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "color")
    list_filter = ("is_active",)
    search_fields = ("name",)


# ----------------- AcademicYear -----------------


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


# ----------------- Group -----------------


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "grade", "teacher", "subject", "capacity")
    list_filter = ("academic_year", "grade", "teacher", "subject")
    search_fields = ("name", "teacher__user__first_name", "teacher__user__last_name")
    autocomplete_fields = ("academic_year", "teacher", "subject")

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "generate-next-week/",
                self.admin_site.admin_view(self.generate_next_week_view),
                name="core_group_generate_next_week",
            ),
            path(
                "generate-next-week/teacher/<int:teacher_id>/",
                self.admin_site.admin_view(self.generate_next_week_teacher_view),
                name="core_group_generate_next_week_teacher",
            ),
        ]
        return my_urls + urls

    def _generate_for_groups(self, groups):
        """منطق التوليد الفعلي؛ يُستخدم في المسارين."""
        created = 0
        today = timezone.localdate()
        next_week = today + timezone.timedelta(days=7)

        blocks_prefetch = WeeklyScheduleBlock.objects.select_related("group")
        groups = groups.select_related("teacher", "subject").prefetch_related(
            models.Prefetch("weekly_blocks", queryset=blocks_prefetch)
        )

        for g in groups:
            for b in g.weekly_blocks.all():
                day = today
                while day <= next_week:
                    if day.isoweekday() == b.weekday:
                        exists = ClassSession.objects.filter(
                            group=g, date=day, start_time=b.start_time
                        ).exists()
                        if not exists:
                            ClassSession.objects.create(
                                group=g,
                                teacher=g.teacher,
                                subject=g.subject,  # ياخذ مادة الجروب
                                date=day,
                                start_time=b.start_time,
                                end_time=b.end_time,
                                is_online=b.is_online,
                                meeting_link=b.meeting_link,
                            )
                            created += 1
                    day += timezone.timedelta(days=1)
        return created

    def generate_next_week_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        if request.method != "POST":
            messages.error(request, "العملية يجب أن تتم عبر POST.")
            return redirect("admin:core_group_changelist")

        groups = Group.objects.all()
        created = self._generate_for_groups(groups)
        messages.success(
            request, f"تم توليد {created} حصة للأسبوع القادم لجميع المجموعات."
        )
        return redirect("admin:core_group_changelist")

    def generate_next_week_teacher_view(self, request, teacher_id: int):
        if not self.has_change_permission(request):
            raise PermissionDenied
        if request.method != "POST":
            messages.error(request, "العملية يجب أن تتم عبر POST.")
            return redirect("admin:core_group_changelist")

        # تأكيد وجود المدرّس
        if not TeacherProfile.objects.filter(id=teacher_id).exists():
            messages.error(request, f"لم يتم العثور على مدرس بالرقم {teacher_id}.")
            return redirect("admin:core_group_changelist")

        groups = Group.objects.filter(teacher_id=teacher_id)
        created = self._generate_for_groups(groups)
        messages.success(
            request,
            f"تم توليد {created} حصة للأسبوع القادم لمجموعات المدرّس #{teacher_id}.",
        )
        return redirect("admin:core_group_changelist")


# ----------------- Student -----------------


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "parent",
        "phone",
        "email",
        "checkin_code",
    )
    list_filter = ("parent",)
    search_fields = ("first_name", "last_name", "phone", "email")
    inlines = [EnrollmentInline]
    readonly_fields = ("checkin_code",)
    autocomplete_fields = ("parent",)
    list_select_related = ("parent__user",)


# ----------------- Enrollment -----------------


@admin.register(Enrollment)
class EnrollmentAdmin(EnrollmentAdminForm):
    list_display = ("student", "group", "joined_on", "is_active", "subject_of_group")
    list_filter = ("is_active", "group__academic_year", "group__subject", "group")
    search_fields = ("student__first_name", "student__last_name", "group__name")
    autocomplete_fields = ("student", "group")
    list_select_related = ("student", "group", "group__subject")

    @admin.display(description=_("المادة"))
    def subject_of_group(self, obj):
        return obj.group.subject


# ----------------- WeeklyScheduleBlock -----------------


@admin.register(WeeklyScheduleBlock)
class WeeklyScheduleBlockAdmin(admin.ModelAdmin):
    list_display = ("group", "weekday", "start_time", "end_time", "is_online")
    list_filter = ("group", "weekday", "is_online")
    search_fields = ("group__name",)
    autocomplete_fields = ("group",)
    list_select_related = ("group",)


# ----------------- ClassSession -----------------


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = (
        "group",
        "date",
        "start_time",
        "end_time",
        "display_subject",
        "is_online",
    )
    list_filter = ("group", "date", "is_online", "subject")
    search_fields = ("group__name", "topic")
    autocomplete_fields = ("group", "teacher", "subject")
    readonly_fields = ("qr_token", "qr_token_expires_at")
    list_select_related = ("group", "teacher", "subject", "group__subject")

    @admin.display(description=_("المادة"))
    def display_subject(self, obj):
        return obj.subject or getattr(obj.group, "subject", None)

    def save_model(self, request, obj, form, change):
        # لو ما في مادة للحصة، خُد مادة المجموعة افتراضياً
        if not obj.subject_id and obj.group_id:
            obj.subject = obj.group.subject
        super().save_model(request, obj, form, change)


# ----------------- Resource -----------------


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "group", "session", "subject", "created_at")
    list_filter = ("kind", "subject", "group")
    search_fields = ("title",)
    autocomplete_fields = ("group", "session", "subject")
    list_select_related = ("group", "session", "subject", "session__group")


# ----------------- Assignment -----------------


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "group",
        "display_subject",
        "assigned_at",
        "due_at",
        "points",
    )
    list_filter = ("group", "subject", "assigned_at", "due_at")
    search_fields = ("title", "group__name")
    autocomplete_fields = ("group", "subject")
    list_select_related = ("group", "subject", "group__subject")

    @admin.display(description=_("المادة"))
    def display_subject(self, obj):
        return obj.subject or getattr(obj.group, "subject", None)


# ----------------- HomeworkSubmission -----------------


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "assignment", "status", "grade", "submitted_at")
    list_filter = ("status", "assignment__group", "submitted_at")
    search_fields = ("student__first_name", "student__last_name", "assignment__title")
    autocomplete_fields = ("student", "assignment")
    date_hierarchy = "submitted_at"
    list_select_related = ("student", "assignment", "assignment__group")


# ----------------- Attendance -----------------


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("session", "student", "status", "note")
    list_filter = ("status", "session__group")
    search_fields = (
        "student__first_name",
        "student__last_name",
        "session__group__name",
    )
    autocomplete_fields = ("session", "student")
    list_select_related = ("session", "session__group", "student")


# ----------------- MonthlyReport -----------------


@admin.register(MonthlyReport)
class MonthlyReportAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "month",
        "year",
        "attendance_pct",
        "avg_homework_score",
        "created_at",
    )
    list_filter = ("year", "month")
    search_fields = ("student__first_name", "student__last_name")
    autocomplete_fields = ("student",)
    date_hierarchy = "created_at"
    list_select_related = ("student",)


# ----------------- Invoice / Payment -----------------


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "parent",
        "group",
        "year",
        "month",
        "amount_egp",
        "status",
        "total_paid_annot",
        "remaining_annot",
        "due_date",
        "issued_at",
    )
    list_filter = ("status", "year", "month", "parent", "group")
    search_fields = (
        "student__first_name",
        "student__last_name",
        "parent__user__username",
    )
    autocomplete_fields = ("parent", "student", "group")
    inlines = [PaymentInline]
    date_hierarchy = "issued_at"
    list_select_related = ("student", "parent__user", "group")

    actions = ["action_refresh_status"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # نضيف paid_sum و remaining_annot لتُعرض بسرعة في الجدول
        qs = qs.annotate(
            paid_sum=Coalesce(Sum("payments__amount_egp"), Value(Decimal("0.00"))),
        ).annotate(remaining_annot=F("amount_egp") - F("paid_sum"))
        return qs.select_related("student", "parent__user", "group")

    @admin.display(description=_("مدفوع"))
    def total_paid_annot(self, obj):
        # يستخدم الـ annotate لتجنّب N+1
        paid = getattr(obj, "paid_sum", None)
        return paid if paid is not None else obj.total_paid

    @admin.display(description=_("المتبقي"))
    def remaining_annot(self, obj):
        rem = getattr(obj, "remaining_annot", None)
        if rem is None:
            rem = obj.amount_egp - obj.total_paid
        # لا نظهر قيم سالبة
        return rem if rem > 0 else Decimal("0.00")

    @admin.action(description=_("تحديث حالة الفواتير المختارة"))
    def action_refresh_status(self, request, queryset):
        updated = 0
        for inv in queryset:
            old = inv.status
            inv.refresh_status(commit=True)
            if inv.status != old:
                updated += 1
        self.message_user(
            request, _(f"تم تحديث حالة {updated} فاتورة."), level=messages.SUCCESS
        )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount_egp", "method", "reference", "received_at")
    list_filter = ("method", "received_at")
    search_fields = (
        "reference",
        "invoice__student__first_name",
        "invoice__student__last_name",
    )
    autocomplete_fields = ("invoice",)
    date_hierarchy = "received_at"
    list_select_related = ("invoice", "invoice__student")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # بعد الحفظ/التعديل نحدّث حالة الفاتورة
        obj.invoice.refresh_status(commit=True)


# ----------------- NotificationLog -----------------


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "object_id", "recipient", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = (
        "recipient__username",
        "recipient__first_name",
        "recipient__last_name",
    )
    date_hierarchy = "created_at"
    list_select_related = ("recipient",)


# ----------------- Profiles -----------------


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    list_select_related = ("user",)


@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    list_select_related = ("user",)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "student")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "student__first_name",
        "student__last_name",
    )
    autocomplete_fields = ("user", "student")
    list_select_related = ("user", "student")


# عناوين اللوحة
admin.site.site_header = "لوحة إدارة المدرّس"
admin.site.site_title = "إدارة المنصّة"
admin.site.index_title = "مرحباً بك"
