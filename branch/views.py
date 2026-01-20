from django.utils.decorators import method_decorator
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import filters, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from user.models import CustomUser

from .history_serializers import BranchHistorySerializer
from .models import Branch, BranchHistory
from .serializers import BranchSerializer


@method_decorator(
    name="get",
    decorator=swagger_auto_schema(
        tags=["Branches"],
        responses={
            200: openapi.Response(
                description="List branches",
                examples={
                    "application/json": {
                        "count": 1,
                        "next": None,
                        "previous": None,
                        "results": [
                            {
                                "id": "uuid-here",
                                "name": "Main Branch",
                                "code": "BR001",
                                "city": "New York",
                                "country": "USA",
                                "is_active": True,
                            }
                        ],
                    }
                },
            )
        },
    ),
)
@method_decorator(
    name="post",
    decorator=swagger_auto_schema(
        tags=["Branches"],
        operation_description="Create a branch in the current tenant",
        responses={
            201: openapi.Response(description="Branch created"),
            400: openapi.Response(description="Validation error"),
            401: openapi.Response(description="Authentication required"),
        },
    ),
)
class BranchListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BranchSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "code", "city", "state", "country", "manager_name", "manager_email"]

    def get_queryset(self):
        if not getattr(self.request.user, "tenant", None):
            return Branch.objects.none()
        from django.db import connections

        connections["default"].tenant = self.request.user.tenant
        return Branch.objects.filter(tenant=self.request.user.tenant).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        if not getattr(request.user, "tenant", None):
            return Response({"detail": "No tenant associated"}, status=status.HTTP_400_BAD_REQUEST)

        from django.db import connections

        connections["default"].tenant = request.user.tenant

        # Ensure user exists in tenant DB (avoid FK issues in tenant DB context)
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        if not tenant_user:
            tenant_user = CustomUser.objects.create(
                id=request.user.id,
                username=request.user.username,
                email=request.user.email,
                first_name=request.user.first_name,
                last_name=request.user.last_name,
                is_active=request.user.is_active,
                is_staff=request.user.is_staff,
                is_superuser=request.user.is_superuser,
                password=request.user.password,
                tenant=None,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        branch = Branch(
            tenant=request.user.tenant,
            created_by=tenant_user,
            **serializer.validated_data,
        )
        branch._changed_by = tenant_user
        branch.save()
        return Response(BranchSerializer(branch).data, status=status.HTTP_201_CREATED)


@method_decorator(
    name="get",
    decorator=swagger_auto_schema(tags=["Branches"], operation_description="Retrieve branch"),
)
@method_decorator(
    name="patch",
    decorator=swagger_auto_schema(tags=["Branches"], operation_description="Update branch"),
)
@method_decorator(
    name="delete",
    decorator=swagger_auto_schema(tags=["Branches"], operation_description="Soft delete branch"),
)
class BranchDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BranchSerializer
    lookup_field = "pk"
    http_method_names = ["get", "patch", "delete"]

    def get_queryset(self):
        if not getattr(self.request.user, "tenant", None):
            return Branch.objects.none()
        from django.db import connections

        connections["default"].tenant = self.request.user.tenant
        return Branch.objects.filter(tenant=self.request.user.tenant)

    def perform_update(self, serializer):
        from django.db import connections

        connections["default"].tenant = self.request.user.tenant
        tenant_user = CustomUser.objects.filter(id=self.request.user.id).first()
        instance = serializer.instance
        instance._changed_by = tenant_user if tenant_user else self.request.user
        serializer.save()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        from django.db import connections

        connections["default"].tenant = request.user.tenant
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        instance.is_active = False
        instance._changed_by = tenant_user if tenant_user else request.user
        instance.save(update_fields=["is_active", "updated_at"])
        return Response({"message": "Branch soft-deleted"}, status=status.HTTP_200_OK)


@method_decorator(
    name="get",
    decorator=swagger_auto_schema(tags=["Branches"], operation_description="Get branch change history"),
)
class BranchHistoryView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BranchHistorySerializer
    lookup_field = "pk"

    def get_queryset(self):
        if not getattr(self.request.user, "tenant", None):
            return BranchHistory.objects.none()
        from django.db import connections

        connections["default"].tenant = self.request.user.tenant
        branch_id = self.kwargs.get("pk")
        try:
            branch = Branch.objects.get(id=branch_id, tenant=self.request.user.tenant)
        except Branch.DoesNotExist:
            return BranchHistory.objects.none()
        return (
            BranchHistory.objects.filter(branch=branch, tenant=self.request.user.tenant)
            .select_related("changed_by")
            .order_by("-created_at")
        )


