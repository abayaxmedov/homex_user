from django.urls import path

from apps.wallet import views


urlpatterns = [
    path("", views.ExpenseListCreateView.as_view(), name="master-expenses"),
    path("<uuid:pk>/", views.ExpenseDetailView.as_view(), name="master-expense-detail"),
]
