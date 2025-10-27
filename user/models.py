from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import connection
import uuid


class TimestampedModel(models.Model):
    """
    Abstract base model that provides created_at and updated_at timestamp fields
    for all models that inherit from it.
    """
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this record was created")
    updated_at = models.DateTimeField(auto_now=True, help_text="When this record was last updated")
    
    class Meta:
        abstract = True


class Tenant(TimestampedModel):
    """Model to store tenant information and database details"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    database_name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name
    
    def create_database(self):
        """Create a new database for this tenant"""
        from .database_service import DatabaseService
        return DatabaseService.create_tenant_database(self.name, self.database_name)


class CustomUser(AbstractUser):
    """Extended user model with tenant relationship"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    is_tenant_admin = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.username} ({self.tenant.name if self.tenant else 'No Tenant'})"


class TenantUser(TimestampedModel):
    """Model for users within a tenant's database"""
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['user', 'tenant']
    
    def __str__(self):
        return f"{self.user.username} - {self.tenant.name}"


class History(TimestampedModel):
    """Model to track all API events and user actions"""
    
    HTTP_METHOD_CHOICES = [
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('PATCH', 'PATCH'),
        ('DELETE', 'DELETE'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, 
                             help_text="User who performed the action")
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True, blank=True,
                               help_text="Tenant context for the action")
    method = models.CharField(max_length=10, choices=HTTP_METHOD_CHOICES,
                              help_text="HTTP method used")
    endpoint = models.CharField(max_length=500, help_text="API endpoint accessed")
    request_data = models.JSONField(null=True, blank=True, 
                                   help_text="Request payload data")
    response_status = models.IntegerField(null=True, blank=True,
                                         help_text="HTTP response status code")
    response_data = models.JSONField(null=True, blank=True,
                                    help_text="Response data")
    ip_address = models.GenericIPAddressField(null=True, blank=True,
                                              help_text="Client IP address")
    user_agent = models.TextField(null=True, blank=True,
                                  help_text="Client user agent")
    execution_time = models.FloatField(null=True, blank=True,
                                      help_text="Request execution time in seconds")
    error_message = models.TextField(null=True, blank=True,
                                    help_text="Error message if request failed")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['method', 'created_at']),
            models.Index(fields=['endpoint', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.method} {self.endpoint} - {self.user.username if self.user else 'Anonymous'} ({self.created_at})"
