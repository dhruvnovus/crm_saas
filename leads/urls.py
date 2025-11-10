from django.urls import path

from . import views


urlpatterns = [
    path('', views.LeadListCreateView.as_view(), name='lead_list_create'),
    path('<uuid:pk>/', views.LeadDetailView.as_view(), name='lead_detail'),
    path('<uuid:pk>/status/', views.LeadStatusUpdateView.as_view(), name='lead_status_update'),
    path('<uuid:pk>/history/', views.LeadHistoryView.as_view(), name='lead_history'),
    path('<uuid:pk>/call-summaries/', views.LeadCallSummaryListCreateView.as_view(), name='lead_call_summary_list_create'),
    path('<uuid:pk>/call-summaries/<uuid:summary_id>/', views.LeadCallSummaryDetailView.as_view(), name='lead_call_summary_detail'),
    path('import/', views.LeadImportView.as_view(), name='lead_import'),
    # New endpoint for creating call summaries by customer ID
    path('call-summaries/by-customer/<uuid:customer_id>/', views.CustomerCallSummaryCreateView.as_view(), name='customer_call_summary_create'),
]


