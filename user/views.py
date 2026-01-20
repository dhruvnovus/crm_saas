from rest_framework import status, generics, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils.decorators import method_decorator
from .permissions import IsTenantAdminOrSuperuser, IsSuperuserOnly
from django.utils import timezone
from django.db import models
from datetime import datetime, timedelta
from .models import Tenant, TenantUser, CustomUser, History
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserSerializer,
    TenantSerializer,
    HistorySerializer,
    HistoryListSerializer,
    CreateTenantUserSerializer,
    ChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    PermissionSerializer,
    GroupSerializer,
    UserGroupPermissionSerializer,
)
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils import timezone
from django.contrib.auth.models import Group, Permission
import random


@swagger_auto_schema(method='get', tags=['Authentication'])
@api_view(['GET'])
@permission_classes([AllowAny])
def test_endpoint(request):
    """Simple test endpoint"""
    return Response({'message': 'API is working!'}, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method='post',
    operation_description="Register a new user and create a tenant with isolated database",
    request_body=UserRegistrationSerializer,
    responses={
        201: openapi.Response(
            description="User registered successfully",
            examples={
                "application/json": {
                    "user": {
                        "id": 1,
                        "username": "john_doe",
                        "email": "john@example.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "tenant": {
                            "id": "uuid-here",
                            "name": "Acme Corp",
                            "database_name": "crm_tenant_acme_corp",
                            "is_active": True
                        },
                        "is_tenant_admin": True
                    },
                    "token": "your-auth-token-here",
                    "message": "User registered successfully"
                }
            }
        ),
        400: openapi.Response(description="Bad request - validation errors")
    },
    tags=['Authentication']
)
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """Register a new user and create tenant"""
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'user': UserSerializer(user).data,
            'token': token.key,
            'message': 'User registered successfully'
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method='post',
    operation_description="Login user and get authentication token. Do NOT send tenant in the body. Tenant is inferred from subdomain or 'X-Tenant' header; if absent, authentication will try main DB, then all active tenants.",
    request_body=UserLoginSerializer,
    responses={
        200: openapi.Response(
            description="Login successful",
            examples={
                "application/json": {
                    "user": {
                        "id": 1,
                        "username": "john_doe",
                        "email": "john@example.com",
                        "tenant": {
                            "id": "uuid-here",
                            "name": "Acme Corp"
                        }
                    },
                    "token": "your-auth-token-here",
                    "message": "Login successful"
                }
            }
        ),
        400: openapi.Response(
            description="Invalid credentials or validation errors",
            examples={
                "application/json": {
                    "non_field_errors": [
                        "Invalid credentials for user \"username\" in tenant \"tenant_name\"",
                        "Invalid credentials for user \"username\". Please check your username and password.",
                        "Tenant \"tenant_name\" not found or not active"
                    ]
                }
            }
        ),
        500: openapi.Response(
            description="Authentication system error",
            examples={
                "application/json": {
                    "error": "Authentication system not properly configured for this tenant. Please contact support."
                }
            }
        )
    },
    tags=['Authentication']
)
@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """Login user and return token"""
    # Ignore any tenant in payload; rely on header/subdomain via serializer context
    login_data = request.data.copy()
    if 'tenant' in login_data:
        login_data.pop('tenant', None)
    
    serializer = UserLoginSerializer(data=login_data, context={'request': request})
    if serializer.is_valid():
        user = serializer.validated_data['user']

        # Ensure token is created in the same database where the user record lives
        try:
            from django.db import connections
            # Determine which DB the user instance originates from
            user_db_alias = getattr(getattr(user, '_state', None), 'db', 'default')

            if getattr(user, 'is_superuser', False) or user_db_alias == 'default':
                # Superusers and users stored in main DB: create token in main DB
                connections['default'].tenant = None
            elif hasattr(user, 'tenant') and user.tenant:
                # Users stored in tenant DB: route to tenant DB
                connections['default'].tenant = user.tenant
            else:
                connections['default'].tenant = None

            token, created = Token.objects.get_or_create(user=user)
        except Exception as e:
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Login token creation error: {str(e)}")
            
            # Check if it's a table doesn't exist error
            if "doesn't exist" in str(e) and "authtoken_token" in str(e):
                return Response({
                    'error': 'Authentication system not properly configured. Please contact support.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response({
                    'error': 'Authentication failed. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            # Always clear tenant context after token creation to avoid leaking it to other requests
            try:
                connections['default'].tenant = None
            except Exception:
                pass
        
        return Response({
            'user': UserSerializer(user).data,
            'token': token.key,
            'message': 'Login successful'
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method='post',
    operation_description="Logout user by deleting authentication token",
    responses={
        200: openapi.Response(
            description="Logout successful",
            examples={
                "application/json": {
                    "message": "Logout successful"
                }
            }
        )
    },
    tags=['Authentication']
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """Logout user by deleting token"""
    try:
        request.user.auth_token.delete()
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
    except:
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method='get',
    operation_description="Get current user profile information",
    responses={
        200: openapi.Response(
            description="User profile retrieved successfully",
            examples={
                "application/json": {
                    "id": 1,
                    "username": "john_doe",
                    "email": "john@example.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "tenant": {
                        "id": "uuid-here",
                        "name": "Acme Corp",
                        "database_name": "crm_tenant_acme_corp",
                        "is_active": True
                    },
                    "is_tenant_admin": True,
                    "date_joined": "2024-01-01T00:00:00Z"
                }
            }
        ),
        401: openapi.Response(description="Authentication required")
    },
    tags=['Tenant Management']
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    """Get current user profile"""
    from django.db import connections
    
    user = request.user
    
    # Tenant admins are stored in the main database and should always be queried from there
    # Regular tenant users are stored in their tenant database
    if getattr(user, 'is_tenant_admin', False):
        # Tenant admin: ensure we query from main database
        connections['default'].tenant = None
        try:
            # Refresh user from main database to ensure we have latest data
            user = CustomUser.objects.get(pk=user.pk)
        except CustomUser.DoesNotExist:
            # If user not found in main DB, use the authenticated user instance
            pass
    elif hasattr(user, 'tenant') and user.tenant:
        # Regular tenant user: query from tenant database
        connections['default'].tenant = user.tenant
        try:
            # Refresh user from tenant database to ensure we have latest data
            user = CustomUser.objects.get(pk=user.pk)
        except CustomUser.DoesNotExist:
            # If user not found in tenant DB, try main database as fallback
            connections['default'].tenant = None
            try:
                user = CustomUser.objects.get(pk=user.pk)
            except CustomUser.DoesNotExist:
                # Use authenticated user instance if not found anywhere
                pass
    else:
        # User without tenant: query from main database
        connections['default'].tenant = None
        try:
            user = CustomUser.objects.get(pk=user.pk)
        except CustomUser.DoesNotExist:
            pass
    
    serializer = UserSerializer(user)
    return Response(serializer.data)


@swagger_auto_schema(
    method='patch',
    operation_description="Update user profile (partial update). All fields are optional.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'username': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Username (must be unique)',
                example='john_doe'
            ),
            'email': openapi.Schema(
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_EMAIL,
                description='Email address',
                example='john@example.com'
            ),
            'first_name': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='First name',
                example='John'
            ),
            'last_name': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Last name',
                example='Doe'
            ),
        },
        required=[]
    ),
    responses={
        200: openapi.Response(
            description="Profile updated successfully",
            examples={
                "application/json": {
                    "id": 1,
                    "username": "john_doe",
                    "email": "john@example.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "tenant": {
                        "id": "uuid-here",
                        "name": "Acme Corp"
                    },
                    "is_tenant_admin": True,
                    "date_joined": "2024-01-01T00:00:00Z"
                }
            }
        ),
        400: openapi.Response(
            description="Validation errors",
            examples={
                "application/json": {
                    "username": ["A user with that username already exists."],
                    "email": ["Enter a valid email address."]
                }
            }
        ),
        401: openapi.Response(description="Authentication required")
    },
    tags=['Tenant Management']
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """Update user profile (partial update)"""
    from django.db import connections
    
    user = request.user
    
    # Handle tenant context for user updates - this will be used by the serializer
    if getattr(user, 'is_tenant_admin', False):
        connections['default'].tenant = None
    elif hasattr(user, 'tenant') and user.tenant:
        connections['default'].tenant = user.tenant
    else:
        connections['default'].tenant = None
    
    # Refresh user from correct database to ensure we have the latest instance
    try:
        user = CustomUser.objects.get(pk=user.pk)
    except CustomUser.DoesNotExist:
        pass
    
    serializer = UserSerializer(user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(name='get', decorator=swagger_auto_schema(tags=['Tenant Management']))
@method_decorator(name='post', decorator=swagger_auto_schema(tags=['Tenant Management']))
class TenantListCreateView(generics.ListCreateAPIView):
    """List and create tenants (admin only)"""
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated, IsSuperuserOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'database_name']
    
    def get_queryset(self):
        # Only show tenants for the current user
        if self.request.user.is_superuser:
            return Tenant.objects.all().order_by('-created_at')
        return Tenant.objects.filter(tenantuser__user=self.request.user).order_by('-created_at')


