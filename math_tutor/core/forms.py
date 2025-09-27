# core/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Assignment, Group, TeacherProfile
from .models import Resource
from .models import HomeworkSubmission
from .models import Invoice, Payment, Group, Student, Enrollment

class AssignmentQuickForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["group", "title", "description", "points", "due_at", "attachment"]
        labels = {
            "group": _("المجموعة"),
            "title": _("عنوان الواجب"),
            "description": _("وصف الواجب"),
            "points": _("الدرجة الكاملة"),
            "due_at": _("تاريخ/وقت التسليم"),
            "attachment": _("مرفق (اختياري)"),
        }
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثال: واجب الكسور – ورقة رقم 3",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "تفاصيل مختصرة عن المطلوب",
                }
            ),
            "points": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "step": 1}
            ),
            # HTML5 datetime-local
            "due_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
        }

    def __init__(self, *args, **kwargs):
        teacher: TeacherProfile = kwargs.pop("teacher", None)
        super().__init__(*args, **kwargs)
        # فلترة المجموعات على مجموعات المدرّس فقط
        qs = Group.objects.none()
        if teacher:
            qs = Group.objects.filter(teacher=teacher).select_related("academic_year")
        self.fields["group"].queryset = qs
        self.fields["group"].widget.attrs.update({"class": "form-select"})
        self.fields["attachment"].widget.attrs.update({"class": "form-control"})

    def clean_due_at(self):
        due_at = self.cleaned_data.get("due_at")
        # تقدر تمنع الماضي لو تحب:
        # from django.utils import timezone
        # if due_at and due_at < timezone.now():
        #     raise forms.ValidationError(_("لا يمكن أن يكون موعد التسليم في الماضي."))
        return due_at


class HomeworkBulkGradeForm(forms.ModelForm):
    # حقل غير مرتبط بالموديل لتحديد الصفوف المطلوب حفظها
    select = forms.BooleanField(required=False, initial=False, label="")  # لتحديد الصف

    class Meta:
        model = HomeworkSubmission
        fields = ["id", "grade", "feedback", "status"]  # id حقل خفي

        widgets = {
            "grade": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "class": "form-control form-control-sm",
                    "placeholder": "درجة",
                }
            ),
            "feedback": forms.Textarea(
                attrs={
                    "rows": 1,
                    "class": "form-control form-control-sm",
                    "placeholder": "تعليق (اختياري)",
                }
            ),
            "status": forms.Select(attrs={"class": "form-select form-select-sm"}),
        }

    def clean(self):
        cleaned = super().clean()
        # مثال تحقق بسيط: لو الحالة مصحّح، يفضّل وجود درجة
        status = cleaned.get("status")
        grade = cleaned.get("grade")
        if self.cleaned_data.get("select"):
            if status == HomeworkSubmission.Status.GRADED and grade is None:
                raise forms.ValidationError(
                    _("عند تعيين الحالة (مصحّح) يُفضّل إدخال درجة.")
                )
        return cleaned


class StudentSubmissionForm(forms.ModelForm):
    class Meta:
        model = HomeworkSubmission
        fields = ["answer_text", "file", "link"]
        widgets = {
            "answer_text": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["academic_year", "name", "grade", "capacity", "subject", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].required = True


class BulkStudentsForm(forms.Form):
    """
    كل سطر: first_name last_name, phone?, email?
    مثال:
    Ali Ahmed, 01000000000, ali@example.com
    """

    lines = forms.CharField(
        label="أدخل الطلاب (سطر لكل طالب)",
        widget=forms.Textarea(attrs={"rows": 6}),
        required=False,
    )


class AddExistingStudentsForm(forms.Form):
    student_ids = forms.CharField(
        label="أرقام طلاب موجودين (IDs) مفصولة بفواصل",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "مثال: 12,15,27"}),
    )


class SubmissionGradeForm(forms.ModelForm):
    class Meta:
        model = HomeworkSubmission
        fields = ["grade", "feedback", "status"]
        widgets = {
            "grade": forms.NumberInput(attrs={"step": "0.01", "class": "form-control"}),
            "feedback": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }


