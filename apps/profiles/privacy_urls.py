from django.urls import path

from apps.profiles import views


urlpatterns = [
    path("", views.PrivacyPolicyView.as_view(), name="privacy-policy"),
]
