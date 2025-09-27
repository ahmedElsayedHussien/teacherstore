from django.core.paginator import Paginator

def paginate(request, qs, per_page=25, page_param="page"):
    """يرجّع Page object جاهز للعرض."""
    page_num = request.GET.get(page_param) or 1
    return Paginator(qs, per_page).get_page(page_num)
