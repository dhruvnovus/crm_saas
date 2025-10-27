from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.conf import settings
from user.models import Tenant
import mysql.connector
from django.core.management import call_command
import os
import sys


class Command(BaseCommand):
    help = 'Set up required tables for a tenant database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=str,
            help='Tenant ID to set up tables for',
        )
        parser.add_argument(
            '--database-name',
            type=str,
            help='Database name to set up tables for',
        )
        parser.add_argument(
            '--all-tenants',
            action='store_true',
            help='Set up tables for all existing tenants',
        )
        parser.add_argument(
            '--fix-foreign-keys',
            action='store_true',
            help='Fix foreign key constraints in all tenant databases',
        )

    def handle(self, *args, **options):
        if options['fix_foreign_keys']:
            self.fix_all_tenant_foreign_keys()
        elif options['all_tenants']:
            self.setup_all_tenants()
        elif options['tenant_id']:
            self.setup_tenant_by_id(options['tenant_id'])
        elif options['database_name']:
            self.setup_tenant_by_database_name(options['database_name'])
        else:
            raise CommandError('Please specify --tenant-id, --database-name, --all-tenants, or --fix-foreign-keys')

    def setup_all_tenants(self):
        """Set up tables for all existing tenants"""
        tenants = Tenant.objects.filter(is_active=True)
        self.stdout.write(f'Found {tenants.count()} active tenants')
        
        for tenant in tenants:
            self.stdout.write(f'Setting up tables for tenant: {tenant.name} ({tenant.database_name})')
            success = self.setup_tenant_tables(tenant.database_name)
            if success:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully set up tables for tenant: {tenant.name}')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Failed to set up tables for tenant: {tenant.name}')
                )

    def setup_tenant_by_id(self, tenant_id):
        """Set up tables for a specific tenant by ID"""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_active=True)
            self.stdout.write(f'Setting up tables for tenant: {tenant.name} ({tenant.database_name})')
            success = self.setup_tenant_tables(tenant.database_name)
            if success:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully set up tables for tenant: {tenant.name}')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Failed to set up tables for tenant: {tenant.name}')
                )
        except Tenant.DoesNotExist:
            raise CommandError(f'Tenant with ID {tenant_id} not found or not active')

    def setup_tenant_by_database_name(self, database_name):
        """Set up tables for a specific tenant by database name"""
        self.stdout.write(f'Setting up tables for database: {database_name}')
        success = self.setup_tenant_tables(database_name)
        if success:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully set up tables for database: {database_name}')
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'Failed to set up tables for database: {database_name}')
            )

    def setup_tenant_tables(self, database_name):
        """Set up all required tables in the tenant database"""
        try:
            # Check if database exists
            if not self.database_exists(database_name):
                self.stdout.write(
                    self.style.ERROR(f'Database {database_name} does not exist')
                )
                return False

            # Connect to the tenant database
            connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT'],
                database=database_name
            )
            
            cursor = connection.cursor()
            
            # Check if tables already exist
            cursor.execute("SHOW TABLES")
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            if existing_tables:
                self.stdout.write(f'Database {database_name} has {len(existing_tables)} tables: {existing_tables}')
                # Check if all required tables exist
                required_tables = [
                    'django_content_type', 'auth_permission', 'auth_group',
                    'auth_group_permissions', 'django_migrations', 'django_session',
                    'django_admin_log', 'user_customuser', 'user_tenantuser', 
                    'user_history', 'auth_user_groups', 'auth_user_user_permissions', 
                    'authtoken_token'
                ]
                missing_tables = [table for table in required_tables if table not in existing_tables]
                if not missing_tables:
                    self.stdout.write('All required tables already exist')
                    cursor.close()
                    connection.close()
                    return True
                else:
                    self.stdout.write(f'Missing tables: {missing_tables}, will create them')

            # Create tables by copying structure from main database
            self.stdout.write(f'Creating tables in database: {database_name}')
            
            # Disable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            
            # Get table creation statements from main database
            main_connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT'],
                database=settings.DATABASES['default']['NAME']
            )
            
            main_cursor = main_connection.cursor()
            
            # Get all tables from main database
            main_cursor.execute("SHOW TABLES")
            main_tables = [row[0] for row in main_cursor.fetchall()]
            
            # Required tables for tenant database (in dependency order)
            # Note: user_tenant table should NOT be in tenant databases
            required_tables = [
                'django_content_type',
                'auth_permission', 
                'auth_group',
                'auth_group_permissions',
                'django_migrations',
                'django_session',
                'django_admin_log',
                'user_customuser',
                'user_tenantuser',
                'user_history',
                'auth_user_groups',
                'auth_user_user_permissions',
                'authtoken_token'
            ]
            
            # Create each required table
            for table_name in required_tables:
                if table_name in main_tables:
                    # Check if table already exists in tenant database
                    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
                    if cursor.fetchone():
                        self.stdout.write(f'Table {table_name} already exists, skipping')
                        continue
                    
                    # Get CREATE TABLE statement
                    main_cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
                    create_statement = main_cursor.fetchone()[1]
                    
                    # Execute CREATE TABLE in tenant database
                    cursor.execute(create_statement)
                    self.stdout.write(f'Created table: {table_name}')
                else:
                    self.stdout.write(f'Warning: Table {table_name} not found in main database')
            
            # Create missing Django built-in tables
            self.create_django_builtin_tables(cursor)
            
            # Always fix user tables to remove tenant foreign key constraints
            self.fix_user_customuser_table(cursor)
            
            # Re-enable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            
            # Copy data from main database for system tables
            system_tables = ['django_content_type', 'auth_permission', 'auth_group']
            for table_name in system_tables:
                if table_name in main_tables:
                    # Check if table already has data
                    cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                    existing_count = cursor.fetchone()[0]
                    
                    if existing_count > 0:
                        self.stdout.write(f'Table {table_name} already has data ({existing_count} rows), skipping')
                        continue
                    
                    # Get data from main database
                    main_cursor.execute(f"SELECT * FROM `{table_name}`")
                    rows = main_cursor.fetchall()
                    
                    if rows:
                        # Get column names
                        main_cursor.execute(f"DESCRIBE `{table_name}`")
                        columns = [row[0] for row in main_cursor.fetchall()]
                        
                        # Insert data into tenant database
                        placeholders = ', '.join(['%s'] * len(columns))
                        insert_query = f"INSERT INTO `{table_name}` ({', '.join([f'`{col}`' for col in columns])}) VALUES ({placeholders})"
                        
                        cursor.executemany(insert_query, rows)
                        self.stdout.write(f'Copied data to table: {table_name} ({len(rows)} rows)')
            
            # Commit changes
            connection.commit()
            
            # Verify tables were created
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Define required tables for verification (excluding user_tenant)
            required_tables = [
                'django_content_type', 'auth_permission', 'auth_group',
                'auth_group_permissions', 'django_migrations', 'django_session',
                'django_admin_log', 'user_customuser', 'user_tenantuser', 
                'user_history', 'auth_user_groups', 'auth_user_user_permissions', 
                'authtoken_token'
            ]
            
            missing_tables = [table for table in required_tables if table not in tables]
            
            if missing_tables:
                self.stdout.write(
                    self.style.WARNING(f'Missing tables in {database_name}: {missing_tables}')
                )
                cursor.close()
                connection.close()
                main_cursor.close()
                main_connection.close()
                return False
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'All required tables created in {database_name}')
                )
                cursor.close()
                connection.close()
                main_cursor.close()
                main_connection.close()
                return True

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error setting up tables for {database_name}: {str(e)}')
            )
            return False

    def create_django_builtin_tables(self, cursor):
        """Create Django built-in tables that might be missing"""
        
        # Create django_session table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `django_session` (
                `session_key` varchar(40) NOT NULL PRIMARY KEY,
                `session_data` longtext NOT NULL,
                `expire_date` datetime(6) NOT NULL
            )
        """)
        self.stdout.write('Created table: django_session')
        
        # Create auth_user_groups table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `auth_user_groups` (
                `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
                `user_id` bigint NOT NULL,
                `group_id` int NOT NULL,
                UNIQUE KEY `auth_user_groups_user_id_group_id_94350c0c_uniq` (`user_id`, `group_id`),
                KEY `auth_user_groups_user_id_6a12ed8b` (`user_id`),
                KEY `auth_user_groups_group_id_97559544` (`group_id`)
            )
        """)
        self.stdout.write('Created table: auth_user_groups')
        
        # Create auth_user_user_permissions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `auth_user_user_permissions` (
                `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
                `user_id` bigint NOT NULL,
                `permission_id` int NOT NULL,
                UNIQUE KEY `auth_user_user_permissions_user_id_permission_id_14a6b632_uniq` (`user_id`, `permission_id`),
                KEY `auth_user_user_permissions_user_id_a95ead1b` (`user_id`),
                KEY `auth_user_user_permissions_permission_id_1fbb5f2c` (`permission_id`)
            )
        """)
        self.stdout.write('Created table: auth_user_user_permissions')

    def fix_user_customuser_table(self, cursor):
        """Fix user_customuser and user_tenantuser tables to remove tenant foreign key constraints"""
        try:
            # Fix user_customuser table
            cursor.execute("SHOW TABLES LIKE 'user_customuser'")
            if cursor.fetchone():
                cursor.execute("SHOW CREATE TABLE user_customuser")
                create_statement = cursor.fetchone()[1]
                
                if 'CONSTRAINT `user_customuser_ibfk_1`' in create_statement:
                    self.stdout.write('Fixing user_customuser table - removing tenant foreign key constraint')
                    cursor.execute("ALTER TABLE user_customuser DROP FOREIGN KEY user_customuser_ibfk_1")
                    cursor.execute("ALTER TABLE user_customuser MODIFY COLUMN tenant_id char(32) NULL")
                    self.stdout.write('Fixed user_customuser table')
                else:
                    self.stdout.write('user_customuser table is already fixed')
            
            # Fix user_tenantuser table
            cursor.execute("SHOW TABLES LIKE 'user_tenantuser'")
            if cursor.fetchone():
                cursor.execute("SHOW CREATE TABLE user_tenantuser")
                create_statement = cursor.fetchone()[1]
                
                if 'CONSTRAINT `user_tenantuser_ibfk_1`' in create_statement:
                    self.stdout.write('Fixing user_tenantuser table - removing tenant foreign key constraint')
                    cursor.execute("ALTER TABLE user_tenantuser DROP FOREIGN KEY user_tenantuser_ibfk_1")
                    cursor.execute("ALTER TABLE user_tenantuser MODIFY COLUMN tenant_id char(32) NULL")
                    self.stdout.write('Fixed user_tenantuser table')
                else:
                    self.stdout.write('user_tenantuser table is already fixed')
                
        except Exception as e:
            self.stdout.write(f'Warning: Could not fix user tables: {str(e)}')

    def fix_all_tenant_foreign_keys(self):
        """Fix foreign key constraints in all tenant databases"""
        tenants = Tenant.objects.filter(is_active=True)
        self.stdout.write(f'Fixing foreign key constraints in {tenants.count()} active tenants')
        
        for tenant in tenants:
            self.stdout.write(f'Fixing foreign keys for tenant: {tenant.name} ({tenant.database_name})')
            success = self.fix_tenant_foreign_keys(tenant.database_name)
            if success:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully fixed foreign keys for tenant: {tenant.name}')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Failed to fix foreign keys for tenant: {tenant.name}')
                )

    def fix_tenant_foreign_keys(self, database_name):
        """Fix foreign key constraints in a specific tenant database"""
        try:
            # Connect to the tenant database
            connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT'],
                database=database_name
            )
            
            cursor = connection.cursor()
            
            # Disable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            
            # Drop user_tenant table if it exists
            cursor.execute("DROP TABLE IF EXISTS user_tenant")
            self.stdout.write(f'Dropped user_tenant table from {database_name}')
            
            # Fix user tables
            self.fix_user_customuser_table(cursor)
            
            # Re-enable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            
            connection.commit()
            cursor.close()
            connection.close()
            
            return True
            
        except Exception as e:
            self.stdout.write(f'Error fixing foreign keys for {database_name}: {str(e)}')
            return False

    def database_exists(self, database_name):
        """Check if database exists"""
        try:
            connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT']
            )
            
            cursor = connection.cursor()
            cursor.execute("SHOW DATABASES LIKE %s", (database_name,))
            result = cursor.fetchone()
            
            cursor.close()
            connection.close()
            
            return result is not None
        except Exception as e:
            self.stdout.write(f'Error checking database existence: {str(e)}')
            return False