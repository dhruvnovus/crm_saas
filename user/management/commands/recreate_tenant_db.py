from django.core.management.base import BaseCommand
from django.conf import settings
import mysql.connector


class Command(BaseCommand):
    help = 'Recreate tenant database with correct structure'
    
    def add_arguments(self, parser):
        parser.add_argument('tenant_name', type=str, help='Name of the tenant')
    
    def handle(self, *args, **options):
        tenant_name = options['tenant_name']
        database_name = f"crm_tenant_{tenant_name.lower()}"
        
        try:
            # Connect to MySQL server
            connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT']
            )
            
            cursor = connection.cursor()
            
            # Drop and recreate database
            cursor.execute(f"DROP DATABASE IF EXISTS `{database_name}`")
            cursor.execute(f"CREATE DATABASE `{database_name}`")
            cursor.execute(f"USE `{database_name}`")
            
            # Create user_customuser table with correct structure
            create_user_table = """
            CREATE TABLE user_customuser (
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
            
            # Create user_tenantuser table
            create_tenant_user_table = """
            CREATE TABLE user_tenantuser (
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
            
            # Create auth_token table
            create_token_table = """
            CREATE TABLE authtoken_token (
                `key` varchar(40) NOT NULL PRIMARY KEY,
                created datetime(6) NOT NULL,
                user_id bigint NOT NULL UNIQUE,
                INDEX authtoken_token_user_id (user_id),
                FOREIGN KEY (user_id) REFERENCES user_customuser (id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            
            # Execute table creation
            cursor.execute(create_user_table)
            cursor.execute(create_tenant_user_table)
            cursor.execute(create_token_table)
            
            connection.commit()
            cursor.close()
            connection.close()
            
            self.stdout.write(self.style.SUCCESS(f"Successfully recreated tenant database: {database_name}"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
