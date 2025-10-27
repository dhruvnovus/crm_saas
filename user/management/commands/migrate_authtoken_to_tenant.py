#!/usr/bin/env python3
"""
Management command to migrate authtoken tables to tenant database
"""
from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from user.models import Tenant


class Command(BaseCommand):
    help = 'Migrate authtoken tables to tenant database'

    def add_arguments(self, parser):
        parser.add_argument('tenant_name', type=str, help='Tenant name')

    def handle(self, *args, **options):
        tenant_name = options['tenant_name']
        
        try:
            tenant = Tenant.objects.get(name=tenant_name, is_active=True)
            self.stdout.write(f"Found tenant: {tenant.name}")
            
            # Get tenant database connection
            tenant_db_name = tenant.database_name
            
            # Create tenant database connection if it doesn't exist
            if tenant_db_name not in connections.databases:
                from user.routers import TenantDatabaseRouter
                router = TenantDatabaseRouter()
                router._get_tenant_connection(tenant)
            
            # Set tenant context
            connections['default'].tenant = tenant
            
            # Run authtoken migrations on tenant database
            from django.core.management import call_command
            
            self.stdout.write(f"Running authtoken migrations on tenant database: {tenant_db_name}")
            call_command('migrate', 'authtoken', database=tenant_db_name, verbosity=2)
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully migrated authtoken tables to tenant database: {tenant_db_name}')
            )
            
        except Tenant.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Tenant "{tenant_name}" not found or not active')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error migrating authtoken tables: {str(e)}')
            )
