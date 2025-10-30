from rest_framework.permissions import BasePermission


class IsTenantAdminOrSuperuser(BasePermission):
    """Allow access only to Django superusers or users marked as tenant admins."""

    message = 'You do not have permission to perform this action.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        # Allow tenant admins
        return getattr(user, 'is_tenant_admin', False)


class IsSuperuserOnly(BasePermission):
    """Allow access only to Django superusers."""

    message = 'Only superusers can perform this action.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return bool(user and user.is_authenticated and user.is_superuser)


