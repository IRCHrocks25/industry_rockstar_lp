from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.sites.models import Site


@login_required
def sites_list(request):
    return render(
        request,
        "editor/sites_list.html",
        {"sites": Site.objects.all(), "base_domain": settings.BASE_DOMAIN},
    )
