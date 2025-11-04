# Generated manually to ensure leads_leadhistory table exists in tenant databases

from django.db import migrations


def create_leadhistory_table_if_not_exists(apps, schema_editor):
    """Create leads_leadhistory table if it doesn't exist"""
    from django.db import connection
    from django.conf import settings
    
    # Get the database name
    db_alias = schema_editor.connection.alias
    database_name = connection.settings_dict['NAME']
    
    # Check if this is a tenant database (not the main database)
    is_tenant_db = database_name.startswith('crm_tenant_') or database_name != settings.DATABASES['default']['NAME']
    
    # Check if table exists
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'leads_leadhistory'
        """, [database_name])
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            # Disable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            
            # Create the table (without tenant FK constraint for tenant databases)
            if is_tenant_db:
                # Tenant database: no FK on tenant_id
                cursor.execute("""
                    CREATE TABLE `leads_leadhistory` (
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
            else:
                # Main database: include tenant FK
                cursor.execute("""
                    CREATE TABLE `leads_leadhistory` (
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
                        CONSTRAINT `leadhistory_tenant_fk` FOREIGN KEY (`tenant_id`) REFERENCES `user_tenant` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
                        CONSTRAINT `leadhistory_changed_by_fk` FOREIGN KEY (`changed_by_id`) REFERENCES `user_customuser` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
                    ) ENGINE=InnoDB;
                """)
            
            # Re-enable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")


def reverse_migration(apps, schema_editor):
    """Reverse migration - optionally drop the table"""
    # Don't drop the table in reverse to preserve data
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0002_leadhistory'),
        ('customer', '0002_customer_address_customer_city_customer_country_and_more'),
        ('user', '0002_history'),
    ]

    operations = [
        migrations.RunPython(
            create_leadhistory_table_if_not_exists,
            reverse_migration,
            atomic=False
        ),
    ]

