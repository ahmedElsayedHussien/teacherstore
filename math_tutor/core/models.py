from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords

from .validators import validate_mime, MaxFileSizeValidator
import secrets

class Subject(models.Model):
    name = models.CharField(_("اسم المادة"), max_length=100, unique=True)
    is_active = models.BooleanField(_("مفعّلة"), default=True)
    color = models.CharField(
        _("لون اختياري (hex)"), max_length=7, blank=True
    )  # مثل #0ea5e9

    class Meta:
        verbose_name = _("مادة")
        verbose_name_plural = _("مواد")
        ordering = ["name"]

    def __str__(self):
        return self.name


class TeacherProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, verbose_name=_("المستخدم")
    )
    phone = models.CharField(_("رقم الهاتف"), max_length=20, blank=True)
    class Meta:
        verbose_name = _("ملف المدرّس")
        verbose_name_plural = _("ملفات المدرّسين")

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class ParentProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="parent_profile",
        verbose_name=_("المستخدم"),
    )
    phone = models.CharField(_("رقم الهاتف"), max_length=20, blank=True)
    
    class Meta:
        verbose_name = _("وليّ الأمر")
        verbose_name_plural = _("أولياء الأمور")

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class AcademicYear(models.Model):
    name = models.CharField(_("اسم السنة"), max_length=50)  # مثال: 2025/2026
    start_date = models.DateField(_("تاريخ البداية"))
    end_date = models.DateField(_("تاريخ النهاية"))
    is_active = models.BooleanField(_("مفعّلة؟"), default=True)

    class Meta:
        verbose_name = _("سنة دراسية")
        verbose_name_plural = _("سنوات دراسية")
        unique_together = ("name", "start_date", "end_date")

    def __str__(self):
        return self.name


class Group(models.Model):
    class Grade(models.TextChoices):
        G1 = "G1", _("الصف الرابع")
        G2 = "G2", _("الصف الخامس")
        G3 = "G3", _("الصف 1 اعدادي")
        G4 = "G4", _("الصف 2 اعدادي")
        G5 = "G5", _("الصف 3 اعدادي")

        OTHER = "OTHER", _("أخرى")

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="groups",
        verbose_name=_("السنة الدراسية"),
    )
    name = models.CharField(_("اسم المجموعة"), max_length=100)
    grade = models.CharField(_("الصف الدراسي"), max_length=10, choices=Grade.choices)
    capacity = models.PositiveIntegerField(_("السعة"), default=30)
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.PROTECT,
        related_name="groups",
        verbose_name=_("المدرّس"),
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("المادة (افتراضي)"),
    )
    note = models.TextField(_("ملاحظات"), blank=True)
    class Meta:
        verbose_name = _("مجموعة")
        verbose_name_plural = _("مجموعات")
        unique_together = ("academic_year", "name")

    def __str__(self):
        return f"{self.name} - {self.academic_year.name}"


class Student(models.Model):
    first_name = models.CharField(_("الاسم الأول"), max_length=60)
    last_name = models.CharField(_("اسم العائلة"), max_length=60)
    dob = models.DateField(_("تاريخ الميلاد"), null=True, blank=True)
    school_name = models.CharField(_("اسم المدرسة"), max_length=120, blank=True)
    parent = models.ForeignKey(
        ParentProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("وليّ الأمر"),
    )
    checkin_code = models.CharField(
        _("كود الحضور"), max_length=12, blank=True, null=True
    )

    phone = models.CharField(_("رقم الهاتف"), max_length=20, blank=True)
    email = models.EmailField(_("البريد الإلكتروني"), blank=True)

    class Meta:
        verbose_name = _("طالب")
        verbose_name_plural = _("طلاب")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if not self.checkin_code:
            self.checkin_code = (
                secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
            )
        return super().save(*args, **kwargs)


class Enrollment(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name=_("الطالب"),
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name=_("المجموعة"),
    )
    joined_on = models.DateField(_("تاريخ الانضمام"), auto_now_add=True)
    is_active = models.BooleanField(_("نشِط؟"), default=True)

    class Meta:
        verbose_name = _("تسجيل")
        verbose_name_plural = _("تسجيلات")
        unique_together = ("student", "group")

    def __str__(self):
        return f"{self.student} ← {self.group}"


