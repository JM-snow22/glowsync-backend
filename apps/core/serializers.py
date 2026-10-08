from django.contrib.auth import password_validation
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Centro, Idioma, Usuario


class TenantPKField(serializers.PrimaryKeyRelatedField):
    """Solo acepta objetos del mismo centro que el usuario (evita referenciar datos ajenos).
    Se usa desde el paso 4."""

    def get_queryset(self):
        qs = super().get_queryset()
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user.centro_id:
            return qs.filter(centro_id=request.user.centro_id)
        return qs.none()


class LoginSerializer(TokenObtainPairSerializer):
    """Login con email y clave. Mete el rol y el centro dentro del token."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["rol"] = user.rol
        token["centro_id"] = user.centro_id
        token["nombre"] = user.nombre
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        u = self.user
        if u.centro_id and not u.centro.suscripcion_activa:
            raise serializers.ValidationError(_("La suscripción del centro está vencida o suspendida."))
        data["usuario"] = {"id": u.id, "nombre": u.nombre, "email": u.email, "rol": u.rol,
                           "idioma": u.idioma, "centro_id": u.centro_id}
        return data


class CentroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Centro
        fields = "__all__"


class UsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = Usuario
        fields = ["id", "email", "nombre", "rol", "idioma", "is_active", "password"]

    def validate_rol(self, value):
        if value == Usuario.Rol.ADMIN_SAAS:
            raise serializers.ValidationError(_("Rol no permitido."))
        return value

    def validate_password(self, value):
        password_validation.validate_password(value)  # rechaza claves comunes como 12345678
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return Usuario.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class MeSerializer(serializers.Serializer):
    """Solo describe la respuesta de /auth/me/ en la documentación."""

    id = serializers.IntegerField()
    nombre = serializers.CharField()
    email = serializers.EmailField()
    rol = serializers.CharField()
    idioma = serializers.CharField()
    centro_id = serializers.IntegerField(allow_null=True)
    centro = serializers.CharField(allow_null=True)


class IdiomaSerializer(serializers.Serializer):
    idioma = serializers.ChoiceField(choices=Idioma.choices)