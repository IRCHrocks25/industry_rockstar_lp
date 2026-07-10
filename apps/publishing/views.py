from django.shortcuts import render


def home(request):
    """Placeholder for a resolved Site's root URL.

    Phase 1 replaces this with the published-page server (rendered blob from
    object storage, cache-first). request.site is guaranteed by
    HostRouterMiddleware.
    """
    return render(request, "publishing/placeholder.html", {"site": request.site})
