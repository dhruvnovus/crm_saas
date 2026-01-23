from django.conf import settings
from django.db import connection, connections
from user.models import Tenant


class TenantDatabaseRouter:
    """Database router for multi-tenant architecture"""
    
    def _get_tenant_connection(self, tenant):
        """Get or create tenant database connection"""
        tenant_db_name = tenant.database_name
        
        # Check if connection already exists
        if tenant_db_name in connections.databases:
            return tenant_db_name
        
        # Create tenant database connection
        tenant_db_config = {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': tenant_db_name,
            'USER': settings.DATABASES['default']['USER'],
            'PASSWORD': settings.DATABASES['default']['PASSWORD'],
            'HOST': settings.DATABASES['default']['HOST'],
            'PORT': settings.DATABASES['default']['PORT'],
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            'ATOMIC_REQUESTS': False,
            'AUTOCOMMIT': True,
            'CONN_HEALTH_CHECKS': False,
            'CONN_MAX_AGE': 0,
            'TIME_ZONE': None,
            'TEST': {
                'CHARSET': None,
                'COLLATION': None,
                'MIGRATE': True,
                'MIRROR': None,
                'NAME': None,
            },
        }
        
        # Add tenant database to connections
        connections.databases[tenant_db_name] = tenant_db_config
        return tenant_db_name
    
    def db_for_read(self, model, **hints):
        """Point all read operations to the tenant database"""
        if hasattr(model, '_meta'):
            # Handle user app models
            if model._meta.app_label == 'user':
                # History and Tenant stay in main database
                if model._meta.model_name in ['history', 'tenant']:
                    return 'default'
                # For users and tenant-user relationships, use the tenant database
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                # If no tenant context, use default database
                return 'default'
            
            # Handle customer app models
            if model._meta.app_label == 'customer':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle leads app models
            if model._meta.app_label == 'leads':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle branch app models
            if model._meta.app_label == 'branch':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle category app models
            if model._meta.app_label == 'category':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle auth/contenttypes for tenant-scoped permissions/groups
            if model._meta.app_label in ['auth', 'contenttypes']:
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle authtoken app models (Token model)
            elif model._meta.app_label == 'authtoken':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'
        
        return None
    
    def db_for_write(self, model, **hints):
        """Point all write operations to the tenant database"""
        if hasattr(model, '_meta'):
            # Handle user app models
            if model._meta.app_label == 'user':
                # History and Tenant stay in main database
                if model._meta.model_name in ['history', 'tenant']:
                    return 'default'
                # For users and tenant-user relationships, use the tenant database
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                # If no tenant context, use default database
                return 'default'
            
            # Handle customer app models
            if model._meta.app_label == 'customer':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle leads app models
            if model._meta.app_label == 'leads':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle branch app models
            if model._meta.app_label == 'branch':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle category app models
            if model._meta.app_label == 'category':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle auth/contenttypes for tenant-scoped permissions/groups
            if model._meta.app_label in ['auth', 'contenttypes']:
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'

            # Handle authtoken app models (Token model)
            elif model._meta.app_label == 'authtoken':
                tenant = getattr(connection, 'tenant', None)
                if tenant:
                    return self._get_tenant_connection(tenant)
                return 'default'
        
        return None
    
    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations between objects in the same database"""
        return True
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Control which migrations run on which databases"""
        if app_label == 'user':
            # Ensure Tenant and History live only in the main database
            if model_name in ['tenant', 'history']:
                return db == 'default'
            # Migrate CustomUser and TenantUser in BOTH default and tenant databases
            # - Default DB: required for Django admin (django_admin_log.user FK)
            # - Tenant DBs: required for tenant-scoped data relations
            if model_name in ['customuser', 'tenantuser']:
                return True
            # Any other models in user app should default to main DB only
            return db == 'default'
        elif app_label == 'authtoken':
            # Ensure Token model exists in both default and tenant databases
            # so superusers (default DB) and tenant users can authenticate
            return True
        elif app_label in ['auth', 'contenttypes']:
            # Permissions, groups, and content types should exist in both
            # the default DB and tenant DBs so each tenant has isolated roles
            return True
        elif app_label == 'customer':
            # Customer tables should live only in tenant databases
            return db != 'default'
        elif app_label == 'leads':
            # Lead tables should live only in tenant databases
            return db != 'default'
        elif app_label == 'branch':
            # Branch tables should live only in tenant databases
            return db != 'default'
        elif app_label == 'category':
            # Category tables should live only in tenant databases
            return db != 'default'
        return db == 'default'
