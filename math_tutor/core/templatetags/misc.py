# core/templatetags/misc.py
from django import template

register = template.Library()


@register.filter
def get_item(d, key):
    try:
        return d.get(key)
    except Exception:
        return None


@register.filter(name="add_class")
def add_class(field, css):
    """
    يضيف كلاس للـ widget بدون ما يلغي الموجود.
    الاستخدام: {{ form.field|add_class:"form-control" }}
    """
    attrs = field.field.widget.attrs.copy()
    old = attrs.get("class", "")
    attrs["class"] = (old + " " + css).strip()
    return field.as_widget(attrs=attrs)


@register.filter(name="attr")
def set_attr(field, arg):
    """
    يضبط أي أتربيوت (مثلاً placeholder)
    الاستخدام: {{ form.field|attr:"placeholder:اكتب العنوان" }}
    أو: {{ form.field|attr:"dir:ltr" }}
    """
    try:
        name, val = arg.split(":", 1)
    except ValueError:
        return field
    attrs = field.field.widget.attrs.copy()
    attrs[name] = val
    return field.as_widget(attrs=attrs)
