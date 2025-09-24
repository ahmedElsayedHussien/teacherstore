# core/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Assignment
from .services.notify import notify_assignment_created
from .utils.images import optimize_image


from django.db.models.signals import pre_save
from .models import HomeworkSubmission, Resource
from django.core.files.base import ContentFile
from .utils.thumbs import make_image_thumb, make_pdf_thumb
import magic
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.core.files.base import ContentFile

from .models import HomeworkSubmission, Resource
from .utils.images import optimize_image
from .utils.thumbs import make_image_thumb, make_pdf_thumb
from .utils.files import is_image, is_pdf
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Payment

@receiver(pre_save, sender=Resource)
def resource_opt(sender, instance, **kwargs):
    f = instance.file
    if f and not f._committed and is_image(f):
        optimize_image(f)


@receiver(post_save, sender=Assignment)
def assignment_created_notify(sender, instance: Assignment, created, **kwargs):
    if not created:
        return
    # نفّذ بعد الكومِت عشان الـ id ثابت وكل شيء محفوظ
    transaction.on_commit(lambda: notify_assignment_created(instance))


@receiver(pre_save, sender=HomeworkSubmission)
def submission_opt(sender, instance, **kwargs):
    f = instance.file
    if f and not f._committed and is_image(f):
        optimize_image(f)


@receiver(pre_save, sender=Resource)
def resource_opt(sender, instance, **kwargs):
    f = instance.file
    if f and not f._committed and is_image(f):
        optimize_image(f)


@receiver([post_save, post_delete], sender=Payment)
def _recalc_invoice_status(sender, instance: Payment, **kwargs):
    inv = instance.invoice
    inv.refresh_status(commit=True)
