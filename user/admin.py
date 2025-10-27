from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Tenant, CustomUser, TenantUser, History


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'database_name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'database_name']


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'tenant', 'is_tenant_admin', 'is_active']
    list_filter = ['tenant', 'is_tenant_admin', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Tenant Information', {'fields': ('tenant', 'is_tenant_admin')}),
    )


@admin.register(TenantUser)
class TenantUserAdmin(admin.ModelAdmin):
    list_display = ['user', 'tenant', 'created_at']
    list_filter = ['tenant', 'created_at']
    search_fields = ['user__username', 'tenant__name']


@admin.register(History)
class HistoryAdmin(admin.ModelAdmin):
    list_display = ['method', 'endpoint', 'user', 'tenant', 'response_status', 'execution_time', 'created_at']
    list_filter = ['method', 'response_status', 'tenant', 'created_at']
    search_fields = ['endpoint', 'user__username', 'tenant__name', 'ip_address']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Request Information', {
            'fields': ('method', 'endpoint', 'request_data')
        }),
        ('Response Information', {
            'fields': ('response_status', 'response_data', 'execution_time', 'error_message')
        }),
        ('User & Tenant', {
            'fields': ('user', 'tenant')
        }),
        ('Technical Details', {
            'fields': ('ip_address', 'user_agent')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Filter history based on user permissions"""
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            if request.user.tenant:
                qs = qs.filter(tenant=request.user.tenant)
            else:
                qs = qs.filter(user=request.user)
        return qs
