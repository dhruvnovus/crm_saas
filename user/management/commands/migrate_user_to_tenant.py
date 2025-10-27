from django.core.management.base import BaseCommand
from django.db import connection, connections
from django.conf import settings
from user.models import CustomUser, Tenant, TenantUser
import mysql.connector
import uuid
from django.utils import timezone


class Command(BaseCommand):
    help = 'Migrate a specific user from main database to tenant database'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to migrate')
        parser.add_argument('tenant_name', type=str, help='Target tenant name')

    def handle(self, *args, **options):
        username = options['username']
        tenant_name = options['tenant_name']
        
        try:
            # Get the user from main database
            user = CustomUser.objects.get(username=username)
            self.stdout.write(f"Found user: {user.username} ({user.email})")
            
            # Get the target tenant
            tenant = Tenant.objects.get(name=tenant_name)
            self.stdout.write(f"Found tenant: {tenant.name} (DB: {tenant.database_name})")
            
            # Connect directly to MySQL for tenant database
            tenant_connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT'],
                database=tenant.database_name
            )
            
            cursor = tenant_connection.cursor()
            
            # Check if user already exists in tenant database
            cursor.execute("SELECT id FROM user_customuser WHERE username = %s", [username])
            existing_user = cursor.fetchone()
            
            if existing_user:
                self.stdout.write(
                    self.style.WARNING(f"User {username} already exists in tenant database {tenant.database_name}")
                )
                cursor.close()
                tenant_connection.close()
                return
            
            # Insert user into tenant database
            insert_user = """
            INSERT INTO user_customuser 
            (id, password, last_login, is_superuser, username, first_name, last_name, 
             email, is_staff, is_active, date_joined, tenant_id, is_tenant_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            (user_id, tenant_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            """
            
            now = timezone.now()
            
            cursor.execute(insert_tenant_user, (
                user.id,
                str(tenant.id),
                now,
                now
            ))
            
            tenant_connection.commit()
            cursor.close()
            tenant_connection.close()
            
            self.stdout.write(
                self.style.SUCCESS(f"Successfully migrated user {username} to tenant {tenant_name}")
            )
            
            # Update user in main database to point to tenant
            user.tenant = tenant
            user.save()
            
            self.stdout.write(
                self.style.SUCCESS(f"Updated user {username} in main database to reference tenant {tenant_name}")
            )
            
        except CustomUser.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"User {username} not found in main database")
            )
        except Tenant.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"Tenant {tenant_name} not found")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error migrating user: {str(e)}")
            )
            import traceback
            self.stdout.write(traceback.format_exc())
