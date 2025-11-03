from rest_framework import serializers

from .models import Lead, LeadStatus
from customer.models import Customer
from customer.serializers import CustomerSerializer


class LeadSerializer(serializers.ModelSerializer):
    # Accept either a customer id or customer_email to link/create during POST
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.none(),  # Will be set dynamically based on tenant
        required=True,
        allow_null=False,
        error_messages={
            'does_not_exist': 'Customer not found in the current tenant.',
            'incorrect_type': 'Customer must be a valid UUID string.'
        }
    )
    customer_email = serializers.EmailField(required=False, allow_null=True, write_only=True)
    customer_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    # Expose full customer details in read responses
    customer_details = CustomerSerializer(source='customer', read_only=True)
    
    class Meta:
        model = Lead
        fields = [
            'id', 'customer', 'customer_email', 'customer_name', 'customer_details', 'name', 'email',
            'phone', 'status', 'source', 'notes', 'is_active', 'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'email': {'required': True, 'allow_null': False, 'allow_blank': False},
            'phone': {'required': True, 'allow_null': False, 'allow_blank': False},
            'status': {'required': True},
            'source': {'required': True, 'allow_null': False, 'allow_blank': False},
            'is_active': {'required': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set tenant-scoped queryset for customer field if tenant is available in context
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            if hasattr(request.user, 'tenant') and request.user.tenant:
                from django.db import connections
                connections['default'].tenant = request.user.tenant
                # Update customer field queryset to be tenant-scoped
                self.fields['customer'].queryset = Customer.objects.filter(
                    tenant=request.user.tenant,
                    is_active=True
                )

    def validate(self, attrs):
        # If both customer and customer_email are missing, that's fine (lead can be unlinked)
        # If provided, keep as-is; linking/creation happens in the view where user/tenant is available
        return attrs



class LeadStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=LeadStatus.choices)

    def update(self, instance, validated_data):
        instance.status = validated_data['status']
        instance.save(update_fields=['status', 'updated_at'])
        return instance

    def create(self, validated_data):
        raise NotImplementedError('Creation is not supported for LeadStatusUpdateSerializer')