class WeeklyScheduleBlock(models.Model):
    class Weekday(models.IntegerChoices):
        MON = 1, _("الاثنين")
        TUE = 2, _("الثلاثاء")
        WED = 3, _("الأربعاء")
        THU = 4, _("الخميس")
        FRI = 5, _("الجمعة")
        SAT = 6, _("السبت")
        SUN = 7, _("الأحد")

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="weekly_blocks",
        verbose_name=_("المجموعة"),
    )
    weekday = models.IntegerField(_("اليوم"), choices=Weekday.choices)
    start_time = models.TimeField(_("وقت البداية"))
    end_time = models.TimeField(_("وقت النهاية"))
    is_online = models.BooleanField(_("أونلاين؟"), default=True)
    location = models.CharField(_("الموقع/العنوان"), max_length=120, blank=True)
    meeting_link = models.URLField(_("رابط الحصة"), blank=True)

    class Meta:
        verbose_name = _("بلوك جدول أسبوعي")
        verbose_name_plural = _("بلوكات الجدول الأسبوعي")
        unique_together = ("group", "weekday", "start_time")

    def __str__(self):
        return f"{self.group} - {self.get_weekday_display()} {self.start_time}"


class ClassSession(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name=_("المجموعة"),
    )
    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.PROTECT, verbose_name=_("المدرّس")
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("المادة"),
    )
    date = models.DateField(_("التاريخ"))
    start_time = models.TimeField(_("وقت البداية"))
    end_time = models.TimeField(_("وقت النهاية"))
    topic = models.CharField(_("الموضوع"), max_length=200, blank=True)
    is_online = models.BooleanField(_("أونلاين؟"), default=True)
    meeting_link = models.URLField(_("رابط الحصة"), blank=True)
    notes = models.TextField(_("ملاحظات"), blank=True)
    qr_token = models.CharField(_("توكن QR"), max_length=64, blank=True)
    qr_token_expires_at = models.DateTimeField(
        _("انتهاء التوكن"), null=True, blank=True
    )
    class Meta:
        verbose_name = _("حصة")
        verbose_name_plural = _("حصص")
        unique_together = ("group", "date", "start_time")

    def __str__(self):
        return f"{self.group} - {self.date} {self.start_time}"

    def get_subject(self):
        return self.subject or getattr(self.group, "subject", None)

    def refresh_qr_token(self, ttl_seconds=60):
        self.qr_token = secrets.token_urlsafe(24)
        self.qr_token_expires_at = timezone.now() + timezone.timedelta(
            seconds=ttl_seconds
        )
        self.save(update_fields=["qr_token", "qr_token_expires_at"])

    def qr_token_valid(self, token: str) -> bool:
        return (
            token
            and self.qr_token
            and token == self.qr_token
            and self.qr_token_expires_at
            and timezone.now() <= self.qr_token_expires_at
        )


class Resource(models.Model):
    class Kind(models.TextChoices):
        VIDEO = "VIDEO", _("رابط فيديو")
        FILE = "FILE", _("ملف مرفوع")
        LINK = "LINK", _("رابط خارجي")
        NOTE = "NOTE", _("ملاحظة")

    session = models.ForeignKey(
        "core.ClassSession",
        on_delete=models.CASCADE,
        related_name="resources",
        null=True,
        blank=True,
        verbose_name=_("حصة"),
    )
    group = models.ForeignKey(
        "core.Group",
        on_delete=models.CASCADE,
        related_name="resources",
        null=True,
        blank=True,
        verbose_name=_("مجموعة"),
    )
    kind = models.CharField(
        _("نوع المورد"), max_length=10, choices=Kind.choices, default=Kind.VIDEO
    )
    title = models.CharField(_("العنوان"), max_length=200)
    url = models.URLField(_("رابط"), blank=True)

    file = models.FileField(
        _("ملف"),
        upload_to="resources/%Y/%m/",
        # storage=PublicMediaStorage(),  # ← فعّلها لو تستخدم S3 public
        blank=True,
        validators=[
            FileExtensionValidator(["pdf", "png", "jpg", "jpeg"]),
            validate_mime,
            MaxFileSizeValidator(50),
        ],
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("المادة"),
    )
    created_at = models.DateTimeField(_("تاريخ الإضافة"), auto_now_add=True)

    class Meta:
        verbose_name = _("مورد")
        verbose_name_plural = _("موارد")

    def clean(self):
        # لازم ترتبط بحصة أو مجموعة على الأقل
        if not self.session and not self.group:
            raise ValidationError(_("أرفق المورد بحصة أو مجموعة."))

        # تحقق بحسب النوع
        if self.kind in [self.Kind.VIDEO, self.Kind.LINK]:
            if not self.url:
                raise ValidationError(_("بالنسبة للروابط، يجب إدخال (رابط)."))
            # ملف اختياري، بس غالبًا غير منطقي هنا
        elif self.kind == self.Kind.FILE:
            if not self.file:
                raise ValidationError(_("بالنسبة للملف، يجب رفع (ملف)."))
            # url اختياري
        elif self.kind == self.Kind.NOTE:
            if not self.url and not self.file:
                raise ValidationError(_("للملاحظة، زوّد رابطًا أو ملفًا على الأقل."))

    def __str__(self):
        return self.title


