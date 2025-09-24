# core/management/commands/assign_role.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group


class Command(BaseCommand):
    help = "Assign a role (group) to a username"

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("role")

    def handle(self, *args, **opts):
        u = User.objects.get(username=opts["username"])
        g = Group.objects.get(name=opts["role"])
        u.groups.add(g)
        self.stdout.write(
            self.style.SUCCESS(f"Assigned {opts['role']} to {u.username}")
        )
