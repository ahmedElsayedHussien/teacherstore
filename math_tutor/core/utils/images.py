# core/utils/images.py
from io import BytesIO
from PIL import Image


def optimize_image(django_file, max_w=1920, max_h=1920, quality=85):
    img = Image.open(django_file)
    img_format = "JPEG" if img.format in ["JPEG", "JPG"] else "PNG"
    # تصحيح الاتجاه من EXIF
    try:
        from PIL import ImageOps

        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    # تغيير مقاس لو أكبر
    img.thumbnail((max_w, max_h))
    # حفظ مؤقت
    buf = BytesIO()
    if img_format == "JPEG":
        img = img.convert("RGB")
        img.save(buf, format="JPEG", optimize=True, quality=quality)
    else:
        img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    django_file.file = buf  # استبدال المحتوى
    django_file.size = buf.getbuffer().nbytes
    return django_file
