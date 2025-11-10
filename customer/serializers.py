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


class CustomerLeadStatusSerializer(serializers.Serializer):
    """Custom serializer for customers with lead status in HubSpot-like format"""
    id = serializers.SerializerMethodField()
    properties = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()

    def get_id(self, obj):
        """Return customer ID as string"""
        return str(obj.id)

    def get_properties(self, obj):
        """Return properties object with phone, firstname, lastname, email, and hs_lead_status"""
        # Split name into firstname and lastname
        name_parts = (obj.name or '').strip().split(maxsplit=1)
        firstname = name_parts[0] if name_parts else ''
        lastname = name_parts[1] if len(name_parts) > 1 else ''

        # Get lead status from annotation (set in view queryset)
        hs_lead_status = None
        if hasattr(obj, 'lead_status_annotation'):
            hs_lead_status = obj.lead_status_annotation

        # Use customer phone if available, otherwise use lead phone (from annotation)
        customer_phone = obj.phone or ''
        lead_phone = getattr(obj, 'lead_phone', None) or ''
        phone = customer_phone if customer_phone else lead_phone
        
        # Remove '-' characters from phone number if present
        phone = phone.replace('-', '')

        properties = {
            'phone': phone,
        }

        # Add optional fields only if they have values
        if firstname:
            properties['firstname'] = firstname
        if lastname:
            properties['lastname'] = lastname
        if obj.email:
            properties['email'] = obj.email
        if hs_lead_status:
            properties['hs_lead_status'] = hs_lead_status

        return properties

    def get_company(self, obj):
        """Return company object if company name exists"""
        if obj.company:
            return {
                'name': obj.company
            }
        return None
