def user_roles(request):
    u = getattr(request, "user", None)
    return {
        "is_auth": bool(u and u.is_authenticated),
        "is_teacher": bool(u and u.is_authenticated and hasattr(u, "teacherprofile")),
        "is_parent": bool(u and u.is_authenticated and hasattr(u, "parent_profile")),
        "is_student": bool(u and u.is_authenticated and hasattr(u, "student_profile")),
    }
