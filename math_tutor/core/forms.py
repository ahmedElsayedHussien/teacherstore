# core/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Assignment, Group, TeacherProfile

from .models import HomeworkSubmission

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
    select = forms.BooleanField(label=_("اختيار"), required=False)

    class Meta:
        model = HomeworkSubmission
        fields = ["select", "grade", "status", "feedback"]
        labels = {
            "grade": _("الدرجة"),
            "status": _("الحالة"),
            "feedback": _("تعليق المدرّس"),
        }
        widgets = {
            "grade": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
            "feedback": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "ملاحظة قصيرة للطالب",
                }
            ),
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
