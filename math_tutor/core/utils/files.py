# core/utils/files.py
import magic


def detect_mime(django_file) -> str:
    head = django_file.read(4096)
    django_file.seek(0)
    try:
        return magic.from_buffer(head, mime=True) or ""
    except Exception:
        return ""


def is_image(django_file) -> bool:
    return detect_mime(django_file).startswith("image/")


def is_pdf(django_file) -> bool:
    mime = detect_mime(django_file)
    if mime == "application/pdf":
        return True
    # احتياط: توقيع PDF
    head = django_file.read(5)
    django_file.seek(0)
    return head == b"%PDF-"
