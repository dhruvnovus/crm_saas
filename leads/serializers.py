from rest_framework import serializers

from .models import Lead
from customer.models import Customer


class LeadSerializer(serializers.ModelSerializer):
    # Accept either a customer id or customer_email to link/create during POST
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True,
        error_messages={
            'does_not_exist': 'Customer not found in the current tenant.',
            'incorrect_type': 'Customer must be a valid UUID string.'
        }
    )
    customer_email = serializers.EmailField(required=False, allow_null=True, write_only=True)
    customer_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    class Meta:
        model = Lead
        fields = [
            'id', 'customer', 'customer_email', 'customer_name', 'name', 'email',
            'phone', 'status', 'source', 'notes', 'is_active', 'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        # If both customer and customer_email are missing, that's fine (lead can be unlinked)
        # If provided, keep as-is; linking/creation happens in the view where user/tenant is available
        return attrs


