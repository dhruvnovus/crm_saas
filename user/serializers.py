from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import Tenant, TenantUser, CustomUser, History


class TenantSerializer(serializers.ModelSerializer):
    """Serializer for Tenant model"""
    
    class Meta:
        model = Tenant
        fields = ['id', 'name', 'database_name', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'created_at', 'updated_at', 'database_name']


class TenantUserSerializer(serializers.ModelSerializer):
    """Serializer for TenantUser model"""
    
    class Meta:
        model = TenantUser
        fields = ['id', 'user', 'tenant', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    tenant_name = serializers.CharField(write_only=True)
    
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'password_confirm', 'tenant_name', 'first_name', 'last_name']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def create(self, validated_data):
        # Remove password_confirm and tenant_name from validated_data
        validated_data.pop('password_confirm')
        tenant_name = validated_data.pop('tenant_name')
        
        # Create or get tenant
        tenant, created = Tenant.objects.get_or_create(
            name=tenant_name,
            defaults={
                'database_name': f"crm_tenant_{tenant_name.lower().replace(' ', '_')}",
                'is_active': True
            }
        )
        
        if created:
            # Create database for new tenant
            tenant.create_database()
        
        # Create user
        user = CustomUser.objects.create_user(**validated_data)
        user.tenant = tenant
        user.is_tenant_admin = True
        user.save()
        
        # Create tenant user relationship
        TenantUser.objects.create(user=user, tenant=tenant)
        
        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for user login with automatic tenant detection"""
    username = serializers.CharField()
    password = serializers.CharField()
    tenant = serializers.CharField(required=False, help_text="Tenant name for tenant users (optional)")
    
    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        tenant_name = attrs.get('tenant')
        
        if username and password:
            # First try to authenticate against main database (for tenant admins)
            user = authenticate(username=username, password=password)
            
            # If not found in main database, try to find user in tenant databases
            if not user:
                try:
                    from django.db import connections
                    from .models import Tenant
                    
                    # If tenant is specified, try that tenant first
                    if tenant_name:
                        try:
                            tenants_to_try = [Tenant.objects.get(name=tenant_name, is_active=True)]
                        except Tenant.DoesNotExist:
                            raise serializers.ValidationError(f'Tenant "{tenant_name}" not found or not active')
                    else:
                        # Try all active tenants
                        tenants_to_try = Tenant.objects.filter(is_active=True)
                    
                    for tenant in tenants_to_try:
                        try:
                            # Set tenant context for database routing
                            connections['default'].tenant = tenant
                            
                            # Try to authenticate against tenant database
                            user = authenticate(username=username, password=password)
                            
                            if user:
                                # Clear tenant context to avoid side effects
                                connections['default'].tenant = None
                                break
                                
                        except Exception as e:
                            # Clear tenant context in case of any error
                            connections['default'].tenant = None
                            continue
                        finally:
                            # Ensure tenant context is cleared
                            connections['default'].tenant = None
                    
                except Exception as e:
                    # Clear tenant context in case of any error
                    connections['default'].tenant = None
                    # Re-raise validation errors (like tenant not found)
                    if isinstance(e, serializers.ValidationError):
                        raise e
                    pass
            
            if not user:
                if tenant_name:
                    raise serializers.ValidationError(f'Invalid credentials for user "{username}" in tenant "{tenant_name}"')
                else:
                    raise serializers.ValidationError(f'Invalid credentials for user "{username}". Please check your username and password.')
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled')
            attrs['user'] = user
        else:
            raise serializers.ValidationError('Must include username and password')
        
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user details"""
    tenant = TenantSerializer(read_only=True)
    
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'tenant', 'is_tenant_admin', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class HistorySerializer(serializers.ModelSerializer):
    """Serializer for History model"""
    user = UserSerializer(read_only=True)
    tenant = TenantSerializer(read_only=True)
    
    class Meta:
        model = History
        fields = [
            'id', 'user', 'tenant', 'method', 'endpoint', 'request_data',
            'response_status', 'response_data', 'ip_address', 'user_agent',
            'execution_time', 'error_message', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'tenant', 'method', 'endpoint', 'request_data',
            'response_status', 'response_data', 'ip_address', 'user_agent',
            'execution_time', 'error_message', 'created_at', 'updated_at'
        ]


class HistoryListSerializer(serializers.ModelSerializer):
    """Simplified serializer for History list view"""
    user_username = serializers.CharField(source='user.username', read_only=True)
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    
    class Meta:
        model = History
        fields = [
            'id', 'user_username', 'tenant_name', 'method', 'endpoint',
            'response_status', 'ip_address', 'execution_time', 'error_message', 'created_at'
        ]
        read_only_fields = [
            'id', 'user_username', 'tenant_name', 'method', 'endpoint',
            'response_status', 'ip_address', 'execution_time', 'error_message', 'created_at'
        ]


class CreateTenantUserSerializer(serializers.ModelSerializer):
    """Serializer for creating a new user within a tenant"""
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'first_name', 'last_name']
    
    def create(self, validated_data):
        """Create user with tenant context"""
        tenant = self.context['tenant']
        # Always create user in main database (simplified approach)
        # TODO: Implement proper tenant database user management
        user = CustomUser.objects.create_user(
            tenant=tenant,
            **validated_data
        )
        
        # Create tenant user relationship in main database
        TenantUser.objects.create(user=user, tenant=tenant)
        
        return user
