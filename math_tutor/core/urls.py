from django.urls import path
from django.contrib.auth import views as auth_views
from . import views, export_views, account_views

app_name = "core"

urlpatterns = [
    # ----- الحساب / الدخول -----
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", views.logout_now, name="logout"),
    path("accounts/route/", views.post_login_redirect, name="post_login_redirect"),
    path("account/profile/", account_views.profile_view, name="account_profile"),
    path(
        "account/profile/save/", account_views.profile_save, name="account_profile_save"
    ),
    path(
        "account/password/change/",
        account_views.PasswordChangeViewCustom.as_view(),
        name="password_change",
    ),
    path(
        "account/password/change/done/",
        account_views.PasswordChangeDoneViewCustom.as_view(),
        name="password_change_done",
    ),
    path(
        "account/password/reset/",
        account_views.PasswordResetViewCustom.as_view(),
        name="password_reset",
    ),
    path(
        "account/password/reset/done/",
        account_views.PasswordResetDoneViewCustom.as_view(),
        name="password_reset_done",
    ),
    path(
        "account/password/reset/confirm/<uidb64>/<token>/",
        account_views.PasswordResetConfirmViewCustom.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "account/password/reset/complete/",
        account_views.PasswordResetCompleteViewCustom.as_view(),
        name="password_reset_complete",
    ),
    # ----- لوحة المدرّس -----
    path("dashboard/", views.teacher_dashboard, name="dashboard"),
    path(
        "dashboard/generate-next-week/",
        views.dashboard_generate_next_week,
        name="dashboard_generate_next_week",
    ),
    path(
        "dashboard/reminders-window/",
        views.dashboard_reminders_window,
        name="dashboard_reminders_window",
    ),
    path(
        "dashboard/assignments/create/",
        views.create_assignment,
        name="create_assignment",
    ),
    path(
        "dashboard/assignments/quick/",
        views.assignment_quick_create,
        name="assignment_quick_create",
    ),
    path(
        "dashboard/assignment/<int:assignment_id>/notify/",
        views.notify_assignment_now,
        name="notify_assignment_now",
    ),
    path("dashboard/bulk-grade/", views.bulk_grade, name="bulk_grade"),
    path(
        "dashboard/bulk-grade/export.csv",
        views.bulk_grade_export,
        name="bulk_grade_export",
    ),
    path(
        "dashboard/bulk-grade/import.csv",
        views.bulk_grade_import,
        name="bulk_grade_import",
    ),
    path(
        "dashboard/submission/<int:submission_id>/download/",
        views.download_submission,
        name="download_submission",
    ),
    path(
        "dashboard/submission/<int:sub_id>/grade/",
        views.grade_submission,
        name="grade_submission",
    ),
    # مجموعات المدرّس
    path("dashboard/groups/", views.teacher_groups, name="teacher_groups"),
    path("dashboard/groups/create/", views.group_create, name="group_create"),
    path("dashboard/group/<int:group_id>/edit/", views.group_edit, name="group_edit"),
    path(
        "dashboard/group/<int:group_id>/students/",
        views.group_students,
        name="group_students",
    ),
    path(
        "dashboard/group/<int:group_id>/students/manage/",
        views.group_students_manage,
        name="group_students_manage",
    ),
    path(
        "dashboard/group/<int:group_id>/sessions/",
        views.sessions_list,
        name="sessions_list",
    ),
    path(
        "dashboard/group/<int:group_id>/assignments/",
        views.assignments_list,
        name="assignments_list",
    ),
    path(
        "api/group/<int:group_id>/students/",
        views.api_group_students,
        name="api_group_students",
    ),
    # الحضور / QR
    path(
        "dashboard/session/<int:session_id>/send-reminder/",
        views.send_session_reminder_now,
        name="send_session_reminder_now",
    ),
    path(
        "dashboard/session/<int:session_id>/qr/",
        views.session_qr_screen,
        name="session_qr_screen",
    ),
    path(
        "dashboard/session/<int:session_id>/qr/refresh/",
        views.session_qr_refresh,
        name="session_qr_refresh",
    ),
    path(
        "attendance/scan/<int:session_id>/",
        views.attendance_scan,
        name="attendance_scan",
    ),
    path(
        "student/checkin/<int:session_id>/",
        views.student_self_checkin,
        name="student_self_checkin",
    ),
    # الموارد
    path("dashboard/resources/create/", views.resource_create, name="resource_create"),
    path("resources/<int:pk>/edit/", views.resource_update, name="resource_update"),
    path("resources/<int:pk>/delete/", views.resource_delete, name="resource_delete"),
    # الفوترة (مدرّس)
    path("billing/invoice/new/", views.invoice_create, name="invoice_create"),
    path(
        "billing/invoice/bulk/", views.invoice_bulk_create, name="invoice_bulk_create"
    ),
    path("billing/invoice/<int:pk>/edit/", views.invoice_update, name="invoice_update"),
    path(
        "billing/invoice/<int:pk>/delete/", views.invoice_delete, name="invoice_delete"
    ),
    path("billing/invoice/<int:pk>/pay/", views.payment_create, name="payment_create"),
    # Alias PDF للمدرّس (نفس الفيو بتاع parent)
    path(
        "billing/invoice/<int:invoice_id>/pdf/",
        views.invoice_pdf,
        name="invoice_pdf_teacher",
    ),
    # بوابة وليّ الأمر
    path("parent/", views.parent_dashboard, name="parent_dashboard"),
    path(
        "parent/report/<int:student_id>/<int:year>/<int:month>/",
        views.parent_report_view,
        name="parent_report_view",
    ),
    path(
        "parent/report/<int:student_id>/<int:year>/<int:month>/pdf/",
        views.parent_report_pdf,
        name="parent_report_pdf",
    ),
    path("parent/invoices/", views.parent_invoices, name="parent_invoices"),
    path("parent/invoice/<int:invoice_id>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    # بوابة الطالب
    path("student/", views.student_dashboard, name="student_dashboard"),
    path(
        "student/assignment/<int:assignment_id>/submit/",
        views.student_assignment_submit,
        name="student_assignment_submit",
    ),
    path(
        "student/submission/<int:submission_id>/",
        views.student_submission_view,
        name="student_submission_view",
    ),
    # تصدير CSV
    path(
        "export/today-attendance.csv",
        export_views.export_today_attendance,
        name="export_today_att",
    ),
    path(
        "export/ungraded-submissions.csv",
        export_views.export_ungraded_submissions,
        name="export_ungraded",
    ),
]