@method_decorator(name='get', decorator=swagger_auto_schema(tags=['Tenant Management']))
@method_decorator(name='delete', decorator=swagger_auto_schema(tags=['Tenant Management']))
class TenantDetailView(generics.RetrieveDestroyAPIView):
    """Retrieve or soft-delete a tenant"""
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated, IsSuperuserOnly]
    lookup_field = 'pk'

    def delete(self, request, *args, **kwargs):
        tenant = self.get_object()
        # Only superuser or tenant admin associated with this tenant can delete
        if not (request.user.is_superuser or (request.user.tenant == tenant and request.user.is_tenant_admin)):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        tenant.is_active = False
        tenant.save(update_fields=['is_active', 'updated_at'])
        return Response({'message': 'Tenant soft-deleted'}, status=status.HTTP_200_OK)


@swagger_auto_schema(method='get', exclude=True)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOnly])
def tenant_users(request):
    """Get users for current tenant"""
    from django.db import connections
    try:
        # Determine tenant: prefer explicit header/query for superuser, fallback to user's tenant
        tenant_obj = None
        if request.user.tenant:
            tenant_obj = request.user.tenant
        else:
            # Allow superusers to specify tenant via header or query
            tenant_name = request.META.get('HTTP_X_TENANT') or request.GET.get('tenant')
            if tenant_name:
                try:
                    tenant_obj = Tenant.objects.get(name=tenant_name, is_active=True)
                except Tenant.DoesNotExist:
                    return Response({'error': 'Tenant not found or inactive'}, status=status.HTTP_400_BAD_REQUEST)
        if not tenant_obj:
            return Response({'error': 'No tenant associated or provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Set tenant context for database routing
        connections['default'].tenant = tenant_obj

        # Query users from tenant database
        tenant_users_qs = CustomUser.objects.all()
        serializer = UserSerializer(tenant_users_qs, many=True)
        return Response(serializer.data)
    finally:
        # Clear tenant context
        try:
            connections['default'].tenant = None
        except Exception:
            pass


@swagger_auto_schema(method='post', exclude=True)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSuperuserOnly])
def create_tenant_user(request):
    """Create a new user within the current tenant"""
    if not request.user.tenant or not request.user.is_tenant_admin:
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    # Ensure all subsequent ORM operations target the logged-in tenant database
    from django.db import connections
    try:
        connections['default'].tenant = request.user.tenant

        serializer = CreateTenantUserSerializer(
            data=request.data, 
            context={'tenant': request.user.tenant}
        )
        
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    finally:
        # Clear tenant context
        try:
            connections['default'].tenant = None
        except Exception:
            pass


