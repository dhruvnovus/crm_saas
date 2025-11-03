from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'email', 'phone', 'company',
            'address', 'city', 'state', 'country', 'zip_code', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'email': {'required': True, 'allow_null': False, 'allow_blank': False},
            'phone': {'required': True, 'allow_null': False, 'allow_blank': False},
            # Align with model: company is optional and can be null/blank
            'company': {'required': False, 'allow_null': True, 'allow_blank': True},
            'is_active': {'required': True},
        }
