from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from django.db import connections
from user.models import Tenant


class TenantAwareTokenAuthentication(TokenAuthentication):
    """
    Custom token authentication that automatically detects tenant from token
    """
    
    def authenticate_credentials(self, key):
        """
        Override to handle tenant-aware token validation
        """
        # First try to find token in main database
        try:
            token = Token.objects.select_related('user').get(key=key)
            user = token.user
            # Only set tenant context if user is NOT a tenant admin
            # Tenant admins live in main database and should always be queried from there
            if hasattr(user, 'tenant') and user.tenant and not getattr(user, 'is_tenant_admin', False):
                connections['default'].tenant = user.tenant
            else:
                # Tenant admin or user without tenant: ensure we're in main database
                connections['default'].tenant = None
            return (user, token)
        except Token.DoesNotExist:
            pass
        
        # If not found in main database, try tenant databases
        try:
            tenants = Tenant.objects.filter(is_active=True)
            for tenant in tenants:
                try:
                    # Set tenant context
                    connections['default'].tenant = tenant
                    
                    # Try to find token in tenant database
                    token = Token.objects.select_related('user').get(key=key)
                    user = token.user
                    
                    # Clear tenant context to avoid side effects
                    connections['default'].tenant = None
                    
                    return (user, token)
                    
                except Token.DoesNotExist:
                    # Clear tenant context
                    connections['default'].tenant = None
                    continue
                except Exception as e:
                    # Clear tenant context in case of any error
                    connections['default'].tenant = None
                    # Log the error for debugging but don't expose it to the user
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error during tenant token authentication: {str(e)}")
                    continue
                    
        except Exception:
            # Clear tenant context in case of any error
            connections['default'].tenant = None
            pass
        
        # If token not found anywhere, raise authentication error
        from rest_framework.exceptions import AuthenticationFailed
        raise AuthenticationFailed('Invalid token.')
