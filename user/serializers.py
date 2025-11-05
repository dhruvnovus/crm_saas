from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import Tenant, TenantUser, CustomUser, History, PasswordResetOTP
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone


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
    tenant_name = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'tenant_name', 'first_name', 'last_name']
    
    def validate_username(self, value):
        """Ensure username is unique in the main database (for tenant admins)"""
        from django.db import connections
        # Tenant admins are stored in main database
        connections['default'].tenant = None
        if CustomUser.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value
    
    def validate_email(self, value):
        """Ensure email is unique in the main database (for tenant admins)"""
        if not value:
            return value
        from django.db import connections
        # Tenant admins are stored in main database
        connections['default'].tenant = None
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with that email already exists.")
        return value
    
    def validate(self, attrs):
        return attrs
    
    def create(self, validated_data):
        # Remove tenant_name from validated_data
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

            # After creating the tenant DB, run migrations to create all tables
            # so the tenant is ready to use immediately after registration
            try:
                from django.conf import settings
                from django.db import connections
                from django.core.management import call_command

                database_name = tenant.database_name

                # Add dynamic DB config for this tenant if not present
                if database_name not in connections.databases:
                    connections.databases[database_name] = {
                        'ENGINE': 'django.db.backends.mysql',
                        'NAME': database_name,
                        'USER': settings.DATABASES['default']['USER'],
                        'PASSWORD': settings.DATABASES['default']['PASSWORD'],
                        'HOST': settings.DATABASES['default']['HOST'],
                        'PORT': settings.DATABASES['default']['PORT'],
                        'OPTIONS': {
                            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                        },
                    }

                # Run migrations for the tenant database (creates user/customer/leads/authtoken tables, etc.)
                call_command('migrate', database=database_name, verbosity=0)
            except Exception:
                # If migrations fail here, we still allow registration to succeed;
                # tenant APIs will error until an admin fixes the DB.
                pass
        
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
    
    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        # Determine tenant from request context (header/subdomain), not from payload
        request = self.context.get('request') if hasattr(self, 'context') else None
        tenant_name = None
        if request is not None:
            # Prefer explicit header
            tenant_name = request.META.get('HTTP_X_TENANT')
            # If middleware has set request.tenant (object), use its name when header not present
            if not tenant_name and hasattr(request, 'tenant') and getattr(request, 'tenant', None):
                try:
                    tenant_name = getattr(request.tenant, 'name', None)
                except Exception:
                    tenant_name = None
        
        if username and password:
            # Allow login with email by converting to username if needed
            if '@' in username:
                try:
                    user_by_email = CustomUser.objects.get(email=username)
                    username = user_by_email.username
                except CustomUser.DoesNotExist:
                    pass
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
                # Final fallback: direct password check in main DB
                try:
                    candidate = CustomUser.objects.get(username=username)
                    if candidate.check_password(password):
                        user = candidate
                except CustomUser.DoesNotExist:
                    # Try resolve by email as a last resort
                    try:
                        candidate = CustomUser.objects.get(email=username)
                        if candidate.check_password(password):
                            user = candidate
                    except CustomUser.DoesNotExist:
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
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'tenant', 'is_tenant_admin', 'is_superuser', 'date_joined']
        read_only_fields = ['id', 'date_joined']
    
    def validate_username(self, value):
        """Ensure username is unique within the same tenant context"""
        # Get the current user instance if updating
        user = self.instance
        if not user:
            return value
        
        # Determine tenant context based on user type
        from django.db import connections
        original_tenant = connections['default'].tenant
        
        try:
            if getattr(user, 'is_tenant_admin', False):
                # Tenant admins are in main database
                connections['default'].tenant = None
            elif hasattr(user, 'tenant') and user.tenant:
                # Regular tenant users are in tenant database
                connections['default'].tenant = user.tenant
            else:
                # No tenant - check in main database
                connections['default'].tenant = None
            
            # Check if username is already taken by another user in the same tenant
            queryset = CustomUser.objects.filter(username=value)
            queryset = queryset.exclude(pk=user.pk)
            
            if queryset.exists():
                raise serializers.ValidationError("A user with that username already exists in this tenant.")
        finally:
            # Restore original tenant context
            connections['default'].tenant = original_tenant
        
        return value
    
    def validate_email(self, value):
        """Ensure email is unique within the same tenant context"""
        if not value:
            return value
        
        # Get the current user instance if updating
        user = self.instance
        if not user:
            return value
        
        # Determine tenant context based on user type
        from django.db import connections
        original_tenant = connections['default'].tenant
        
        try:
            if getattr(user, 'is_tenant_admin', False):
                # Tenant admins are in main database
                connections['default'].tenant = None
            elif hasattr(user, 'tenant') and user.tenant:
                # Regular tenant users are in tenant database
                connections['default'].tenant = user.tenant
            else:
                # No tenant - check in main database
                connections['default'].tenant = None
            
            # Check if email is already taken by another user in the same tenant
            queryset = CustomUser.objects.filter(email=value)
            queryset = queryset.exclude(pk=user.pk)
            
            if queryset.exists():
                raise serializers.ValidationError("A user with that email already exists in this tenant.")
        finally:
            # Restore original tenant context
            connections['default'].tenant = original_tenant
        
        return value


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
    
    def validate_username(self, value):
        """Ensure username is unique within the tenant database"""
        tenant = self.context.get('tenant')
        if not tenant:
            return value
        
        from django.db import connections
        connections['default'].tenant = tenant
        
        if CustomUser.objects.filter(username=value).exists():
            connections['default'].tenant = None
            raise serializers.ValidationError("A user with that username already exists in this tenant.")
        
        connections['default'].tenant = None
        return value
    
    def validate_email(self, value):
        """Ensure email is unique within the tenant database"""
        if not value:
            return value
        
        tenant = self.context.get('tenant')
        if not tenant:
            return value
        
        from django.db import connections
        connections['default'].tenant = tenant
        
        if CustomUser.objects.filter(email=value).exists():
            connections['default'].tenant = None
            raise serializers.ValidationError("A user with that email already exists in this tenant.")
        
        connections['default'].tenant = None
        return value
    
    def create(self, validated_data):
        """Create user with tenant context"""
        tenant = self.context['tenant']
        from django.db import connections
        # Ensure ORM targets the tenant database for this request
        connections['default'].tenant = tenant
        
        # Create the user inside the tenant database
        user = CustomUser.objects.create_user(
            tenant=tenant,
            **validated_data
        )
        
        # Create tenant-user mapping in the tenant database as well
        TenantUser.objects.get_or_create(user=user, tenant=tenant)
        
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for authenticated user to change password"""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs.get('old_password')):
            raise serializers.ValidationError({'old_password': _('Old password is incorrect')})
        validate_password(attrs.get('new_password'), user=user)
        return attrs

    def save(self, **kwargs):
        from django.db import connections
        user = self.context['request'].user
        new_password = self.validated_data['new_password']

        original_tenant = getattr(connections['default'], 'tenant', None)
        try:
            # Route to the DB where the user record lives
            # Tenant admins are stored in the main database even if they have a tenant relation
            if getattr(user, 'is_tenant_admin', False):
                setattr(connections['default'], 'tenant', None)
            elif hasattr(user, 'tenant') and user.tenant:
                setattr(connections['default'], 'tenant', user.tenant)
            else:
                setattr(connections['default'], 'tenant', None)

            user.set_password(new_password)
            # Persist only the password field
            user.save(update_fields=['password'])
            return user
        finally:
            setattr(connections['default'], 'tenant', original_tenant)


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for requesting a password reset via email"""
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer to confirm reset with uid, token and new password"""
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    tenant = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        uidb64 = attrs.get('uidb64')
        token = attrs.get('token')
        tenant_name = attrs.get('tenant')

        # Determine tenant context and resolve user
        from django.db import connections
        original_tenant = connections['default'].tenant
        try:
            if tenant_name:
                try:
                    tenant_obj = Tenant.objects.get(name=tenant_name, is_active=True)
                    connections['default'].tenant = tenant_obj
                except Tenant.DoesNotExist:
                    # If invalid tenant provided, treat as main DB
                    connections['default'].tenant = None
            else:
                connections['default'].tenant = None

            try:
                uid = force_str(urlsafe_base64_decode(uidb64))
            except Exception:
                raise serializers.ValidationError({'uidb64': _('Invalid uid')})

            try:
                user = CustomUser.objects.get(pk=uid)
            except CustomUser.DoesNotExist:
                raise serializers.ValidationError({'uidb64': _('User not found')})

            if not default_token_generator.check_token(user, token):
                raise serializers.ValidationError({'token': _('Invalid or expired token')})

            # Validate password via Django validators
            validate_password(attrs.get('new_password'), user=user)

            attrs['user'] = user
            return attrs
        finally:
            connections['default'].tenant = original_tenant

    def save(self, **kwargs):
        user = self.validated_data['user']
        new_password = self.validated_data['new_password']
        user.set_password(new_password)
        user.save(update_fields=['password'])
        return user


class PasswordOTPRequestSerializer(serializers.Serializer):
    """Serializer for requesting a password reset/change OTP by email"""
    email = serializers.EmailField()


class PasswordOTPVerifySerializer(serializers.Serializer):
    """Serializer for verifying an OTP for a given email"""
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)


class ChangePasswordWithOTPSerializer(serializers.Serializer):
    """Serializer for changing password using email + OTP"""
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        otp = attrs.get('otp')

        # Resolve user by email across main DB and tenants
        from django.db import connections
        original_tenant = getattr(connections['default'], 'tenant', None)
        user = None
        user_tenant = None
        try:
            # Try main db
            setattr(connections['default'], 'tenant', None)
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                user = None

            # Try tenants
            if not user:
                for t in Tenant.objects.filter(is_active=True):
                    setattr(connections['default'], 'tenant', t)
                    try:
                        found = CustomUser.objects.get(email=email)
                        user = found
                        user_tenant = t
                        break
                    except CustomUser.DoesNotExist:
                        continue

            if not user:
                raise serializers.ValidationError({'email': _('No account found for this email')})

            # OTP is stored in main DB; force main DB for OTP lookups
            setattr(connections['default'], 'tenant', None)
            now = timezone.now()
            try:
                otp_obj = PasswordResetOTP.objects.filter(user=user, code=otp, is_used=False, expires_at__gte=now).order_by('-created_at').first()
            except Exception:
                otp_obj = None

            if not otp_obj:
                raise serializers.ValidationError({'otp': _('Invalid or expired OTP')})

            # Validate password complexity
            validate_password(attrs.get('new_password'), user=user)

            attrs['user'] = user
            attrs['user_tenant'] = user_tenant
            attrs['otp_obj'] = otp_obj
            return attrs
        finally:
            setattr(connections['default'], 'tenant', original_tenant)

    def save(self, **kwargs):
        from django.db import connections
        user = self.validated_data['user']
        user_tenant = self.validated_data['user_tenant']
        otp_obj = self.validated_data['otp_obj']
        new_password = self.validated_data['new_password']

        original_tenant = getattr(connections['default'], 'tenant', None)
        try:
            # Save password in the DB where user lives
            if user_tenant:
                setattr(connections['default'], 'tenant', user_tenant)
            else:
                setattr(connections['default'], 'tenant', None)

            user.set_password(new_password)
            user.save(update_fields=['password'])

            # Mark OTP used in main DB
            setattr(connections['default'], 'tenant', None)
            otp_obj.is_used = True
            otp_obj.save(update_fields=['is_used', 'updated_at'])
            return user
        finally:
            setattr(connections['default'], 'tenant', original_tenant)
