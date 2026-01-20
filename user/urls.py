from django.urls import path
from . import views

urlpatterns = [
    # Test endpoint
    path('test/', views.test_endpoint, name='test'),

    # Authentication endpoints
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('password/change/', views.change_password, name='change_password'),
    path('password/forgot/', views.forgot_password, name='forgot_password'),
    path('password/reset/', views.reset_password_confirm, name='reset_password'),

    # User profile endpoints
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/update/', views.update_profile, name='update_profile'),

    # Tenant management
    path('tenants/', views.TenantListCreateView.as_view(), name='tenant_list'),
    path('tenants/<uuid:pk>/', views.TenantDetailView.as_view(), name='tenant_detail'),

    # History endpoints
    path('history/', views.HistoryListView.as_view(), name='history_list'),
    path('history/<uuid:pk>/', views.history_detail, name='history_detail'),
    path('history/statistics/', views.history_statistics, name='history_statistics'),

    # Permissions & groups (tenant-scoped)
    path('permissions/', views.PermissionListView.as_view(), name='permission_list'),
    path('groups/', views.GroupListCreateView.as_view(), name='group_list_create'),
    path('groups/<int:pk>/', views.GroupDetailView.as_view(), name='group_detail'),
    path('users/<int:user_id>/permissions/', views.user_permissions_detail, name='user_permissions_detail'),
    path('users/<int:user_id>/set-groups-permissions/', views.set_user_groups_permissions, name='set_user_groups_permissions'),
]
