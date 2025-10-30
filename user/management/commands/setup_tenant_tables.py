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
                    'authtoken_token', 'customer_customer', 'leads_lead'
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
                'authtoken_token',
                'customer_customer',
                'leads_lead'
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
            
            # Always fix user/customer tables to remove tenant foreign key constraints
            self.fix_user_customuser_table(cursor)
            # Ensure customer new columns exist
            self.ensure_customer_columns(cursor)
            
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
                'authtoken_token', 'customer_customer', 'leads_lead'
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
        """Fix user_customuser, user_tenantuser and customer_customer tables to remove tenant foreign key constraints"""
        try:
            # Helper to drop all FKs on a column regardless of generated name
            def drop_foreign_keys(table_name, column_name):
                cursor.execute("""
                    SELECT CONSTRAINT_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = %s
                      AND COLUMN_NAME = %s
                      AND REFERENCED_TABLE_NAME IS NOT NULL
                """, (table_name, column_name))
                constraints = [row[0] for row in cursor.fetchall()]
                for constraint in constraints:
                    self.stdout.write(f"Dropping foreign key {constraint} on {table_name}.{column_name}")
                    cursor.execute(f"ALTER TABLE `{table_name}` DROP FOREIGN KEY `{constraint}`")

            # Fix user_customuser table
            cursor.execute("SHOW TABLES LIKE 'user_customuser'")
            if cursor.fetchone():
                drop_foreign_keys('user_customuser', 'tenant_id')
                # relax the column type to nullable in case it was NOT NULL with FK
                try:
                    cursor.execute("ALTER TABLE user_customuser MODIFY COLUMN tenant_id char(32) NULL")
                except Exception:
                    pass
                self.stdout.write('Checked and fixed FKs for user_customuser')

            # Fix user_tenantuser table
            cursor.execute("SHOW TABLES LIKE 'user_tenantuser'")
            if cursor.fetchone():
                drop_foreign_keys('user_tenantuser', 'tenant_id')
                try:
                    cursor.execute("ALTER TABLE user_tenantuser MODIFY COLUMN tenant_id char(32) NULL")
                except Exception:
                    pass
                self.stdout.write('Checked and fixed FKs for user_tenantuser')

            # Fix customer_customer table
            cursor.execute("SHOW TABLES LIKE 'customer_customer'")
            if cursor.fetchone():
                drop_foreign_keys('customer_customer', 'tenant_id')
                drop_foreign_keys('customer_customer', 'created_by_id')
                try:
                    cursor.execute("ALTER TABLE customer_customer MODIFY COLUMN tenant_id char(32) NULL")
                except Exception:
                    pass
                try:
                    cursor.execute("ALTER TABLE customer_customer MODIFY COLUMN created_by_id bigint NULL")
                except Exception:
                    pass
                self.stdout.write('Checked and fixed FKs for customer_customer')
                
        except Exception as e:
            self.stdout.write(f'Warning: Could not fix user tables: {str(e)}')

    def fix_leads_table(self, cursor):
        """Fix leads_lead table FK constraints if present in tenant DB"""
        try:
            def drop_foreign_keys(table_name, column_name):
                cursor.execute("""
                    SELECT CONSTRAINT_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = %s
                      AND COLUMN_NAME = %s
                      AND REFERENCED_TABLE_NAME IS NOT NULL
                """, (table_name, column_name))
                constraints = [row[0] for row in cursor.fetchall()]
                for constraint in constraints:
                    self.stdout.write(f"Dropping foreign key {constraint} on {table_name}.{column_name}")
                    cursor.execute(f"ALTER TABLE `{table_name}` DROP FOREIGN KEY `{constraint}`")

            cursor.execute("SHOW TABLES LIKE 'leads_lead'")
            if cursor.fetchone():
                for col in ['tenant_id', 'created_by_id', 'customer_id']:
                    drop_foreign_keys('leads_lead', col)
                try:
                    cursor.execute("ALTER TABLE leads_lead MODIFY COLUMN tenant_id char(32) NULL")
                except Exception:
                    pass
                try:
                    cursor.execute("ALTER TABLE leads_lead MODIFY COLUMN created_by_id bigint NULL")
                except Exception:
                    pass
                try:
                    cursor.execute("ALTER TABLE leads_lead MODIFY COLUMN customer_id char(32) NULL")
                except Exception:
                    pass
                self.stdout.write('Checked and fixed FKs for leads_lead')
        except Exception as e:
            self.stdout.write(f'Warning: Could not fix leads_lead table: {str(e)}')

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
            
            # Fix user, customer, and leads tables
            self.fix_user_customuser_table(cursor)
            self.ensure_customer_columns(cursor)
            self.fix_leads_table(cursor)
            
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

    def ensure_customer_columns(self, cursor):
        """Add missing columns for customer_customer introduced recently"""
        try:
            cursor.execute("SHOW TABLES LIKE 'customer_customer'")
            if not cursor.fetchone():
                return
            desired_columns = [
                ('address', "TEXT NULL"),
                ('city', "VARCHAR(120) NULL"),
                ('state', "VARCHAR(120) NULL"),
                ('country', "VARCHAR(120) NULL"),
                ('zip_code', "VARCHAR(20) NULL"),
                ('is_active', "TINYINT(1) NOT NULL DEFAULT 1"),
            ]
            for col_name, col_def in desired_columns:
                cursor.execute(
                    """
                    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'customer_customer'
                      AND COLUMN_NAME = %s
                    """,
                    (col_name,)
                )
                if not cursor.fetchone():
                    self.stdout.write(f"Adding column {col_name} to customer_customer")
                    cursor.execute(f"ALTER TABLE customer_customer ADD COLUMN {col_name} {col_def}")
        except Exception as e:
            self.stdout.write(f'Warning: Could not ensure customer columns: {str(e)}')