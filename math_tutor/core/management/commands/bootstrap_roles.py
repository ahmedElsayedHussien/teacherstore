from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from core import models as m

ROLE_DEFS = {
    "Teachers": [
        # حصص/واجبات/حضور/موارد
        (m.ClassSession, ["add", "change", "view"]),
        (m.Assignment, ["add", "change", "view"]),
        (m.HomeworkSubmission, ["view", "change"]),  # للتصحيح
        (m.Attendance, ["add", "change", "view"]),
        (m.Resource, ["add", "change", "view"]),
        # مجموعات وطلاب (قراءة فقط غالبًا)
        (m.Group, ["view"]),
        (m.Student, ["view"]),
        # فوترة (عرض)
        (m.Invoice, ["view"]),
        (m.Payment, ["view"]),
    ],
    "Students": [
        (m.Assignment, ["view"]),
        (m.HomeworkSubmission, ["add", "change", "view"]),  # تسليم وتعديل قبل الموعد
        (m.Resource, ["view"]),
        (m.ClassSession, ["view"]),
        (m.Group, ["view"]),
    ],
    "Parents": [
        (m.Student, ["view"]),
        (m.Assignment, ["view"]),
        (m.HomeworkSubmission, ["view"]),
        (m.ClassSession, ["view"]),
        (m.Invoice, ["view"]),
        (m.Payment, ["view"]),
        (m.MonthlyReport, ["view"]),
        (m.Resource, ["view"]),
    ],
    "BillingStaff": [
        (m.Invoice, ["add", "change", "view"]),
        (m.Payment, ["add", "change", "view"]),
    ],
}


def grant_perms(group, model, actions):
    ct = ContentType.objects.get_for_model(model)
    for act in actions:
        codename = f"{act}_{model._meta.model_name}"
        try:
            p = Permission.objects.get(content_type=ct, codename=codename)
            group.permissions.add(p)
        except Permission.DoesNotExist:
            pass


class Command(BaseCommand):
    help = "Bootstrap default roles & permissions"

    def handle(self, *args, **options):
        for role, rules in ROLE_DEFS.items():
            g, _ = Group.objects.get_or_create(name=role)
            for model, actions in rules:
                grant_perms(g, model, actions)
        self.stdout.write(self.style.SUCCESS("Roles & permissions bootstrapped."))
