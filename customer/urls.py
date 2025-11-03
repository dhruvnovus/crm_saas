from django.urls import path
from .views import CustomerListCreateView, CustomerDetailView, CustomerImportView

urlpatterns = [
    path('', CustomerListCreateView.as_view(), name='customer_list_create'),
    path('<uuid:pk>/', CustomerDetailView.as_view(), name='customer_detail'),
    path('import/', CustomerImportView.as_view(), name='customer_import'),
]
