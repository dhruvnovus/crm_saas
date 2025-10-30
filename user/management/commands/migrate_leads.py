from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connections
from django.core.management import call_command
import mysql.connector

from user.models import Tenant


class Command(BaseCommand):
    help = 'Run migrations for the leads app on one or all tenant databases'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-name',
            type=str,
            help='Tenant name to migrate only that tenant',
        )
        parser.add_argument(
            '--all-tenants',
            action='store_true',
            help='Migrate all active tenants',
        )
        parser.add_argument(
            '--makemigrations',
            action='store_true',
            help='Run makemigrations for the leads app before migrating tenants',
        )
        # Note: Django already provides a global --verbosity option

    def handle(self, *args, **options):
        tenant_name = options.get('tenant_name')
        all_tenants = options.get('all_tenants')
        run_makemigrations = options.get('makemigrations')
        verbosity = options.get('verbosity', 1)

        if not tenant_name and not all_tenants:
            raise CommandError('Specify --tenant-name or --all-tenants')

        # Optionally create migrations for leads app in the main project
        if run_makemigrations:
            self.stdout.write('Running makemigrations for leads...')
            call_command('makemigrations', 'leads', verbosity=verbosity)

        tenants_qs = Tenant.objects.filter(is_active=True)
        if tenant_name:
            tenants_qs = tenants_qs.filter(name=tenant_name)

        tenants = list(tenants_qs)
        if not tenants:
            raise CommandError('No matching active tenants found')

        for tenant in tenants:
            db_name = tenant.database_name
            self.stdout.write(f"Preparing connection for tenant: {tenant.name} ({db_name})")

            # Ensure the tenant database is present in Django connections (match router config)
            connections.databases.setdefault(db_name, {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': db_name,
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
            })

            try:
                # Apply prerequisite apps first with --fake-initial to register migrations
                # without recreating already-existing tables
                prerequisite_apps = [
                    'contenttypes', 'auth', 'sessions', 'authtoken', 'user', 'customer'
                ]
                for app_label in prerequisite_apps:
                    if app_label != 'customer':
                        self.stdout.write(f"Ensuring migrations for {app_label} on {db_name} (fake-initial)")
                        call_command('migrate', app_label, database=db_name, fake_initial=True, verbosity=verbosity)
                        continue

                    # Handle customer specially to avoid duplicate-column errors
                    self.stdout.write(f"Ensuring migrations for customer on {db_name} with safe strategy")
                    # Step 1: ensure 0001 is applied
                    call_command('migrate', 'customer', '0001', database=db_name, fake_initial=True, verbosity=verbosity)
                    # Step 2: if columns from 0002 already exist, fake that migration
                    try:
                        self._fake_customer_0002_if_needed(db_name)
                    except Exception as warn_exc:
                        self.stdout.write(f"Warning while ensuring customer 0002 on {db_name}: {warn_exc}")
                    # Step 3: finish customer to head
                    call_command('migrate', 'customer', database=db_name, fake_initial=True, verbosity=verbosity)

                # Now apply leads migrations (also allow fake-initial just in case)
                self.stdout.write(f"Migrating leads for tenant: {tenant.name} -> {db_name}")
                try:
                    call_command('migrate', 'leads', database=db_name, fake_initial=True, verbosity=verbosity)
                    self.stdout.write(self.style.SUCCESS(f"Successfully migrated leads for {tenant.name}"))
                except Exception as migrate_exc:
                    # FK errors are likely due to missing user_tenant table in tenant DB. Create a minimal stub and retry.
                    self.stdout.write(f"Leads migration failed on {db_name}: {migrate_exc}. Attempting FK-safe fallback...")
                    try:
                        self._ensure_user_tenant_stub(db_name)
                        call_command('migrate', 'leads', database=db_name, fake_initial=True, verbosity=verbosity)
                        self.stdout.write(self.style.SUCCESS(f"Leads migrated after creating user_tenant stub for {tenant.name}"))
                    except Exception:
                        # Final fallback: clone leads_lead and mark migration as applied
                        self.stdout.write("Falling back to cloning leads_lead and faking migration entry")
                        self._clone_table_from_default('leads_lead', db_name)
                        if not self._table_exists(db_name, 'leads_lead'):
                            raise CommandError("Unable to create leads_lead on tenant database")
                        call_command('migrate', 'leads', database=db_name, fake=True, verbosity=verbosity)
                        self.stdout.write(self.style.SUCCESS(f"Created leads_lead by cloning and faked migration for {tenant.name}"))

                # Verify leads_lead exists; if missing (edge), clone from default DB
                if not self._table_exists(db_name, 'leads_lead'):
                    self.stdout.write(f"leads_lead missing on {db_name}; cloning table structure from default DB")
                    self._clone_table_from_default('leads_lead', db_name)
                    if self._table_exists(db_name, 'leads_lead'):
                        self.stdout.write(self.style.SUCCESS(f"Created leads_lead on {db_name} by cloning"))
                    else:
                        raise CommandError("Unable to create leads_lead on tenant database")
            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f"Failed to migrate leads for {tenant.name}: {exc}"
                ))

    def _table_exists(self, db_alias: str, table_name: str) -> bool:
        conn = connections[db_alias]
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES LIKE %s", [table_name])
            return cursor.fetchone() is not None

    def _fake_customer_0002_if_needed(self, db_alias: str) -> None:
        """If customer 0002 columns are already present, mark that migration as applied for the tenant."""
        conn = connections[db_alias]
        # Check any one new column from 0002 (e.g., address)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'customer_customer'
                  AND COLUMN_NAME = 'address'
            """)
            address_exists = cursor.fetchone() is not None
        if address_exists:
            call_command(
                'migrate',
                'customer',
                '0002_customer_address_customer_city_customer_country_and_more',
                database=db_alias,
                fake=True,
                verbosity=1,
            )

    def _clone_table_from_default(self, table_name: str, tenant_db_name: str) -> None:
        """Clone CREATE TABLE of table_name from default DB into tenant_db_name using mysql connector."""
        default_cfg = settings.DATABASES['default']
        # Get CREATE TABLE from default DB
        main_conn = mysql.connector.connect(
            host=default_cfg['HOST'],
            user=default_cfg['USER'],
            password=default_cfg['PASSWORD'],
            port=default_cfg['PORT'],
            database=default_cfg['NAME']
        )
        try:
            main_cur = main_conn.cursor()
            main_cur.execute(f"SHOW CREATE TABLE `{table_name}`")
            row = main_cur.fetchone()
            if not row:
                raise CommandError(f"Table {table_name} not found in default DB")
            create_stmt = row[1]
        finally:
            main_cur.close()
            main_conn.close()

        # Execute CREATE TABLE in tenant DB
        tenant_conn = mysql.connector.connect(
            host=default_cfg['HOST'],
            user=default_cfg['USER'],
            password=default_cfg['PASSWORD'],
            port=default_cfg['PORT'],
            database=tenant_db_name
        )
        try:
            cur = tenant_conn.cursor()
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            cur.execute(create_stmt)
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
            tenant_conn.commit()
        finally:
            cur.close()
            tenant_conn.close()

    def _ensure_user_tenant_stub(self, db_alias: str) -> None:
        """Create a minimal user_tenant table in the tenant DB so FK to Tenant(id) can be formed."""
        conn = connections[db_alias]
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES LIKE 'user_tenant'")
            if cursor.fetchone():
                return
            # Minimal schema with id only (CHAR(32) matches Django UUIDField on MySQL)
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            cursor.execute(
                """
                CREATE TABLE `user_tenant` (
                    `id` char(32) NOT NULL,
                    PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            conn.commit()
