from django.urls import path

from . import views


urlpatterns = [
    path('', views.LeadListCreateView.as_view(), name='lead_list_create'),
    path('<uuid:pk>/', views.LeadDetailView.as_view(), name='lead_detail'),
    path('<uuid:pk>/status/', views.LeadStatusUpdateView.as_view(), name='lead_status_update'),
]


