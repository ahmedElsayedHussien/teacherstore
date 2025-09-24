# core/validators.py
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.deconstruct import deconstructible

ALLOWED_EXTS = (".pdf", ".png", ".jpg", ".jpeg")


def validate_mime(file: UploadedFile):
    # فحص خفيف حسب الامتداد (بدون python-magic حتى ما نعلق بتبعيات)
    name = (file.name or "").lower()
    if not name.endswith(ALLOWED_EXTS):
        raise ValidationError("نوع الملف غير مسموح. المسموح: PDF, PNG, JPG, JPEG.")


@deconstructible
class MaxFileSizeValidator:
    """الحد بالـ MB، يدعم الهجرات."""

    def __init__(self, mb: int):
        self.mb = int(mb)

    def __call__(self, file: UploadedFile):
        limit = self.mb * 1024 * 1024
        if getattr(file, "size", 0) and file.size > limit:
            raise ValidationError(f"الحجم الأقصى {self.mb}MB.")

    def __eq__(self, other):
        return isinstance(other, MaxFileSizeValidator) and self.mb == other.mb
