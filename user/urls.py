from django.urls import path
from . import views

urlpatterns = [
    # Test endpoint
    path('test/', views.test_endpoint, name='test'),
    
    # Authentication endpoints
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    
    # User profile endpoints
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    
    # Tenant management
    path('tenants/', views.TenantListCreateView.as_view(), name='tenant_list'),
    path('tenant/users/', views.tenant_users, name='tenant_users'),
    path('tenant/users/create/', views.create_tenant_user, name='create_tenant_user'),
    
    # History endpoints
    path('history/', views.HistoryListView.as_view(), name='history_list'),
    path('history/<uuid:pk>/', views.history_detail, name='history_detail'),
    path('history/statistics/', views.history_statistics, name='history_statistics'),
]
