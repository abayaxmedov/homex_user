from django.urls import path

from apps.profiles import views


urlpatterns = [
    path("certificates/", views.MasterCertificateListCreateView.as_view(), name="master-certificates"),
    path("certificates/<uuid:pk>/", views.MasterCertificateDeleteView.as_view(), name="master-certificate-delete"),
    path("documents/", views.MasterDocumentListCreateView.as_view(), name="master-documents"),
]
