#!/usr/bin/env python3
"""
Management command to create Token table in tenant database
"""
from django.core.management.base import BaseCommand
from django.db import connections
from user.models import Tenant


class Command(BaseCommand):
    help = 'Create Token table in tenant database'

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
            
            # Connect to tenant database
            tenant_connection = connections[tenant_db_name]
            
            # Create Token table
            create_token_table_sql = """
            CREATE TABLE IF NOT EXISTS `authtoken_token` (
                `key` varchar(40) NOT NULL PRIMARY KEY,
                `user_id` bigint NOT NULL,
                `created` datetime(6) NOT NULL,
                CONSTRAINT `authtoken_token_user_id_35299eff_fk_user_customuser_id` 
                FOREIGN KEY (`user_id`) REFERENCES `user_customuser` (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            
            with tenant_connection.cursor() as cursor:
                cursor.execute(create_token_table_sql)
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created Token table in tenant database: {tenant_db_name}')
            )
            
        except Tenant.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Tenant "{tenant_name}" not found or not active')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating Token table: {str(e)}')
            )
