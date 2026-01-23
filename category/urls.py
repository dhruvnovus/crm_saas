from django.urls import path
from .views import (
    CategoryListCreateView, 
    CategoryDetailView, 
    CategoryHistoryView,
)

urlpatterns = [
    path('', CategoryListCreateView.as_view(), name='category_list_create'),
    path('<uuid:pk>/', CategoryDetailView.as_view(), name='category_detail'),
    path('<uuid:pk>/history/', CategoryHistoryView.as_view(), name='category_history'),
]


