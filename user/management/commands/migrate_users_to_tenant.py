from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from user.models import Tenant, CustomUser, TenantUser
import mysql.connector


class Command(BaseCommand):
    help = 'Migrate existing users to tenant-specific database'
    
    def add_arguments(self, parser):
        parser.add_argument('tenant_name', type=str, help='Name of the tenant')
    
    def handle(self, *args, **options):
        tenant_name = options['tenant_name']
        
        try:
            # Get tenant from main database
            tenant = Tenant.objects.get(name=tenant_name)
            database_name = tenant.database_name
            
            self.stdout.write(f"Found tenant: {tenant.name} with database: {database_name}")
            
            # Get all users for this tenant from main database
            tenant_users = CustomUser.objects.filter(tenant=tenant)
            self.stdout.write(f"Found {tenant_users.count()} users for tenant {tenant.name}")
            
            if tenant_users.count() == 0:
                self.stdout.write("No users found for this tenant")
                return
            
            # Connect to tenant database
            connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT'],
                database=database_name
            )
            
            cursor = connection.cursor()
            
            # Migrate each user
            for user in tenant_users:
                try:
                    # Insert user into tenant database
                    insert_user = """
                    INSERT INTO user_customuser 
                    (id, password, last_login, is_superuser, username, first_name, last_name, 
                     email, is_staff, is_active, date_joined, tenant_id, is_tenant_admin)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    password = VALUES(password),
                    last_login = VALUES(last_login),
                    is_superuser = VALUES(is_superuser),
                    first_name = VALUES(first_name),
                    last_name = VALUES(last_name),
                    email = VALUES(email),
                    is_staff = VALUES(is_staff),
                    is_active = VALUES(is_active),
                    date_joined = VALUES(date_joined),
                    tenant_id = VALUES(tenant_id),
                    is_tenant_admin = VALUES(is_tenant_admin)
                    """
                    
                    cursor.execute(insert_user, (
                        user.id,
                        user.password,
                        user.last_login,
                        user.is_superuser,
                        user.username,
                        user.first_name,
                        user.last_name,
                        user.email,
                        user.is_staff,
                        user.is_active,
                        user.date_joined,
                        str(tenant.id),
                        user.is_tenant_admin
                    ))
                    
                    # Insert tenant user relationship
                    insert_tenant_user = """
                    INSERT INTO user_tenantuser 
                    (created_at, updated_at, user_id, tenant_id)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    created_at = VALUES(created_at),
                    updated_at = VALUES(updated_at)
                    """
                    
                    tenant_user_rel = TenantUser.objects.filter(user=user, tenant=tenant).first()
                    if tenant_user_rel:
                        cursor.execute(insert_tenant_user, (
                            tenant_user_rel.created_at,
                            tenant_user_rel.updated_at,
                            user.id,
                            str(tenant.id)
                        ))
                    
                    self.stdout.write(f"Migrated user: {user.username}")
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error migrating user {user.username}: {e}"))
            
            connection.commit()
            cursor.close()
            connection.close()
            
            self.stdout.write(self.style.SUCCESS(f"Successfully migrated {tenant_users.count()} users to tenant database: {database_name}"))
            
        except Tenant.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Tenant '{tenant_name}' not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
