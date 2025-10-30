from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from django.utils.decorators import method_decorator

from .models import Lead
from customer.models import Customer
from .serializers import LeadSerializer
from user.models import CustomUser


@method_decorator(name='get', decorator=swagger_auto_schema(tags=['Leads']))
@method_decorator(name='post', decorator=swagger_auto_schema(tags=['Leads']))
class LeadListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer

    def get_queryset(self):
        # Scope to current tenant
        if hasattr(self.request.user, 'tenant') and self.request.user.tenant:
            from django.db import connections
            connections['default'].tenant = self.request.user.tenant
            return Lead.objects.filter(tenant=self.request.user.tenant, is_active=True)
        return Lead.objects.none()

    @swagger_auto_schema(operation_description="Create a lead in the current tenant", tags=['Leads'])
    def create(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response({'detail': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        if not request.user.tenant:
            return Response({'detail': 'No tenant associated'}, status=status.HTTP_400_BAD_REQUEST)
        from django.db import connections
        connections['default'].tenant = request.user.tenant

        # Resolve a user that actually exists inside the current tenant DB.
        # If the authenticated user hasn't been copied into the tenant DB yet,
        # fall back to None to avoid FK errors.
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)

        # Link or create customer if customer id not explicitly provided
        customer = validated.pop('customer', None)
        customer_email = validated.pop('customer_email', None)
        customer_name = validated.pop('customer_name', None)

        if not customer and customer_email:
            # Ensure we operate in the tenant database
            try:
                customer = Customer.objects.get(tenant=request.user.tenant, email=customer_email)
            except Customer.DoesNotExist:
                customer = Customer.objects.create(
                    tenant=request.user.tenant,
                    created_by=tenant_user,
                    name=customer_name or validated.get('name') or customer_email.split('@')[0],
                    email=customer_email,
                    is_active=True,
                )

        lead = Lead(
            tenant=request.user.tenant,
            created_by=tenant_user,  # may be None if user isn't present in tenant DB
            customer=customer,
            **validated,
        )
        lead.save()
        return Response(LeadSerializer(lead).data, status=status.HTTP_201_CREATED)


@method_decorator(name='get', decorator=swagger_auto_schema(tags=['Leads']))
@method_decorator(name='put', decorator=swagger_auto_schema(tags=['Leads']))
@method_decorator(name='patch', decorator=swagger_auto_schema(tags=['Leads']))
@method_decorator(name='delete', decorator=swagger_auto_schema(tags=['Leads']))
class LeadDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        if hasattr(self.request.user, 'tenant') and self.request.user.tenant:
            from django.db import connections
            connections['default'].tenant = self.request.user.tenant
            return Lead.objects.filter(tenant=self.request.user.tenant, is_active=True)
        return Lead.objects.none()

    def perform_update(self, serializer):
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        serializer.save()

    @swagger_auto_schema(operation_description="Soft delete a lead", tags=['Leads'])
    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
        return Response({'message': 'Lead soft-deleted'}, status=status.HTTP_200_OK)


