from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Idioma(models.TextChoices):
    ES = "es", "Español"
    EN = "en", "English"


class Centro(models.Model):
    """Cliente del SaaS: un centro de estética (tabla CENTRO_ESTETICO)."""

    class Plan(models.TextChoices):
        BASICO = "BASICO", _("Básico")
        PRO = "PRO", _("Pro")
        PREMIUM = "PREMIUM", _("Premium")

    class EstadoSuscripcion(models.TextChoices):
        ACTIVA = "ACTIVA", _("Activa")
        VENCIDA = "VENCIDA", _("Vencida")
        SUSPENDIDA = "SUSPENDIDA", _("Suspendida")

    nombre = models.CharField(max_length=150)
    nit = models.CharField(max_length=30, blank=True)
    ciudad = models.CharField(max_length=80, blank=True)
    telefono_whatsapp = models.CharField(max_length=20, blank=True)
    plan = models.CharField(max_length=10, choices=Plan.choices, default=Plan.BASICO)
    estado_suscripcion = models.CharField(
        max_length=12, choices=EstadoSuscripcion.choices, default=EstadoSuscripcion.ACTIVA
    )
    fecha_vencimiento = models.DateField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "centro_estetico"

    def __str__(self):
        return self.nombre

    @property
    def suscripcion_activa(self):
        return (
            self.estado_suscripcion == self.EstadoSuscripcion.ACTIVA
            and self.fecha_vencimiento >= timezone.localdate()
        )


class TenantModel(models.Model):
    """Base para toda tabla que pertenece a un centro (multitenant). Se usa desde el paso 4."""

    centro = models.ForeignKey(Centro, on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("El email es obligatorio")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("rol", Usuario.Rol.ADMIN_SAAS)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("nombre", "Admin SaaS")
        return self.create_user(email, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    class Rol(models.TextChoices):
        ADMIN_SAAS = "ADMIN_SAAS", _("Administrador SaaS")
        RECEPCIONISTA = "RECEPCIONISTA", _("Recepcionista")
        ESTETICISTA = "ESTETICISTA", _("Esteticista")

    email = models.EmailField(unique=True)
    nombre = models.CharField(max_length=120)
    rol = models.CharField(max_length=15, choices=Rol.choices)
    idioma = models.CharField(max_length=2, choices=Idioma.choices, default=Idioma.ES)
    centro = models.ForeignKey(Centro, null=True, blank=True, on_delete=models.CASCADE, related_name="usuarios")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = UsuarioManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]

    class Meta:
        db_table = "usuario"
        constraints = [
            # El admin del SaaS no pertenece a un centro; todos los demás roles sí.
            models.CheckConstraint(
                name="usuario_rol_centro",
                condition=(
                    models.Q(rol="ADMIN_SAAS", centro__isnull=True)
                    | (~models.Q(rol="ADMIN_SAAS") & models.Q(centro__isnull=False))
                ),
            )
        ]

    def __str__(self):
        return f"{self.nombre} ({self.rol})"