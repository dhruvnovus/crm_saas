from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from user.models import Tenant
from user.database_service import DatabaseService


class Command(BaseCommand):
    help = 'Run migrations for all tenant databases'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--active-only',
            action='store_true',
            help='Only migrate active tenants',
        )
        parser.add_argument(
            '--create',
            action='store_true',
            help='Create tenant database if it does not exist',
        )
    
    def handle(self, *args, **options):
        active_only = options['active_only']
        create_db = options['create']
        verbosity = options.get('verbosity', 1)
        
        # Get all tenants
        if active_only:
            tenants = Tenant.objects.filter(is_active=True)
            self.stdout.write(f"Found {tenants.count()} active tenant(s)")
        else:
            tenants = Tenant.objects.all()
            self.stdout.write(f"Found {tenants.count()} tenant(s)")
        
        if tenants.count() == 0:
            self.stdout.write(self.style.WARNING("No tenants found to migrate"))
            return
        
        successful = 0
        failed = 0
        
        for tenant in tenants:
            self.stdout.write("")
            self.stdout.write(f"{'='*60}")
            self.stdout.write(f"Processing tenant: {tenant.name} (Database: {tenant.database_name})")
            self.stdout.write(f"{'='*60}")
            
            try:
                database_name = tenant.database_name
                
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
                    if verbosity >= 1:
                        self.stdout.write(f"✓ Successfully connected to tenant database: {database_name}")
                except Exception as e:
                    if create_db:
                        self.stdout.write(f"Database {database_name} does not exist. Creating...")
                        if DatabaseService.create_tenant_database(tenant.name, database_name):
                            self.stdout.write(self.style.SUCCESS(f"✓ Successfully created database: {database_name}"))
                            # Re-add connection after creation
                            connections.databases[database_name] = tenant_db_config
                        else:
                            self.stdout.write(self.style.ERROR(f"✗ Failed to create database: {database_name}"))
                            failed += 1
                            continue
                    else:
                        self.stdout.write(self.style.ERROR(f"✗ Cannot connect to database {database_name}: {e}"))
                        self.stdout.write(self.style.WARNING(f"   Hint: Use --create flag to create missing databases automatically"))
                        failed += 1
                        continue
                
                # Run migrations
                if verbosity >= 1:
                    self.stdout.write(f"Running migrations for tenant database: {database_name}")
                
                from django.core.management import call_command
                
                try:
                    # First, check and fake migrations if tables/columns already exist
                    # This must be done BEFORE fake_initial to avoid conflicts
                    try:
                        import mysql.connector
                        test_conn = mysql.connector.connect(
                            host=settings.DATABASES['default']['HOST'],
                            user=settings.DATABASES['default']['USER'],
                            password=settings.DATABASES['default']['PASSWORD'],
                            port=settings.DATABASES['default']['PORT'],
                            database=database_name
                        )
                        test_cursor = test_conn.cursor()
                        
                        # Check if customer.0002 columns exist
                        test_cursor.execute("""
                            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                            WHERE TABLE_SCHEMA = %s
                              AND TABLE_NAME = 'customer_customer'
                              AND COLUMN_NAME IN ('address', 'city', 'state', 'country', 'zip_code', 'is_active')
                        """, (database_name,))
                        column_count = test_cursor.fetchone()[0]
                        
                        # Check if customer.0002 migration is already applied
                        test_cursor.execute("""
                            SELECT COUNT(*) FROM django_migrations
                            WHERE app = 'customer' AND name = '0002_customer_address_customer_city_customer_country_and_more'
                        """)
                        customer_0002_exists = test_cursor.fetchone()[0] > 0
                        
                        # Check if customer_customerhistory table exists
                        test_cursor.execute("SHOW TABLES LIKE 'customer_customerhistory'")
                        customer_history_exists = test_cursor.fetchone() is not None
                        
                        # Check if customer.0003 migration is already applied
                        test_cursor.execute("""
                            SELECT COUNT(*) FROM django_migrations
                            WHERE app = 'customer' AND name = '0003_customerhistory'
                        """)
                        customer_0003_exists = test_cursor.fetchone()[0] > 0
                        
                        # Check if leads_leadhistory table exists
                        test_cursor.execute("SHOW TABLES LIKE 'leads_leadhistory'")
                        leads_history_exists = test_cursor.fetchone() is not None
                        
                        # Check if leads.0002 migration is already applied
                        test_cursor.execute("""
                            SELECT COUNT(*) FROM django_migrations
                            WHERE app = 'leads' AND name = '0002_leadhistory'
                        """)
                        leads_0002_exists = test_cursor.fetchone()[0] > 0

                        # Check if leads.0007 migration is applied (LeadCallSummary)
                        test_cursor.execute("""
                            SELECT COUNT(*) FROM django_migrations
                            WHERE app = 'leads' AND name = '0007_remove_lead_call_summaries_leadcallsummary'
                        """)
                        leads_0007_exists = test_cursor.fetchone()[0] > 0

                        # Check if leads_leadcallsummary table exists
                        test_cursor.execute("SHOW TABLES LIKE 'leads_leadcallsummary'")
                        lead_call_summary_exists = test_cursor.fetchone() is not None
                        
                        test_cursor.close()
                        test_conn.close()
                        
                        # Fake customer.0002 if columns exist but migration not marked
                        if column_count >= 6 and not customer_0002_exists:
                            call_command('migrate', 'customer', '0002_customer_address_customer_city_customer_country_and_more',
                                        database=database_name, fake=True, verbosity=verbosity)
                            if verbosity >= 1:
                                self.stdout.write(f'✓ Faked customer.0002 migration (columns already exist)')
                        
                        # Handle customer.0003 - create table if it doesn't exist, then fake migration
                        if not customer_0003_exists:
                            if not customer_history_exists:
                                # Create the table manually (without tenant FK constraint)
                                if verbosity >= 1:
                                    self.stdout.write('Creating customer_customerhistory table...')
                                # Disable FK checks temporarily
                                test_cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                                test_cursor.execute("""
                                    CREATE TABLE IF NOT EXISTS `customer_customerhistory` (
                                        `id` char(32) NOT NULL PRIMARY KEY,
                                        `created_at` datetime(6) NOT NULL,
                                        `updated_at` datetime(6) NOT NULL,
                                        `customer_id` char(32) NOT NULL,
                                        `tenant_id` char(32) NOT NULL,
                                        `changed_by_id` bigint NULL,
                                        `action` varchar(20) NOT NULL,
                                        `field_name` varchar(100) NULL,
                                        `old_value` longtext NULL,
                                        `new_value` longtext NULL,
                                        `changes` json NULL,
                                        `notes` longtext NULL,
                                        KEY `customer_cu_custome_cb020b_idx` (`customer_id`, `created_at`),
                                        KEY `customer_cu_tenant__33f174_idx` (`tenant_id`, `created_at`),
                                        KEY `customer_cu_action_7efb1a_idx` (`action`, `created_at`),
                                        CONSTRAINT `customerhistory_customer_fk` FOREIGN KEY (`customer_id`) REFERENCES `customer_customer` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
                                        CONSTRAINT `customerhistory_changed_by_fk` FOREIGN KEY (`changed_by_id`) REFERENCES `user_customuser` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
                                    ) ENGINE=InnoDB;
                                """)
                                test_cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                                test_conn.commit()
                            # Fake the migration since table now exists (or already existed)
                            call_command('migrate', 'customer', '0003_customerhistory',
                                        database=database_name, fake=True, verbosity=verbosity)
                            if verbosity >= 1:
                                self.stdout.write(f'✓ Faked customer.0003 migration')
                        
                        # Check if leads.0001 migration is already applied
                        test_cursor.execute("""
                            SELECT COUNT(*) FROM django_migrations
                            WHERE app = 'leads' AND name = '0001_initial'
                        """)
                        leads_0001_exists = test_cursor.fetchone()[0] > 0
                        
                        # Check if leads_lead table exists
                        test_cursor.execute("SHOW TABLES LIKE 'leads_lead'")
                        leads_table_exists = test_cursor.fetchone() is not None
                        
                        # Fake leads.0001 if table exists but migration not marked (must be done before 0002)
                        if leads_table_exists and not leads_0001_exists:
                            call_command('migrate', 'leads', '0001_initial',
                                        database=database_name, fake=True, verbosity=verbosity)
                            if verbosity >= 1:
                                self.stdout.write(f'✓ Faked leads.0001 migration (table already exists)')
                        
                        # Handle leads.0002 - create table if it doesn't exist, then fake migration
                        if not leads_0002_exists:
                            if not leads_history_exists:
                                # Ensure leads_lead table exists before creating history table
                                if not leads_table_exists:
                                    if verbosity >= 1:
                                        self.stdout.write('Warning: leads_lead table does not exist, cannot create history table')
                                else:
                                    # Create the table manually (without tenant FK constraint)
                                    if verbosity >= 1:
                                        self.stdout.write('Creating leads_leadhistory table...')
                                    # Disable FK checks temporarily
                                    test_cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                                    test_cursor.execute("""
                                        CREATE TABLE IF NOT EXISTS `leads_leadhistory` (
                                            `id` char(32) NOT NULL PRIMARY KEY,
                                            `created_at` datetime(6) NOT NULL,
                                            `updated_at` datetime(6) NOT NULL,
                                            `lead_id` char(32) NOT NULL,
                                            `tenant_id` char(32) NOT NULL,
                                            `changed_by_id` bigint NULL,
                                            `action` varchar(20) NOT NULL,
                                            `field_name` varchar(100) NULL,
                                            `old_value` longtext NULL,
                                            `new_value` longtext NULL,
                                            `changes` json NULL,
                                            `notes` longtext NULL,
                                            KEY `leads_leadh_lead_id_0512de_idx` (`lead_id`, `created_at`),
                                            KEY `leads_leadh_tenant__086cc8_idx` (`tenant_id`, `created_at`),
                                            KEY `leads_leadh_action_5746c6_idx` (`action`, `created_at`),
                                            CONSTRAINT `leadhistory_lead_fk` FOREIGN KEY (`lead_id`) REFERENCES `leads_lead` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
                                            CONSTRAINT `leadhistory_changed_by_fk` FOREIGN KEY (`changed_by_id`) REFERENCES `user_customuser` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
                                        ) ENGINE=InnoDB;
                                    """)
                                    test_cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                                    test_conn.commit()
                            # Fake the migration since table now exists (or already existed)
                            call_command('migrate', 'leads', '0002_leadhistory',
                                        database=database_name, fake=True, verbosity=verbosity)
                            if verbosity >= 1:
                                self.stdout.write(f'✓ Faked leads.0002 migration')

                        # Ensure leads.0007 (LeadCallSummary) - create table if missing, then fake migration
                        if not leads_0007_exists:
                            if not lead_call_summary_exists:
                                if verbosity >= 1:
                                    self.stdout.write('Creating leads_leadcallsummary table...')
                                # Disable FK checks temporarily
                                test_cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                                # Try to create with foreign keys; if that fails, fall back without FKs
                                try:
                                    test_cursor.execute("""
                                        CREATE TABLE IF NOT EXISTS `leads_leadcallsummary` (
                                            `id` char(32) NOT NULL PRIMARY KEY,
                                            `created_at` datetime(6) NOT NULL,
                                            `updated_at` datetime(6) NOT NULL,
                                            `tenant_id` char(32) NOT NULL,
                                            `lead_id` char(32) NOT NULL,
                                            `summary` longtext NOT NULL,
                                            `call_time` datetime(6) NULL,
                                            `created_by_id` bigint NULL,
                                            `is_active` bool NOT NULL DEFAULT 1,
                                            KEY `leads_leadc_tenant_lead_created_idx` (`tenant_id`, `lead_id`, `created_at`),
                                            KEY `leads_leadc_tenant_created_idx` (`tenant_id`, `created_at`),
                                            CONSTRAINT `leadcallsummary_lead_fk` FOREIGN KEY (`lead_id`) REFERENCES `leads_lead` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
                                            CONSTRAINT `leadcallsummary_created_by_fk` FOREIGN KEY (`created_by_id`) REFERENCES `user_customuser` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
                                        ) ENGINE=InnoDB;
                                    """)
                                except Exception:
                                    # Fallback: create without foreign keys to avoid FK issues on older tenants
                                    test_cursor.execute("""
                                        CREATE TABLE IF NOT EXISTS `leads_leadcallsummary` (
                                            `id` char(32) NOT NULL PRIMARY KEY,
                                            `created_at` datetime(6) NOT NULL,
                                            `updated_at` datetime(6) NOT NULL,
                                            `tenant_id` char(32) NOT NULL,
                                            `lead_id` char(32) NOT NULL,
                                            `summary` longtext NOT NULL,
                                            `call_time` datetime(6) NULL,
                                            `created_by_id` bigint NULL,
                                            `is_active` bool NOT NULL DEFAULT 1,
                                            KEY `leads_leadc_tenant_lead_created_idx` (`tenant_id`, `lead_id`, `created_at`),
                                            KEY `leads_leadc_tenant_created_idx` (`tenant_id`, `created_at`)
                                        ) ENGINE=InnoDB;
                                    """)
                                test_cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                                test_conn.commit()
                            # Fake the migration since table now exists (or already existed)
                            call_command('migrate', 'leads', '0007_remove_lead_call_summaries_leadcallsummary',
                                        database=database_name, fake=True, verbosity=verbosity)
                            if verbosity >= 1:
                                self.stdout.write(f'✓ Faked leads.0007 migration')
                    except Exception as e:
                        if verbosity >= 2:
                            self.stdout.write(f'Warning: Could not check/fake migrations: {e}')
                    
                    # Use fake_initial=True to handle tables created by setup_tenant_tables
                    # This will mark existing migrations as applied without recreating tables
                    call_command('migrate', database=database_name, fake_initial=True, verbosity=verbosity)
                    
                    # Then apply any new migrations that don't exist yet
                    call_command('migrate', database=database_name, verbosity=verbosity)
                    self.stdout.write(self.style.SUCCESS(f"✓ Successfully migrated tenant database: {database_name}"))
                    successful += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"✗ Error running migrations for {database_name}: {e}"))
                    failed += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ Error processing tenant {tenant.name}: {e}"))
                failed += 1
        
        # Summary
        self.stdout.write("")
        self.stdout.write(f"{'='*60}")
        self.stdout.write(self.style.SUCCESS(f"Migration Summary: {successful} successful, {failed} failed"))
        self.stdout.write(f"{'='*60}")