@method_decorator(name='get', decorator=swagger_auto_schema(tags=['History']))
class HistoryListView(generics.ListAPIView):
    """List all API history records with filtering and pagination"""
    serializer_class = HistoryListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['method', 'response_status', 'user', 'tenant']
    search_fields = ['endpoint', 'user__username', 'tenant__name']
    ordering_fields = ['created_at', 'execution_time', 'response_status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter history based on user permissions"""
        queryset = History.objects.all()
        
        # If user is not superuser, only show their tenant's history
        if not self.request.user.is_superuser:
            if self.request.user.tenant:
                queryset = queryset.filter(tenant=self.request.user.tenant)
            else:
                queryset = queryset.filter(user=self.request.user)
        
        return queryset


@swagger_auto_schema(
    method='get',
    operation_description="Get detailed information about a specific API history record",
    responses={
        200: openapi.Response(
            description="History record retrieved successfully",
            examples={
                "application/json": {
                    "id": "uuid-here",
                    "user": {
                        "id": 1,
                        "username": "john_doe",
                        "email": "john@example.com"
                    },
                    "tenant": {
                        "id": "uuid-here",
                        "name": "Acme Corp"
                    },
                    "method": "POST",
                    "endpoint": "/api/users/",
                    "request_data": {"username": "newuser", "email": "new@example.com"},
                    "response_status": 201,
                    "response_data": {"id": 2, "username": "newuser"},
                    "ip_address": "127.0.0.1",
                    "user_agent": "Mozilla/5.0...",
                    "execution_time": 0.123,
                    "error_message": None,
                    "created_at": "2024-01-01T12:00:00Z"
                }
            }
        ),
        404: openapi.Response(description="History record not found"),
        403: openapi.Response(description="Permission denied")
    },
    tags=['History']
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def history_detail(request, pk):
    """Get detailed information about a specific history record"""
    try:
        history = History.objects.get(pk=pk)
        
        # Check permissions
        if not request.user.is_superuser:
            if request.user.tenant and history.tenant != request.user.tenant:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            elif not request.user.tenant and history.user != request.user:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = HistorySerializer(history)
        return Response(serializer.data)
    
    except History.DoesNotExist:
        return Response({'error': 'History record not found'}, status=status.HTTP_404_NOT_FOUND)


@swagger_auto_schema(
    method='get',
    operation_description="Get API usage statistics for the current tenant",
    responses={
        200: openapi.Response(
            description="Statistics retrieved successfully",
            examples={
                "application/json": {
                    "total_requests": 150,
                    "requests_by_method": {
                        "GET": 80,
                        "POST": 45,
                        "PUT": 15,
                        "PATCH": 8,
                        "DELETE": 2
                    },
                    "requests_by_status": {
                        "200": 120,
                        "201": 25,
                        "400": 3,
                        "401": 2
                    },
                    "average_execution_time": 0.156,
                    "most_used_endpoints": [
                        {"endpoint": "/api/users/", "count": 45},
                        {"endpoint": "/api/auth/login/", "count": 30}
                    ],
                    "requests_today": 12,
                    "requests_this_week": 85
                }
            }
        )
    },
    tags=['History']
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def history_statistics(request):
    """Get API usage statistics"""
    queryset = History.objects.all()
    
    # Filter by tenant if user is not superuser
    if not request.user.is_superuser and request.user.tenant:
        queryset = queryset.filter(tenant=request.user.tenant)
    
    # Optional: filter by response status (status-wise statistics)
    status_param = request.query_params.get('status') or request.query_params.get('response_status')
    if status_param:
        try:
            queryset = queryset.filter(response_status=int(status_param))
        except (TypeError, ValueError):
            # Ignore invalid status values; proceed without status filtering
            pass
    
    # Calculate statistics
    total_requests = queryset.count()
    
    # Requests by method
    requests_by_method = {}
    for method, _ in History.HTTP_METHOD_CHOICES:
        count = queryset.filter(method=method).count()
        if count > 0:
            requests_by_method[method] = count
    
    # Requests by status
    requests_by_status = {}
    status_counts = queryset.values('response_status').annotate(count=models.Count('response_status'))
    for item in status_counts:
        requests_by_status[str(item['response_status'])] = item['count']
    
    # Average execution time
    avg_execution_time = queryset.aggregate(
        avg_time=models.Avg('execution_time')
    )['avg_time'] or 0
    
    # Most used endpoints (group by endpoint, method, and response status)
    most_used_endpoints = queryset.values('endpoint', 'method', 'response_status').annotate(
        count=models.Count('id')
    ).order_by('-count')
    
    # Requests today and this week
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    
    requests_today = queryset.filter(created_at__date=today).count()
    requests_this_week = queryset.filter(created_at__date__gte=week_ago).count()
    
    return Response({
        'total_requests': total_requests,
        'requests_by_method': requests_by_method,
        'requests_by_status': requests_by_status,
        'average_execution_time': round(avg_execution_time, 3),
        'most_used_endpoints': list(most_used_endpoints),
        'requests_today': requests_today,
        'requests_this_week': requests_this_week
    })


# Password Management

@swagger_auto_schema(
    method='post',
    operation_description="Change password for authenticated user",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'old_password': openapi.Schema(type=openapi.TYPE_STRING),
            'new_password': openapi.Schema(type=openapi.TYPE_STRING),
        },
        required=['old_password', 'new_password']
    ),
    tags=['Authentication']
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method='post',
    operation_description="Forgot password - send OTP to email",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL)},
        required=['email']
    ),
    tags=['Authentication']
)
@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password(request):
    from .models import PasswordResetOTP
    serializer = PasswordResetRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data['email']
    from django.db import connections
    # Safely capture current tenant context if set by middleware/router
    original_tenant = getattr(connections['default'], 'tenant', None)
    try:
        # Locate user by email across main and all tenants
        user = None
        connections['default'].tenant = None
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            for t in Tenant.objects.filter(is_active=True):
                connections['default'].tenant = t
                try:
                    user = CustomUser.objects.get(email=email)
                    break
                except CustomUser.DoesNotExist:
                    continue

        # Always generic response if user not found
        if not user:
            return Response({'message': 'OTP has been sent.'}, status=status.HTTP_200_OK)

        # Generate and store OTP (main DB)
        code = f"{random.randint(100000, 999999)}"
        expires_at = timezone.now() + timedelta(minutes=10)
        connections['default'].tenant = None
        PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)
        PasswordResetOTP.objects.create(user=user, code=code, expires_at=expires_at)

        # Send email
        subject = 'Your OTP for Password Reset'
        message = (
            'Use the following OTP to reset your password.\n\n'
            f'OTP: {code}\n'
            'This code expires in 10 minutes.\n\n'
            'If you did not request this, please ignore this email.'
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        except Exception:
            # Do not disclose anything
            pass

        return Response({'message': 'OTP has been sent.'}, status=status.HTTP_200_OK)
    finally:
        setattr(connections['default'], 'tenant', original_tenant)


@swagger_auto_schema(
    method='post',
    operation_description="Reset password using email + OTP",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
            'otp': openapi.Schema(type=openapi.TYPE_STRING),
            'new_password': openapi.Schema(type=openapi.TYPE_STRING),
        },
        required=['email', 'otp', 'new_password']
    ),
    tags=['Authentication']
)
@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password_confirm(request):
    from .serializers import ChangePasswordWithOTPSerializer
    serializer = ChangePasswordWithOTPSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({'message': 'Password has been reset successfully'}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# OTP helper types (no standalone endpoints now)


@swagger_auto_schema(
    method='post',
    operation_description="Request an OTP sent to email for password change/reset",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL)},
        required=['email']
    ),
    tags=['Authentication']
)
@api_view(['POST'])
@permission_classes([AllowAny])
def request_password_otp(request):
    serializer = PasswordOTPRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data['email']
    from django.db import connections
    original_tenant = getattr(connections['default'], 'tenant', None)
    try:
        # Find user by email in main or tenant DBs
        user = None
        user_tenant_name = ''
        setattr(connections['default'], 'tenant', None)
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            user = None

        if not user:
            for t in Tenant.objects.filter(is_active=True):
                setattr(connections['default'], 'tenant', t)
                try:
                    user = CustomUser.objects.get(email=email)
                    user_tenant_name = t.name
                    break
                except CustomUser.DoesNotExist:
                    continue

        # Always respond 200 (avoid enumeration), but only create OTP when user exists
        if not user:
            return Response({'message': 'OTP has been sent.'}, status=status.HTTP_200_OK)

        # Generate 6-digit numeric OTP
        code = f"{random.randint(100000, 999999)}"
        expires_at = timezone.now() + timedelta(minutes=10)

        # Store OTP in main DB regardless of tenant
        setattr(connections['default'], 'tenant', None)
        PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)
        PasswordResetOTP.objects.create(user=user, code=code, expires_at=expires_at)

        # Email the OTP
        subject = 'Your OTP for Password Change'
        message = (
            'Use the following OTP to change your password.\n\n'
            f'OTP: {code}\n'
            f'Tenant: {user_tenant_name or "(main)"}\n'
            'This code expires in 10 minutes.\n\n'
            'If you did not request this, please ignore this email.'
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        except Exception:
            # If email fails, don't reveal user existence
            return Response({'message': 'OTP has been sent.'}, status=status.HTTP_200_OK)

        return Response({'message': 'OTP has been sent.'}, status=status.HTTP_200_OK)
    finally:
        setattr(connections['default'], 'tenant', original_tenant)


@swagger_auto_schema(
    method='post',
    operation_description="Verify OTP sent to email",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
            'otp': openapi.Schema(type=openapi.TYPE_STRING),
        },
        required=['email', 'otp']
    ),
    tags=['Authentication']
)
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_password_otp(request):
    serializer = PasswordOTPVerifySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data['email']
    otp = serializer.validated_data['otp']

    from django.db import connections
    original_tenant = getattr(connections['default'], 'tenant', None)
    try:
        # Resolve user by email (main then tenants)
        user = None
        setattr(connections['default'], 'tenant', None)
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            for t in Tenant.objects.filter(is_active=True):
                setattr(connections['default'], 'tenant', t)
                try:
                    user = CustomUser.objects.get(email=email)
                    break
                except CustomUser.DoesNotExist:
                    continue

        # Always generic response on missing user/otp
        if not user:
            return Response({'message': 'OTP verified' if False else 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate OTP from main DB
        setattr(connections['default'], 'tenant', None)
        now = timezone.now()
        otp_obj = PasswordResetOTP.objects.filter(user=user, code=otp, is_used=False, expires_at__gte=now).order_by('-created_at').first()
        if not otp_obj:
            return Response({'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'OTP verified'}, status=status.HTTP_200_OK)
    finally:
        setattr(connections['default'], 'tenant', original_tenant)


@swagger_auto_schema(
    method='post',
    operation_description="Change password using email and OTP",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
            'otp': openapi.Schema(type=openapi.TYPE_STRING),
            'new_password': openapi.Schema(type=openapi.TYPE_STRING),
        },
        required=['email', 'otp', 'new_password']
    ),
    tags=['Authentication']
)
@api_view(['POST'])
@permission_classes([AllowAny])
def change_password_with_otp(request):
    serializer = ChangePasswordWithOTPSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ===== Tenant-scoped Permissions & Groups =====

def _resolve_tenant_for_admin(request):
    """
    For superusers, allow specifying tenant via X-Tenant header or ?tenant query.
    For regular tenant admins, use their own tenant.
    Returns (tenant_obj or None, error_response or None).
    """
    from django.db import connections

    user = request.user
    tenant_obj = None

    if getattr(user, "tenant", None):
        tenant_obj = user.tenant
    else:
        tenant_name = request.META.get("HTTP_X_TENANT") or request.GET.get("tenant")
        if tenant_name:
            try:
                tenant_obj = Tenant.objects.get(name=tenant_name, is_active=True)
            except Tenant.DoesNotExist:
                return None, Response({"error": "Tenant not found or inactive"}, status=status.HTTP_400_BAD_REQUEST)

    if not tenant_obj:
        return None, Response({"error": "No tenant associated or provided"}, status=status.HTTP_400_BAD_REQUEST)

    connections["default"].tenant = tenant_obj
    return tenant_obj, None


@method_decorator(
    name="get",
    decorator=swagger_auto_schema(
        tags=["Permissions"],
        operation_description="List all permissions available in the current tenant database "
        "(or main DB for tenant admins/superusers).",
    ),
)
class PermissionListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdminOrSuperuser]
    serializer_class = PermissionSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["codename", "name", "content_type__app_label"]

    def get_queryset(self):
        from django.db import connections

        # Route to correct DB (tenant or main)
        connections["default"].tenant = None
        if getattr(self.request.user, "tenant", None) and not self.request.user.is_superuser:
            connections["default"].tenant = self.request.user.tenant
        return Permission.objects.all().order_by("content_type__app_label", "codename")


@method_decorator(
    name="get",
    decorator=swagger_auto_schema(
        tags=["Permissions"],
        operation_description="List groups for the current tenant (or main DB for superusers).",
    ),
)
@method_decorator(
    name="post",
    decorator=swagger_auto_schema(
        tags=["Permissions"],
        operation_description="Create a new group for the current tenant and assign permissions.",
    ),
)
class GroupListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdminOrSuperuser]
    serializer_class = GroupSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]

    def get_queryset(self):
        from django.db import connections

        # Route to tenant DB or main DB
        connections["default"].tenant = None
        if getattr(self.request.user, "tenant", None) and not self.request.user.is_superuser:
            connections["default"].tenant = self.request.user.tenant
        return Group.objects.all().order_by("name")

    def perform_create(self, serializer):
        # DB routing handled in get_queryset by DRF internals (same DB alias)
        serializer.save()


