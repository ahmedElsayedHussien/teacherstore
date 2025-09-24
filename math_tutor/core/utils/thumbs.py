# core/utils/thumbs.py
from io import BytesIO
from PIL import Image
import fitz  # PyMuPDF


def make_image_thumb(django_file, max_size=400):
    im = Image.open(django_file)
    im.thumbnail((max_size, max_size))
    buf = BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=80, optimize=True)
    buf.seek(0)
    return buf  # ملف JPEG مصغّر


def make_pdf_thumb(django_file, max_size=400):
    data = django_file.read()
    django_file.seek(0)
    doc = fitz.open(stream=data, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap()
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img.thumbnail((max_size, max_size))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=80, optimize=True)
    buf.seek(0)
    return buf
