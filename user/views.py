from rest_framework import status, generics, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
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
    CreateTenantUserSerializer
)


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
    operation_description="Login user and get authentication token. Tenant field is optional - if not provided, system will try to authenticate against main database first, then all tenant databases.",
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
    # Get tenant from header if not provided in data (optional for frontend)
    login_data = request.data.copy()
    if 'tenant' not in login_data:
        tenant_name = request.META.get('HTTP_X_TENANT')
        if tenant_name:
            login_data['tenant'] = tenant_name
        # If no tenant provided, that's fine - the serializer will handle it
    
    serializer = UserLoginSerializer(data=login_data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # Handle token creation - for now, always use main database
        # TODO: Implement proper tenant database user management
        try:
            # Always create token in main database for now
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
    tags=['User Profile']
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    """Get current user profile"""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """Update user profile"""
    serializer = UserSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TenantListCreateView(generics.ListCreateAPIView):
    """List and create tenants (admin only)"""
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Only show tenants for the current user
        if self.request.user.is_superuser:
            return Tenant.objects.all()
        return Tenant.objects.filter(tenantuser__user=self.request.user)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tenant_users(request):
    """Get users for current tenant"""
    if not request.user.tenant:
        return Response({'error': 'No tenant associated'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Set tenant context for database routing
    from django.db import connections
    connections['default'].tenant = request.user.tenant
    
    # Query users from tenant database
    tenant_users = CustomUser.objects.all()
    serializer = UserSerializer(tenant_users, many=True)
    return Response(serializer.data)


@swagger_auto_schema(
    method='post',
    operation_description="Create a new user within the current tenant",
    request_body=CreateTenantUserSerializer,
    responses={
        201: openapi.Response(
            description="User created successfully",
            examples={
                "application/json": {
                    "id": 4,
                    "username": "newuser",
                    "email": "newuser@example.com",
                    "first_name": "New",
                    "last_name": "User",
                    "tenant": {
                        "id": "uuid-here",
                        "name": "TestTenant"
                    },
                    "is_tenant_admin": False,
                    "date_joined": "2024-01-01T00:00:00Z"
                }
            }
        ),
        400: openapi.Response(description="Bad request - validation errors"),
        403: openapi.Response(description="Permission denied")
    },
    tags=['Tenant Management']
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_tenant_user(request):
    """Create a new user within the current tenant"""
    if not request.user.tenant or not request.user.is_tenant_admin:
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    # Create user in main database (simplified approach)
    # TODO: Implement proper tenant database user management
    serializer = CreateTenantUserSerializer(
        data=request.data, 
        context={'tenant': request.user.tenant}
    )
    
    if serializer.is_valid():
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
    
    # Most used endpoints
    most_used_endpoints = queryset.values('endpoint').annotate(
        count=models.Count('endpoint')
    ).order_by('-count')[:5]
    
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
