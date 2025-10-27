import mysql.connector
from django.conf import settings
from django.core.management import call_command
from django.db import connections
import os
import subprocess


class DatabaseService:
    """Service for managing tenant databases"""
    
    @staticmethod
    def create_tenant_database(tenant_name, database_name):
        """Create a new database for a tenant"""
        try:
            # Connect to MySQL server
            connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT']
            )
            
            cursor = connection.cursor()
            
            # Create database
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database_name}`")
            
            # Set up database with Django tables
            DatabaseService._setup_tenant_database(database_name)
            
            cursor.close()
            connection.close()
            
            return True
            
        except Exception as e:
            print(f"Error creating database: {e}")
            return False
    
    @staticmethod
    def _setup_tenant_database(database_name):
        """Set up Django tables in the tenant database"""
        from django.core.management import call_command
        
        try:
            # Use the setup_tenant_tables management command
            call_command('setup_tenant_tables', '--database-name', database_name, verbosity=1)
            return True
        except Exception as e:
            print(f"Error setting up tenant database {database_name}: {e}")
            return False
    
    @staticmethod
    def delete_tenant_database(database_name):
        """Delete a tenant database"""
        try:
            connection = mysql.connector.connect(
                host=settings.DATABASES['default']['HOST'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                port=settings.DATABASES['default']['PORT']
            )
            
            cursor = connection.cursor()
            cursor.execute(f"DROP DATABASE IF EXISTS `{database_name}`")
            
            cursor.close()
            connection.close()
            
            return True
            
        except Exception as e:
            print(f"Error deleting database: {e}")
            return False
    
    @staticmethod
    def get_tenant_connection(tenant):
        """Get database connection for a specific tenant"""
        tenant_db_config = {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': tenant.database_name,
            'USER': settings.DATABASES['default']['USER'],
            'PASSWORD': settings.DATABASES['default']['PASSWORD'],
            'HOST': settings.DATABASES['default']['HOST'],
            'PORT': settings.DATABASES['default']['PORT'],
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
        
        # Add tenant database to connections
        connections.databases[tenant.database_name] = tenant_db_config
        return connections[tenant.database_name]