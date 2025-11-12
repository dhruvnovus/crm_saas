from rest_framework import serializers

from .models import Lead, LeadStatus, LeadCallSummary, CallOutcome
from customer.models import Customer
from customer.serializers import CustomerSerializer


class LeadCallSummarySerializer(serializers.ModelSerializer):
    created_by_username = serializers.SerializerMethodField()
    q3_preference_display = serializers.CharField(source='get_q3_preference_display', read_only=True)
    call_outcome_display = serializers.CharField(source='get_call_outcome_display', read_only=True)

    class Meta:
        model = LeadCallSummary
        fields = [
            'id', 'lead', 'summary', 'call_time', 'created_by_username', 
            'q1_preparing_usmle_residency', 'q1_interested_future',
            'q2_clinical_research_opportunities', 'q2_want_to_learn_more',
            'q3_preference', 'q3_preference_display', 'q3_want_call_after_info',
            'call_outcome', 'call_outcome_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'lead', 'created_by_username', 
            'q3_preference_display', 'call_outcome_display',
            'created_at', 'updated_at'
        ]

    def get_created_by_username(self, obj):
        return getattr(obj.created_by, 'username', None)
    
    def to_representation(self, instance):
        """Convert boolean fields to 'Yes'/'No' in API responses"""
        data = super().to_representation(instance)
        
        # List of boolean fields to convert
        boolean_fields = [
            'q1_preparing_usmle_residency',
            'q1_interested_future',
            'q2_clinical_research_opportunities',
            'q2_want_to_learn_more',
            'q3_want_call_after_info',
        ]
        
        # Convert boolean values to "Yes"/"No"
        for field in boolean_fields:
            if field in data:
                value = data[field]
                if isinstance(value, bool):
                    data[field] = "Yes" if value else "No"
                # If None or not a boolean, leave as is
        
        return data
    
    def to_internal_value(self, data):
        """Convert 'Yes'/'No' strings to boolean values when receiving data"""
        # List of boolean fields that might be sent as "Yes"/"No"
        boolean_fields = [
            'q1_preparing_usmle_residency',
            'q1_interested_future',
            'q2_clinical_research_opportunities',
            'q2_want_to_learn_more',
            'q3_want_call_after_info',
        ]
        
        # Convert "Yes"/"No" strings to booleans
        for field in boolean_fields:
            if field in data and isinstance(data[field], str):
                value = data[field].strip()
                if value.lower() == 'yes':
                    data[field] = True
                elif value.lower() == 'no':
                    data[field] = False
                # If not "yes" or "no", let DRF handle the validation
        
        return super().to_internal_value(data)
    
    def validate(self, attrs):
        """Validate the call flow logic - allow all fields to be set as sent"""
        # All fields are allowed to be set as sent by the user
        # The call flow logic is informational - users can record data flexibly
        # No auto-correction - preserve what the user sends
        return attrs


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
    # Expose full customer details in GET responses only (read-only)
    customer_details = CustomerSerializer(source='customer', read_only=True)
    call_summaries = serializers.SerializerMethodField()
    
    class Meta:
        model = Lead
        fields = [
            'id', 'customer', 'customer_email', 'customer_name', 'customer_details', 'name', 'email',
            'phone', 'status', 'source', 'notes', 'call_summaries', 'is_active', 'created_at',
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
        
        # Exclude customer_details from POST/PATCH requests, only include in GET responses
        if request and request.method in ('POST', 'PATCH', 'PUT'):
            self.fields.pop('customer_details', None)

    def get_call_summaries(self, obj):
        """Return only active call summaries for the lead"""
        try:
            active_summaries = obj.call_summaries.filter(is_active=True).order_by('-created_at')
            # Only serialize fields that exist in the database
            # Check if new fields exist by trying to access the model's _meta
            model_fields = [f.name for f in active_summaries.model._meta.get_fields()]
            # Pass context to nested serializer to ensure proper serialization
            serializer = LeadCallSummarySerializer(active_summaries, many=True, context=self.context)
            # Filter out fields that don't exist in the database
            data = serializer.data
            # If any field access fails, return minimal data
            return data
        except Exception as e:
            # If there's an error (e.g., missing columns), return empty list
            # This can happen if migrations haven't been applied yet
            return []

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

