from rest_framework import serializers
from .models import CustomerHistory
from user.models import CustomUser


class CustomerHistorySerializer(serializers.ModelSerializer):
    """Serializer for CustomerHistory model"""
    changed_by_username = serializers.CharField(source='changed_by.username', read_only=True)
    changed_by_email = serializers.CharField(source='changed_by.email', read_only=True)
    
    class Meta:
        model = CustomerHistory
        fields = [
            'id', 'customer', 'tenant', 'changed_by', 'changed_by_username', 'changed_by_email',
            'action', 'field_name', 'old_value', 'new_value', 'changes', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

