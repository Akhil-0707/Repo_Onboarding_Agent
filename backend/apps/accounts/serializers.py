from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    name = serializers.SerializerMethodField()
    github_connected = serializers.BooleanField(read_only=True)
    private_repo_access = serializers.BooleanField(source="has_private_repo_access", read_only=True)

    class Meta:
        model = User
        # The encrypted GitHub token is deliberately absent.
        fields = (
            "id",
            "username",
            "name",
            "email",
            "avatar_url",
            "github_connected",
            "private_repo_access",
            "date_joined",
        )
        read_only_fields = fields

    def get_name(self, user: User) -> str:
        return user.get_full_name() or user.username


class ExchangeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=128)


class AccessTokenSerializer(serializers.Serializer):
    access = serializers.CharField()
    user = UserSerializer()
