from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from user.models import Tenant
from user.database_service import DatabaseService


class Command(BaseCommand):
    help = 'Run migrations for a specific tenant database'
    
    def add_arguments(self, parser):
        parser.add_argument('tenant_name', type=str, help='Name of the tenant')
        parser.add_argument('--create', action='store_true', help='Create tenant database if it does not exist')
    
    def handle(self, *args, **options):
        tenant_name = options['tenant_name']
        create_db = options['create']
        
        try:
            # Get tenant from main database
            tenant = Tenant.objects.get(name=tenant_name)
            database_name = tenant.database_name
            
            self.stdout.write(f"Found tenant: {tenant.name} with database: {database_name}")
            
            # Create database connection configuration
            tenant_db_config = {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': database_name,
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
            }
            
            # Add tenant database to connections
            connections.databases[database_name] = tenant_db_config
            
            # Test connection
            try:
                connection = connections[database_name]
                connection.ensure_connection()
                self.stdout.write(f"Successfully connected to tenant database: {database_name}")
            except Exception as e:
                if create_db:
                    self.stdout.write(f"Database {database_name} does not exist. Creating...")
                    if DatabaseService.create_tenant_database(tenant_name, database_name):
                        self.stdout.write(self.style.SUCCESS(f"Successfully created database: {database_name}"))
                        # Re-add connection after creation
                        connections.databases[database_name] = tenant_db_config
                    else:
                        self.stdout.write(self.style.ERROR(f"Failed to create database: {database_name}"))
                        return
                else:
                    self.stdout.write(self.style.ERROR(f"Cannot connect to database {database_name}: {e}"))
                    return
            
            # Run migrations
            self.stdout.write(f"Running migrations for tenant database: {database_name}")
            from django.core.management import call_command
            
            # Use fake_initial=True to handle tables created by setup_tenant_tables
            # This will mark existing migrations as applied without recreating tables
            call_command('migrate', database=database_name, fake_initial=True, verbosity=1)
            # Then apply any new migrations that don't exist yet
            call_command('migrate', database=database_name, verbosity=1)
            self.stdout.write(self.style.SUCCESS(f"Successfully migrated tenant database: {database_name}"))
            
        except Tenant.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Tenant '{tenant_name}' not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