@method_decorator(
    name="get",
    decorator=swagger_auto_schema(tags=["Permissions"], operation_description="Retrieve a group."),
)
@method_decorator(
    name="patch",
    decorator=swagger_auto_schema(tags=["Permissions"], operation_description="Update a group name/permissions."),
)
@method_decorator(
    name="delete",
    decorator=swagger_auto_schema(tags=["Permissions"], operation_description="Delete a group."),
)
class GroupDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsTenantAdminOrSuperuser]
    serializer_class = GroupSerializer
    lookup_field = "pk"

    def get_queryset(self):
        from django.db import connections

        connections["default"].tenant = None
        if getattr(self.request.user, "tenant", None) and not self.request.user.is_superuser:
            connections["default"].tenant = self.request.user.tenant
        return Group.objects.all().order_by("name")


@swagger_auto_schema(
    method="get",
    tags=["Permissions"],
    operation_description=(
        "Get effective permissions for a user in the current tenant (direct + via groups). "
        "Tenant admin/superuser only."
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantAdminOrSuperuser])
def user_permissions_detail(request, user_id):
    from django.db import connections

    try:
        # Route to tenant DB if applicable
        connections["default"].tenant = None
        if getattr(request.user, "tenant", None) and not request.user.is_superuser:
            connections["default"].tenant = request.user.tenant

        target_user = CustomUser.objects.get(pk=user_id)
        perms = target_user.get_all_permissions()
        return Response({"user_id": target_user.id, "permissions": sorted(list(perms))})
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    finally:
        try:
            connections["default"].tenant = None
        except Exception:
            pass


@swagger_auto_schema(
    method="post",
    tags=["Permissions"],
    request_body=UserGroupPermissionSerializer,
    operation_description=(
        "Assign groups and direct permissions to a user in the current tenant. "
        "Overwrites existing membership/permissions."
    ),
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsTenantAdminOrSuperuser])
def set_user_groups_permissions(request, user_id):
    from django.db import connections

    serializer = UserGroupPermissionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        connections["default"].tenant = None
        if getattr(request.user, "tenant", None) and not request.user.is_superuser:
            connections["default"].tenant = request.user.tenant

        try:
            target_user = CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        group_ids = serializer.validated_data.get("group_ids") or []
        perm_ids = serializer.validated_data.get("permission_ids") or []

        groups = Group.objects.filter(id__in=group_ids)
        perms = Permission.objects.filter(id__in=perm_ids)

        target_user.groups.set(groups)
        target_user.user_permissions.set(perms)

        return Response(
            {
                "user_id": target_user.id,
                "group_ids": list(groups.values_list("id", flat=True)),
                "permission_ids": list(perms.values_list("id", flat=True)),
            },
            status=status.HTTP_200_OK,
        )
    finally:
        try:
            connections["default"].tenant = None
        except Exception:
            pass
