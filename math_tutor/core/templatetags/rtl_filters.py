from django import template
import arabic_reshaper
from bidi.algorithm import get_display

register = template.Library()


@register.filter
def rtl(value):
    """يشكّل النص العربي ويضبط اتجاهه للعرض مع xhtml2pdf."""
    if value is None:
        return ""
    try:
        text = str(value)
        # مهم: ما نلعب بالنص لو إنجليزي صِرف — بس عادةً مفيش ضرر
        reshaped = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped)
        return bidi_text
    except Exception:
        return value
