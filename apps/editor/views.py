from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.sites.models import Site

from .forms import SiteForm


@login_required
def sites_list(request):
    return render(
        request,
        "editor/sites_list.html",
        {"sites": Site.objects.all(), "base_domain": settings.BASE_DOMAIN},
    )


@login_required
def site_create(request):
    form = SiteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        site = form.save()
        messages.success(request, f"“{site.name}” is live at {site.subdomain}.{settings.BASE_DOMAIN}.")
        return redirect("sites_list")
    return render(
        request,
        "editor/site_form.html",
        {"form": form, "base_domain": settings.BASE_DOMAIN},
    )
