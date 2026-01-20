from rest_framework import serializers

from .models import Branch


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = [
            "id",
            "name",
            "code",
            "address",
            "city",
            "state",
            "country",
            "zip_code",
            "phone",
            "email",
            "manager_name",
            "manager_email",
            "manager_phone",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


