from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from django.utils.decorators import method_decorator
from .models import Customer
from .serializers import CustomerSerializer


@method_decorator(name='get', decorator=swagger_auto_schema(tags=['Customers']))
@method_decorator(name='post', decorator=swagger_auto_schema(tags=['Customers']))
class CustomerListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerSerializer

    def get_queryset(self):
        # Scope to current tenant
        if hasattr(self.request.user, 'tenant') and self.request.user.tenant:
            from django.db import connections
            connections['default'].tenant = self.request.user.tenant
            return Customer.objects.filter(tenant=self.request.user.tenant)
        return Customer.objects.none()

    @swagger_auto_schema(operation_description="Create a customer in the current tenant", tags=['Customers'])
    def create(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response({'detail': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        if not request.user.tenant:
            return Response({'detail': 'No tenant associated'}, status=status.HTTP_400_BAD_REQUEST)
        from django.db import connections
        connections['default'].tenant = request.user.tenant
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = Customer(
            tenant=request.user.tenant,
            created_by=request.user,
            **serializer.validated_data,
        )
        customer.save()
        return Response(CustomerSerializer(customer).data, status=status.HTTP_201_CREATED)


@method_decorator(name='get', decorator=swagger_auto_schema(tags=['Customers']))
@method_decorator(name='put', decorator=swagger_auto_schema(tags=['Customers']))
@method_decorator(name='patch', decorator=swagger_auto_schema(tags=['Customers']))
@method_decorator(name='delete', decorator=swagger_auto_schema(tags=['Customers']))
class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerSerializer
    lookup_field = 'pk'

    def get_queryset(self):
        if hasattr(self.request.user, 'tenant') and self.request.user.tenant:
            from django.db import connections
            connections['default'].tenant = self.request.user.tenant
            return Customer.objects.filter(tenant=self.request.user.tenant)
        return Customer.objects.none()

    def perform_update(self, serializer):
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        serializer.save()

    @swagger_auto_schema(operation_description="Soft delete a customer", tags=['Customers'])
    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
        return Response({'message': 'Customer soft-deleted'}, status=status.HTTP_200_OK)
