from rest_framework import status, generics, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils.decorators import method_decorator
 

from .models import Lead
from customer.models import Customer
from .serializers import LeadSerializer, LeadStatusUpdateSerializer
from user.models import CustomUser


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        responses={
            200: openapi.Response(
                description='List leads',
                examples={
                    'application/json': {
                        'count': 1,
                        'next': None,
                        'previous': None,
                        'results': [
                            {
                                'id': 'uuid-here',
                                'name': 'Website Inquiry',
                                'status': 'new',
                                'customer': 'uuid-of-customer',
                                'is_active': True,
                            }
                        ],
                    }
                },
            )
        },
    ),
)
@method_decorator(
    name='post',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Create a lead (link customer by ID or email)',
        responses={
            201: openapi.Response(
                description='Lead created',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Website Inquiry',
                        'status': 'new',
                        'customer': 'uuid-of-customer',
                        'is_active': True,
                    }
                },
            ),
            400: openapi.Response(description='Validation error'),
            401: openapi.Response(description='Authentication required'),
        },
    ),
)
class LeadListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'email', 'phone', 'status', 'customer__name', 'customer__email']

    def get_queryset(self):
        # Scope to current tenant
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return Lead.objects.none()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        # Default ordering: newest first
        return Lead.objects.filter(tenant=self.request.user.tenant, is_active=True).order_by('-created_at')

    
    def create(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response({'detail': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        if not hasattr(request.user, 'tenant') or not request.user.tenant:
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

        # Validate customer if provided by ID
        if customer:
            # Ensure customer belongs to the same tenant
            if customer.tenant != request.user.tenant:
                return Response(
                    {'detail': 'Customer does not belong to the current tenant'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not customer.is_active:
                return Response(
                    {'detail': 'Customer is inactive'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if not customer and customer_email:
            # Ensure we operate in the tenant database
            try:
                customer = Customer.objects.get(tenant=request.user.tenant, email=customer_email, is_active=True)
            except Customer.DoesNotExist:
                customer = Customer.objects.create(
                    tenant=request.user.tenant,
                    created_by=tenant_user,
                    name=customer_name or validated.get('name') or customer_email.split('@')[0],
                    email=customer_email,
                    is_active=True,
                )
            except Customer.MultipleObjectsReturned:
                # Handle duplicate emails (shouldn't happen due to unique constraint, but handle gracefully)
                customer = Customer.objects.filter(tenant=request.user.tenant, email=customer_email, is_active=True).first()

        lead = Lead(
            tenant=request.user.tenant,
            created_by=tenant_user,  # may be None if user isn't present in tenant DB
            customer=customer,
            **validated,
        )
        lead.save()
        return Response(LeadSerializer(lead, context={'request': request}).data, status=status.HTTP_201_CREATED)


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        responses={
            200: openapi.Response(
                description='Retrieve lead',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Website Inquiry',
                        'status': 'new',
                        'customer': 'uuid-of-customer',
                        'is_active': True,
                    }
                },
            ),
            404: openapi.Response(description='Not found'),
        },
    ),
)
@method_decorator(
    name='patch',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        responses={
            200: openapi.Response(
                description='Lead updated',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Website Inquiry',
                        'status': 'contacted',
                        'customer': 'uuid-of-customer',
                        'is_active': True,
                    }
                },
            ),
            400: openapi.Response(description='Validation error'),
        },
    ),
)
@method_decorator(
    name='delete',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        responses={
            200: openapi.Response(
                description='Soft delete confirmation',
                examples={'application/json': {'message': 'Lead soft-deleted'}},
            ),
        },
    ),
)
class LeadDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer
    lookup_field = 'pk'
    http_method_names = ['get', 'patch', 'delete']  # Exclude PUT

    def get_queryset(self):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return Lead.objects.none()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        return Lead.objects.filter(tenant=self.request.user.tenant, is_active=True)

    def perform_update(self, serializer):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'No tenant associated with user'})
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        serializer.save()

    def delete(self, request, *args, **kwargs):
        if not hasattr(request.user, 'tenant') or not request.user.tenant:
            return Response({'detail': 'No tenant associated with user'}, status=status.HTTP_400_BAD_REQUEST)
        instance = self.get_object()
        from django.db import connections
        connections['default'].tenant = request.user.tenant
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
        return Response({'message': 'Lead soft-deleted'}, status=status.HTTP_200_OK)


@method_decorator(
    name='patch',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Update lead status',
        responses={
            200: openapi.Response(
                description='Lead status updated',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Website Inquiry',
                        'status': 'closed',
                        'customer': 'uuid-of-customer',
                        'is_active': True,
                    }
                },
            ),
            400: openapi.Response(description='Validation error'),
        },
    ),
)
class LeadStatusUpdateView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadStatusUpdateSerializer
    lookup_field = 'pk'
    http_method_names = ['patch']
    # Ensure tag grouping in Swagger under "Leads" (not auto path-based "leads")
    swagger_schema_fields = {"tags": ["Leads"]}

    def get_queryset(self):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return Lead.objects.none()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        return Lead.objects.filter(tenant=self.request.user.tenant, is_active=True)

    def patch(self, request, *args, **kwargs):
        if not hasattr(request.user, 'tenant') or not request.user.tenant:
            return Response({'detail': 'No tenant associated with user'}, status=status.HTTP_400_BAD_REQUEST)
        from django.db import connections
        connections['default'].tenant = request.user.tenant
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(LeadSerializer(instance, context={'request': request}).data, status=status.HTTP_200_OK)

