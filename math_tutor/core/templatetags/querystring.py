# core/templatetags/querystring.py
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """
    يدمج الباراميترات الحالية من request.GET مع أي تحديثات جديدة (مثل page)
    ويرجع querystring جاهز (بدون ?).
    الاستخدام: <a href="?{% url_replace page=2 %}">...</a>
    أو: <a href="?{% url_replace request=request page=2 %}">...</a>
    """
    request = context.get("request")
    if request is None:
        # لو مش متوفّر في الكونتكست، جرّب نلقطه من kwargs (Fallback)
        request = kwargs.pop("request", None)

    params = {}
    if request is not None:
        params.update(request.GET.dict())

    # احذف المفاتيح التي قيمتها None لتُزال من الكويري
    for k, v in kwargs.items():
        if v is None:
            params.pop(k, None)
        else:
            params[k] = v

    # ابنِ الـ querystring
    from urllib.parse import urlencode

    return urlencode(params, doseq=True)
