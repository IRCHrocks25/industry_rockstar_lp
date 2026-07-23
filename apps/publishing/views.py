from django.http import Http404, HttpResponse
from django.shortcuts import render

from .service import read_published_html


def serve_page(request, path=""):
    """The published-page server (architecture.md §10). request.site is set by
    HostRouterMiddleware. Serves the stored publish blob; an unpublished
    homepage shows the friendly placeholder, any other unpublished path 404s."""
    page = request.site.pages.filter(path=path).first()
    if page is None or not page.is_published:
        if path == "":
            return render(request, "publishing/placeholder.html", {"site": request.site})
        raise Http404
    html = read_published_html(page)
    if html is None:
        raise Http404
    return HttpResponse(html)
