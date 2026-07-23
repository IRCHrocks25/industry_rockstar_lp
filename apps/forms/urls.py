"""Publishing-plane form routes. Mounted under the site host by urls_publishing."""

from django.urls import path

from . import views

urlpatterns = [
    path("_submit/<uuid:form_id>", views.submit, name="form_submit"),
]
