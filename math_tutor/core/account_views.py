from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.contrib.auth.views import (
    PasswordChangeView,
    PasswordChangeDoneView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings

from .forms_account import (
    UserBaseForm,
    TeacherProfileForm,
    ParentProfileForm,
    StudentProfileForm,
    StudentCoreForm,
)
from .models import TeacherProfile, ParentProfile, StudentProfile


@login_required
def profile_view(request):
    user = request.user
    user_form = UserBaseForm(instance=user)

    role = None
    t_form = p_form = s_form = s_core_form = None

    if hasattr(user, "teacherprofile"):
        role = "teacher"
        t_form = TeacherProfileForm(instance=user.teacherprofile)
    elif hasattr(user, "parent_profile"):
        role = "parent"
        p_form = ParentProfileForm(instance=user.parent_profile)
    elif hasattr(user, "student_profile"):
        role = "student"
        s_form = StudentProfileForm(instance=user.student_profile)
        s_core_form = StudentCoreForm(instance=user.student_profile.student)

    return render(
        request,
        "core/account_profile.html",
        {
            "user_form": user_form,
            "role": role,
            "t_form": t_form,
            "p_form": p_form,
            "s_form": s_form,
            "s_core_form": s_core_form,
        },
    )


@login_required
def profile_save(request):
    if request.method != "POST":
        return redirect("core:account_profile")

    user = request.user
    user_form = UserBaseForm(request.POST, instance=user)

    saved = False
    role = None

    if hasattr(user, "teacherprofile"):
        role = "teacher"
        t_form = TeacherProfileForm(request.POST, instance=user.teacherprofile)
        if user_form.is_valid() and t_form.is_valid():
            user_form.save()
            t_form.save()
            saved = True
    elif hasattr(user, "parent_profile"):
        role = "parent"
        p_form = ParentProfileForm(request.POST, instance=user.parent_profile)
        if user_form.is_valid() and p_form.is_valid():
            user_form.save()
            p_form.save()
            saved = True
    elif hasattr(user, "student_profile"):
        role = "student"
        s_form = StudentProfileForm(request.POST, instance=user.student_profile)
        s_core_form = StudentCoreForm(
            request.POST, instance=user.student_profile.student
        )
        if user_form.is_valid() and s_core_form.is_valid():
            user_form.save()
            s_core_form.save()
            saved = True
    else:
        # مستخدم عادي بدون بروفايلات
        if user_form.is_valid():
            user_form.save()
            saved = True

    if saved:
        messages.success(request, "تم حفظ الملف الشخصي بنجاح.")
    else:
        messages.error(request, "تعذّر الحفظ. تحقق من البيانات.")
    return redirect("core:account_profile")


# ====== Password Change (logged-in) ======
class PasswordChangeViewCustom(LoginRequiredMixin, PasswordChangeView):
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("core:password_change_done")


class PasswordChangeDoneViewCustom(LoginRequiredMixin, PasswordChangeDoneView):
    template_name = "registration/password_change_done.html"


# ====== Password Reset (via Email) ======
class PasswordResetViewCustom(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("core:password_reset_done")
    # لو عندك إعدادات EMAIL_BACKEND و DEFAULT_FROM_EMAIL مضبوطة—تمام


class PasswordResetDoneViewCustom(PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class PasswordResetConfirmViewCustom(PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("core:password_reset_complete")


class PasswordResetCompleteViewCustom(PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"
