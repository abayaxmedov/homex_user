from django.urls import path

from apps.orders import views


urlpatterns = [
    path("", views.MasterReviewListView.as_view(), name="master-reviews"),
    path("summary/", views.MasterReviewSummaryView.as_view(), name="master-reviews-summary"),
]
