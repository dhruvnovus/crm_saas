from django.conf import settings
from django.db import connections
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
import json
import time
import logging
from user.models import Tenant, History

logger = logging.getLogger(__name__)


class TenantMiddleware:
    """Middleware to set the current tenant for database routing"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Extract tenant from request (could be from subdomain, header, etc.)
        tenant_name = self.get_tenant_from_request(request)
        try:
            if tenant_name:
                try:
                    tenant = Tenant.objects.get(name=tenant_name, is_active=True)
                    # Set tenant in connection for database routing
                    connections['default'].tenant = tenant
                    request.tenant = tenant
                except Tenant.DoesNotExist:
                    request.tenant = None
            else:
                request.tenant = None
            
            response = self.get_response(request)
            
            # After authentication, try to get tenant from user if not already set
            # BUT: Tenant admins live in main database and should not have tenant context set
            if hasattr(request, 'user') and request.user.is_authenticated and not request.tenant:
                if hasattr(request.user, 'tenant') and request.user.tenant:
                    # Only set tenant context if user is NOT a tenawt admin
                    # Tenant admins are stored in main database and queries should go there
                    if not getattr(request.user, 'is_tenant_admin', False):
                        request.tenant = request.user.tenant
                        connections['default'].tenant = request.user.tenant
            
            return response
        finally:
            # Always clear tenant context to prevent leakage between requests
            try:
                connections['default'].tenant = None
            except Exception:
                pass
    
    def get_tenant_from_request(self, request):
        """Extract tenant name from request"""
        # Method 1: From subdomain
        host = request.get_host().split(':')[0]
        if '.' in host:
            subdomain = host.split('.')[0]
            if subdomain != 'www':
                return subdomain
        
        # Method 2: From header
        return request.META.get('HTTP_X_TENANT')
        
        # Method 3: From URL parameter (for API testing)
        # return request.GET.get('tenant')


class HistoryMiddleware(MiddlewareMixin):
    """Middleware to log all API requests and responses"""
    
    def process_request(self, request):
        """Store request start time and prepare for logging"""
        request._history_start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Log the API request and response"""
        try:
            # Only log API requests (not static files, admin, etc.)
            if self._should_log_request(request):
                self._log_request(request, response)
        except Exception as e:
            logger.error(f"Error logging request: {str(e)}")
        
        return response
    
    def _should_log_request(self, request):
        """Determine if this request should be logged"""
        # Skip logging for certain paths
        skip_paths = [
            '/admin/',
            '/static/',
            '/media/',
            '/favicon.ico',
            '/swagger/',
            '/redoc/',
            '/api/schema/',
        ]
        
        path = request.path
        for skip_path in skip_paths:
            if path.startswith(skip_path):
                return False
        
        # Only log API requests (typically starting with /api/)
        return path.startswith('/api/')
    
    def _log_request(self, request, response):
        """Log the request details to History model"""
        try:
            # Get execution time
            execution_time = None
            if hasattr(request, '_history_start_time'):
                execution_time = time.time() - request._history_start_time
            
            # Get request data - handle the case where body might already be read
            request_data = None
            if request.method in ['POST', 'PUT', 'PATCH']:
                try:
                    # Try to get data from request.POST or request.data if available
                    if hasattr(request, 'data') and request.data:
                        request_data = dict(request.data)
                    elif hasattr(request, 'POST') and request.POST:
                        request_data = dict(request.POST)
                    elif hasattr(request, 'body') and request.body:
                        try:
                            request_data = json.loads(request.body.decode('utf-8'))
                        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                            # Body might have been read already, try to get from _body if available
                            if hasattr(request, '_body') and request._body:
                                try:
                                    request_data = json.loads(request._body.decode('utf-8'))
                                except (json.JSONDecodeError, UnicodeDecodeError):
                                    request_data = {'raw_body': str(request._body)[:1000]}
                            else:
                                request_data = {'note': 'Request body already consumed'}
                except Exception as e:
                    request_data = {'error': f'Could not parse request data: {str(e)}'}
            
            # Get response data
            response_data = None
            if hasattr(response, 'content') and response.content:
                try:
                    if isinstance(response, JsonResponse):
                        response_data = json.loads(response.content.decode('utf-8'))
                    elif response.get('Content-Type', '').startswith('application/json'):
                        response_data = json.loads(response.content.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    response_data = {'raw_content': str(response.content)[:1000]}  # Limit size
            
            # Get IP address
            ip_address = self._get_client_ip(request)
            
            # Get user and tenant
            user = getattr(request, 'user', None)
            tenant = getattr(request, 'tenant', None)
            
            # If tenant is not set but user has a tenant, use user's tenant
            if not tenant and user and hasattr(user, 'tenant') and user.tenant:
                tenant = user.tenant
            
            # Create history record
            History.objects.create(
                user=user if user and user.is_authenticated else None,
                tenant=tenant,
                method=request.method,
                endpoint=request.path,
                request_data=request_data,
                response_status=response.status_code,
                response_data=response_data,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                execution_time=execution_time,
                error_message=None if 200 <= response.status_code < 400 else f"HTTP {response.status_code}"
            )
            
        except Exception as e:
            logger.error(f"Failed to create history record: {str(e)}")
    
    def _get_client_ip(self, request):
        """Get the client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
