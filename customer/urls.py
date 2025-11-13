from django.urls import path
from .views import (
    CustomerListCreateView, 
    CustomerDetailView, 
    CustomerImportView, 
    CustomerHistoryView,
    CustomersByLeadStatusView,
    CustomerByIdByLeadStatusView
)

urlpatterns = [
    path('', CustomerListCreateView.as_view(), name='customer_list_create'),
    path('<uuid:pk>/', CustomerDetailView.as_view(), name='customer_detail'),
    path('<uuid:pk>/history/', CustomerHistoryView.as_view(), name='customer_history'),
    path('import/', CustomerImportView.as_view(), name='customer_import'),
    path('by-lead-status/', CustomersByLeadStatusView.as_view(), name='customers_by_lead_status'),
    path('<uuid:pk>/by-lead-status/', CustomerByIdByLeadStatusView.as_view(), name='customer_by_id_by_lead_status'),
]
