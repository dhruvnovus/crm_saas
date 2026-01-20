from rest_framework import serializers

from .models import BranchHistory


class BranchHistorySerializer(serializers.ModelSerializer):
    changed_by_username = serializers.SerializerMethodField()
    changed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = BranchHistory
        fields = [
            "id",
            "action",
            "field_name",
            "old_value",
            "new_value",
            "changes",
            "notes",
            "changed_by_username",
            "changed_by_email",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_changed_by_username(self, obj):
        return obj.changed_by.username if obj.changed_by else None

    def get_changed_by_email(self, obj):
        return obj.changed_by.email if obj.changed_by else None


