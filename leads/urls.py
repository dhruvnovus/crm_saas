from django.urls import path

from . import views


urlpatterns = [
    path('', views.LeadListCreateView.as_view(), name='lead_list_create'),
    path('<uuid:pk>/', views.LeadDetailView.as_view(), name='lead_detail'),
    path('<uuid:pk>/status/', views.LeadStatusUpdateView.as_view(), name='lead_status_update'),
    path('<uuid:pk>/history/', views.LeadHistoryView.as_view(), name='lead_history'),
    path('import/', views.LeadImportView.as_view(), name='lead_import'),
]


