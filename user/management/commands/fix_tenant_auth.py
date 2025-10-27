#!/usr/bin/env python3
"""
Management command to fix authentication issues for a tenant
This command ensures all necessary authentication tables exist in the tenant database
"""
from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from user.models import Tenant
import mysql.connector


class Command(BaseCommand):
    help = 'Fix authentication issues for a tenant by ensuring all auth tables exist'

    def add_arguments(self, parser):
        parser.add_argument('tenant_name', type=str, help='Name of the tenant')
        parser.add_argument('--all', action='store_true', help='Fix all active tenants')

    def handle(self, *args, **options):
        tenant_name = options['tenant_name']
        fix_all = options['all']
        
        if fix_all:
            self.stdout.write("Fixing authentication for all active tenants...")
            tenants = Tenant.objects.filter(is_active=True)
            for tenant in tenants:
                self._fix_tenant_auth(tenant)
        else:
            try:
                tenant = Tenant.objects.get(name=tenant_name, is_active=True)
                self._fix_tenant_auth(tenant)
            except Tenant.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Tenant "{tenant_name}" not found or not active')
                )

    def _fix_tenant_auth(self, tenant):
        """Fix authentication for a specific tenant"""
        try:
            database_name = tenant.database_name
            self.stdout.write(f"Fixing authentication for tenant: {tenant.name} (DB: {database_name})")
            
            # Connect to MySQL and create tables directly
            connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT'],
                database=database_name
            )
            
            cursor = connection.cursor()
            
            # Check if tables exist and create them if they don't
            tables_to_check = [
                ('user_customuser', self._get_user_table_sql()),
                ('user_tenantuser', self._get_tenant_user_table_sql()),
                ('authtoken_token', self._get_token_table_sql()),
            ]
            
            for table_name, create_sql in tables_to_check:
                try:
                    # Check if table exists
                    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
                    if not cursor.fetchone():
                        self.stdout.write(f"Creating missing table: {table_name}")
                        cursor.execute(create_sql)
                    else:
                        self.stdout.write(f"Table {table_name} already exists")
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f"Could not create table {table_name}: {str(e)}")
                    )
            
            connection.commit()
            cursor.close()
            connection.close()
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully fixed authentication for tenant: {tenant.name}')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error fixing authentication for tenant {tenant.name}: {str(e)}')
            )

    def _get_user_table_sql(self):
        """Get SQL for creating user table"""
        return """
        CREATE TABLE IF NOT EXISTS user_customuser (
            id bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
            password varchar(128) NOT NULL,
            last_login datetime(6) NULL,
            is_superuser bool NOT NULL,
            username varchar(150) NOT NULL UNIQUE,
            first_name varchar(150) NOT NULL,
            last_name varchar(150) NOT NULL,
            email varchar(254) NOT NULL,
            is_staff bool NOT NULL,
            is_active bool NOT NULL,
            date_joined datetime(6) NOT NULL,
            tenant_id varchar(36) NULL,
            is_tenant_admin bool NOT NULL,
            INDEX user_customuser_username (username),
            INDEX user_customuser_email (email),
            INDEX user_customuser_tenant_id (tenant_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """

    def _get_tenant_user_table_sql(self):
        """Get SQL for creating tenant user table"""
        return """
        CREATE TABLE IF NOT EXISTS user_tenantuser (
            id bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
            created_at datetime(6) NOT NULL,
            updated_at datetime(6) NOT NULL,
            user_id bigint NOT NULL UNIQUE,
            tenant_id varchar(36) NOT NULL,
            INDEX user_tenantuser_user_id (user_id),
            INDEX user_tenantuser_tenant_id (tenant_id),
            FOREIGN KEY (user_id) REFERENCES user_customuser (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """

    def _get_token_table_sql(self):
        """Get SQL for creating token table"""
        return """
        CREATE TABLE IF NOT EXISTS authtoken_token (
            `key` varchar(40) NOT NULL PRIMARY KEY,
            created datetime(6) NOT NULL,
            user_id bigint NOT NULL UNIQUE,
            INDEX authtoken_token_user_id (user_id),
            FOREIGN KEY (user_id) REFERENCES user_customuser (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
