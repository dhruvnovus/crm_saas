from django.urls import path

from .views import BranchDetailView, BranchHistoryView, BranchListCreateView

urlpatterns = [
    path("", BranchListCreateView.as_view(), name="branch_list_create"),
    path("<uuid:pk>/", BranchDetailView.as_view(), name="branch_detail"),
    path("<uuid:pk>/history/", BranchHistoryView.as_view(), name="branch_history"),
]


