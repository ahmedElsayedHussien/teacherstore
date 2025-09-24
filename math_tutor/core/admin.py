# core/admin.py
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
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

# ------------ Inlines ------------


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


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    verbose_name = _("سداد")
    verbose_name_plural = _("مدفوعات")


# ------------ User Admin مع بروفايل الطالب/المدرّس/ولي الأمر ------------


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


# إعادة تسجيل User بالـ Admin مع الإنلاينات
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# ------------ موديلات أساسية ------------


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "color")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "grade", "teacher", "subject", "capacity")
    list_filter = ("academic_year", "grade", "teacher", "subject")
    search_fields = ("name", "teacher__user__first_name", "teacher__user__last_name")
    autocomplete_fields = ("academic_year", "teacher", "subject")


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


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "group", "joined_on", "is_active")
    list_filter = ("is_active", "group__academic_year", "group")
    search_fields = ("student__first_name", "student__last_name", "group__name")
    autocomplete_fields = ("student", "group")


@admin.register(WeeklyScheduleBlock)
class WeeklyScheduleBlockAdmin(admin.ModelAdmin):
    list_display = ("group", "weekday", "start_time", "end_time", "is_online")
    list_filter = ("group", "weekday", "is_online")
    search_fields = ("group__name",)
    autocomplete_fields = ("group",)


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ("group", "date", "start_time", "end_time", "subject", "is_online")
    list_filter = ("group", "date", "is_online", "subject")
    search_fields = ("group__name", "topic")
    autocomplete_fields = ("group", "teacher", "subject")
    readonly_fields = ("qr_token", "qr_token_expires_at")


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "group", "session", "subject", "created_at")
    list_filter = ("kind", "subject", "group")
    search_fields = ("title",)
    autocomplete_fields = ("group", "session", "subject")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "group", "subject", "assigned_at", "due_at", "points")
    list_filter = ("group", "subject", "assigned_at", "due_at")
    search_fields = ("title", "group__name")
    autocomplete_fields = ("group", "subject")


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "assignment", "status", "grade", "submitted_at")
    list_filter = ("status", "assignment__group", "submitted_at")
    search_fields = ("student__first_name", "student__last_name", "assignment__title")
    autocomplete_fields = ("student", "assignment")
    date_hierarchy = "submitted_at"


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("session", "student", "status", "note")
    list_filter = (
        "status",
        "session__group",
    )
    search_fields = (
        "student__first_name",
        "student__last_name",
        "session__group__name",
    )
    autocomplete_fields = ("session", "student")


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


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "object_id", "recipient", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = (
        "recipient__username",
        "recipient__first_name",
        "recipient__last_name",
    )


# تسجيل نماذج منفصلة لو تحب تديرها مباشرة
@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = ("user__username", "user__first_name", "user__last_name")


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


# عناوين اللوحة بالعربي (اختياري)
admin.site.site_header = "لوحة إدارة المدرّس"
admin.site.site_title = "إدارة المنصّة"
admin.site.index_title = "مرحباً بك"