class Assignment(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("المجموعة"),
    )
    title = models.CharField(_("عنوان الواجب"), max_length=200)
    description = models.TextField(_("وصف الواجب"), blank=True)
    assigned_at = models.DateTimeField(_("تاريخ الإسناد"), auto_now_add=True)
    due_at = models.DateTimeField(_("تاريخ التسليم"), null=True, blank=True)
    attachment = models.FileField(_("مرفق"), upload_to="assignments/", blank=True)
    points = models.PositiveIntegerField(_("الدرجة الكاملة"), default=100)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("المادة"),
    )
    def get_subject(self):
        return self.subject or getattr(self.group, "subject", None)

    class Meta:
        verbose_name = _("واجب")
        verbose_name_plural = _("واجبات")

    def __str__(self):
        return self.title


class HomeworkSubmission(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", _("مُسلَّم")
        GRADED = "GRADED", _("مصحّح")
        LATE = "LATE", _("متأخّر")

    history = HistoricalRecords(verbose_name="سجل التغييرات")

    assignment = models.ForeignKey(
        "core.Assignment",
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name=_("الواجب"),
    )
    student = models.ForeignKey(
        "core.Student",
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name=_("الطالب"),
    )
    submitted_at = models.DateTimeField(_("وقت التسليم"), auto_now_add=True)
    answer_text = models.TextField(_("نص الإجابة"), blank=True)

    file = models.FileField(
        _("ملف مرفوع"),
        upload_to="submissions/%Y/%m/",
        # storage=PrivateMediaStorage(),  # ← فعّلها لو تستخدم S3 خاص
        blank=True,
        validators=[
            FileExtensionValidator(["pdf", "png", "jpg", "jpeg"]),
            validate_mime,
            MaxFileSizeValidator(50),
        ],
    )
    link = models.URLField(_("رابط الإجابة"), blank=True)

    grade = models.DecimalField(
        _("الدرجة"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    feedback = models.TextField(_("تعليق المدرّس"), blank=True)
    status = models.CharField(
        _("الحالة"), max_length=10, choices=Status.choices, default=Status.SUBMITTED
    )

    class Meta:
        verbose_name = _("تسليم واجب")
        verbose_name_plural = _("تسليمات الواجبات")
        unique_together = ("assignment", "student")

    def clean(self):
        # لازم واحدة من (file/link/answer_text) حتى يعتبر تسليم
        if (
            not self.file
            and not self.link
            and not (self.answer_text and self.answer_text.strip())
        ):
            raise ValidationError(_("يرجى رفع ملف أو إدخال رابط أو كتابة إجابة."))

    def __str__(self):
        return f"{self.student} - {self.assignment}"


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", _("حاضر")
        ABSENT = "ABSENT", _("غائب")
        LATE = "LATE", _("متأخّر")
        EXCUSED = "EXCUSED", _("معذور")

    session = models.ForeignKey(
        ClassSession,
        on_delete=models.CASCADE,
        related_name="attendance",
        verbose_name=_("الحصة"),
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="attendance",
        verbose_name=_("الطالب"),
    )
    status = models.CharField(
        _("الحالة"), max_length=10, choices=Status.choices, default=Status.PRESENT
    )
    note = models.CharField(_("ملاحظة"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("سجل حضور")
        verbose_name_plural = _("سجلات الحضور")
        unique_together = ("session", "student")

    def __str__(self):
        return f"{self.session} - {self.student} ({self.get_status_display()})"


class MonthlyReport(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="monthly_reports",
        verbose_name=_("الطالب"),
    )
    year = models.PositiveIntegerField(_("السنة"))
    month = models.PositiveIntegerField(_("الشهر"))  # 1..12
    attendance_pct = models.DecimalField(
        _("نسبة الحضور"), max_digits=5, decimal_places=2, default=0
    )  # مثال 92.50
    avg_homework_score = models.DecimalField(
        _("متوسط درجة الواجب"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    strengths = models.TextField(_("نِقَاط القوة"), blank=True)
    weaknesses = models.TextField(_("نِقَاط الضعف"), blank=True)
    recommendations = models.TextField(_("توصيات"), blank=True)
    teacher_comment = models.TextField(_("تعليق المدرّس العام"), blank=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("تقرير شهري")
        verbose_name_plural = _("تقارير شهرية")
        unique_together = ("student", "year", "month")

    def __str__(self):
        return f"تقرير {self.student} - {self.month}/{self.year}"


class NotificationLog(models.Model):
    class Event(models.TextChoices):
        ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED", "إنشاء واجب"
        SESSION_REMINDER = "SESSION_REMINDER", "تذكير حصة"

    event_type = models.CharField(max_length=40, choices=Event.choices)
    object_id = models.IntegerField()  # id للواجب أو الحصة
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_notifications"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["event_type", "object_id", "recipient"])]
        unique_together = (("event_type", "object_id", "recipient"),)

    def __str__(self):
        return f"{self.event_type} -> {self.recipient_id} #{self.object_id}"
# thumb = models.ImageField(
#     upload_to="thumbs/%Y/%m/", blank=True, null=True
# )

class Invoice(models.Model):
    class Status(models.TextChoices):
        DUE = "DUE", _("مستحق")
        PAID = "PAID", _("مدفوع")
        OVERDUE = "OVERDUE", _("متأخّر")
        CANCELED = "CANCELED", _("ملغاة")

    parent = models.ForeignKey(
        "core.ParentProfile",
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name=_("وليّ الأمر"),
    )
    student = models.ForeignKey(
        "core.Student",
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name=_("الطالب"),
    )
    group = models.ForeignKey(
        "core.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name=_("المجموعة"),
    )

    year = models.IntegerField(_("سنة الفاتورة"))
    month = models.IntegerField(_("شهر الفاتورة"))  # 1..12
    amount_egp = models.DecimalField(
        _("المبلغ بالجنيه"), max_digits=10, decimal_places=2
    )
    status = models.CharField(
        _("الحالة"), max_length=10, choices=Status.choices, default=Status.DUE
    )
    due_date = models.DateField(_("تاريخ الاستحقاق"), null=True, blank=True)
    issued_at = models.DateTimeField(_("تاريخ الإصدار"), auto_now_add=True)
    paid_at = models.DateTimeField(_("تاريخ السداد"), null=True, blank=True)
    notes = models.TextField(_("ملاحظات"), blank=True)

    class Meta:
        verbose_name = _("فاتورة")
        verbose_name_plural = _("فواتير")
        unique_together = ("parent", "student", "group", "year", "month")
        indexes = [
            models.Index(fields=["parent", "status"]),
            models.Index(fields=["year", "month"]),
        ]
        ordering = ["-year", "-month", "-issued_at"]

    def __str__(self):
        return (
            f"فاتورة {self.student} - {self.month}/{self.year} - {self.amount_egp} EGP"
        )

    @property
    def total_paid(self) -> Decimal:
        agg = self.payments.aggregate(s=models.Sum("amount_egp"))["s"]
        return agg or Decimal("0.00")

    @property
    def remaining(self) -> Decimal:
        return max(Decimal("0.00"), self.amount_egp - self.total_paid)

    def refresh_status(self, commit=True):
        old = self.status
        if self.remaining <= 0:
            self.status = self.Status.PAID
            if not self.paid_at:
                self.paid_at = timezone.now()
        else:
            # لو متأخرة عن due_date
            if self.due_date and timezone.localdate() > self.due_date:
                self.status = self.Status.OVERDUE
            else:
                self.status = self.Status.DUE
            self.paid_at = None
        if commit and self.status != old:
            self.save(update_fields=["status", "paid_at"])


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", _("نقدي")
        TRANSFER = "TRANSFER", _("تحويل بنكي")
        OTHER = "OTHER", _("أخرى")

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("الفاتورة"),
    )
    amount_egp = models.DecimalField(
        _("المبلغ بالجنيه"), max_digits=10, decimal_places=2
    )
    method = models.CharField(
        _("طريقة الدفع"), max_length=10, choices=Method.choices, default=Method.CASH
    )
    reference = models.CharField(_("رقم مرجع/إيصال"), max_length=100, blank=True)
    received_at = models.DateTimeField(_("تاريخ الاستلام"), default=timezone.now)
    note = models.CharField(_("ملاحظة"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("سداد")
        verbose_name_plural = _("مدفوعات")
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.amount_egp} EGP - {self.method} - {self.invoice_id}"


class StudentProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        verbose_name=_("المستخدم"),
    )
    student = models.OneToOneField(
        "core.Student",
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("الطالب"),
    )

    class Meta:
        verbose_name = _("ملف الطالب")
        verbose_name_plural = _("ملفات الطلاب")

    def __str__(self):
        return self.user.get_full_name() or self.user.username