class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ["title", "kind", "group", "session", "subject", "url", "file"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "kind": forms.Select(attrs={"class": "form-select"}),
            "group": forms.Select(attrs={"class": "form-select"}),
            "session": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.Select(attrs={"class": "form-select"}),
            "url": forms.URLInput(attrs={"class": "form-control"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }


class InvoiceForm(forms.ModelForm):
    class Meta:
        
        model = Invoice
        fields = ["group", "student", "year", "month", "amount_egp", "due_date", "notes"]
        widgets = {
            "group":     forms.Select(attrs={"class": "form-select", "id": "id_group"}),
            "student":   forms.Select(attrs={"class": "form-select", "id": "id_student", "disabled": "disabled"}),
            "year":      forms.NumberInput(attrs={"class":"form-control","min":2020}),
            "month":     forms.NumberInput(attrs={"class":"form-control","min":1,"max":12}),
            "amount_egp":forms.NumberInput(attrs={"class":"form-control","step":"0.01","min":"0"}),
            "due_date":  forms.DateInput(attrs={"type":"date","class":"form-control"}),
            "notes":     forms.Textarea(attrs={"class":"form-control","rows":2}),
        }
        widgets = {
            "parent": forms.Select(attrs={"class": "form-select"}),
            "student": forms.Select(attrs={"class": "form-select"}),
            "group": forms.Select(attrs={"class": "form-select"}),
            "year": forms.NumberInput(attrs={"class": "form-control", "min": 2020}),
            "month": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 12}
            ),
            "amount_egp": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "due_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get("student")
        group = cleaned.get("group")
        # لو فيه جروب، تأكد إنه الطالب مسجّل فيه
        if (
            student
            and group
            and not Enrollment.objects.filter(
                student=student, group=group, is_active=True
            ).exists()
        ):
            self.add_error("group", "الطالب غير مسجّل في هذه المجموعة.")
        # parent من بروفايل الطالب إن لم يُحدَّد
        if student and not cleaned.get("parent"):
            cleaned["parent"] = getattr(student, "parent", None)
        return cleaned


class InvoiceBulkForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=Group.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="المجموعة",
    )
    year = forms.IntegerField(
        min_value=2020,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="السنة",
    )
    month = forms.IntegerField(
        min_value=1,
        max_value=12,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        label="الشهر",
    )
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        label="المبلغ",
    )

    def __init__(self, *args, **kwargs):
        teacher = kwargs.pop("teacher", None)
        super().__init__(*args, **kwargs)
        if teacher:
            self.fields["group"].queryset = Group.objects.filter(
                teacher=teacher
            ).order_by("name")


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount_egp", "method", "reference", "received_at", "note"]
        widgets = {
            "amount_egp": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "method": forms.Select(attrs={"class": "form-select"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
            "received_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }
# core/forms.py
from django import forms
from .models import Invoice, Group, Student, Enrollment


class InvoiceSimpleForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "group",
            "student",
            "year",
            "month",
            "amount_egp",
            "due_date",
            "notes",
        ]
        widgets = {
            "group": forms.Select(attrs={"class": "form-select", "id": "id_group"}),
            "student": forms.Select(
                attrs={
                    "class": "form-select",
                    "id": "id_student",
                    "disabled": "disabled",
                }
            ),
            "year": forms.NumberInput(attrs={"class": "form-control", "min": 2020}),
            "month": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 12}
            ),
            "amount_egp": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "due_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        teacher = kwargs.pop("teacher", None)
        super().__init__(*args, **kwargs)
        # فلترة المجموعات بمجموعات المدرّس
        if teacher:
            self.fields["group"].queryset = (
                Group.objects.filter(teacher=teacher)
                .select_related("academic_year")
                .order_by("name")
            )
        else:
            self.fields["group"].queryset = Group.objects.none()

        # افتراضيًا لا طلاب حتى تُختار المجموعة
        self.fields["student"].queryset = Student.objects.none()

        # لو الفورم به قيمة group (POST أو instance) رشّح الطلاب
        group = self.data.get("group") or (
            self.instance.group_id if self.instance and self.instance.pk else None
        )
        if group:
            self.fields["student"].widget.attrs.pop("disabled", None)
            self.fields["student"].queryset = (
                Student.objects.filter(
                    enrollments__group_id=group, enrollments__is_active=True
                )
                .distinct()
                .order_by("last_name", "first_name")
            )

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get("student")
        group = cleaned.get("group")
        if not group:
            self.add_error("group", "اختر المجموعة أولًا.")
        if (
            student
            and group
            and not Enrollment.objects.filter(
                student=student, group=group, is_active=True
            ).exists()
        ):
            self.add_error("student", "الطالب غير مسجّل في هذه المجموعة.")
        return cleaned
