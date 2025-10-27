from django.core.management.base import BaseCommand
from django.db import connection
from user.models import Tenant
from user.database_service import DatabaseService


class Command(BaseCommand):
    help = 'Set up tenant database and run migrations'
    
    def add_arguments(self, parser):
        parser.add_argument('tenant_name', type=str, help='Name of the tenant')
        parser.add_argument('--database-name', type=str, help='Database name for the tenant')
    
    def handle(self, *args, **options):
        tenant_name = options['tenant_name']
        database_name = options.get('database_name') or f"crm_tenant_{tenant_name.lower().replace(' ', '_')}"
        
        self.stdout.write(f"Setting up tenant: {tenant_name}")
        self.stdout.write(f"Database name: {database_name}")
        
        # Create tenant record
        tenant, created = Tenant.objects.get_or_create(
            name=tenant_name,
            defaults={
                'database_name': database_name,
                'is_active': True
            }
        )
        
        if created:
            self.stdout.write(f"Created tenant record: {tenant.name}")
        else:
            self.stdout.write(f"Tenant already exists: {tenant.name}")
        
        # Create database
        if DatabaseService.create_tenant_database(tenant_name, database_name):
            self.stdout.write(self.style.SUCCESS(f"Successfully created database: {database_name}"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to create database: {database_name}"))
