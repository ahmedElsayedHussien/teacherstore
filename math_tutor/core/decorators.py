# core/decorators.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from functools import wraps


def student_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not hasattr(request.user, "student_profile"):
            return redirect("core:post_login_redirect")  # أو للصفحة الرئيسية
        return view_func(request, *args, **kwargs)

    return _wrapped
