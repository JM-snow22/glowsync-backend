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


class Recurso(models.Model):
    """Recurso protegido (tabla RECURSO). Es un permiso concreto con formato «modulo.accion»:
    citas.ver, citas.editar, usuarios.ver… «editar» incluye «ver»."""

    nombre = models.CharField(max_length=45, unique=True)

    class Meta:
        db_table = "recurso"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Rol(models.Model):
    """Rol (tabla ROL). Se relaciona N:M con recursos (ROL_HAS_RECURSO) y con usuarios (USUARIO_HAS_ROL).
    Los cuatro roles de `Usuario.Rol` son roles de sistema: no se renombran ni se eliminan."""

    nombre = models.CharField(max_length=45, unique=True)
    recursos = models.ManyToManyField(Recurso, db_table="rol_has_recurso", related_name="roles", blank=True)

    class Meta:
        db_table = "rol"
        ordering = ["id"]

    def __str__(self):
        return self.nombre

    @property
    def es_de_sistema(self):
        return self.nombre in Usuario.Rol.values


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
        ADMIN_NEGOCIO = "ADMIN_NEGOCIO", _("Administrador de negocio")
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
    # USUARIO_HAS_ROL: todos los roles del usuario. `rol` es el principal y siempre está incluido.
    roles = models.ManyToManyField("Rol", db_table="usuario_has_rol", related_name="usuarios", blank=True)

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

    @classmethod
    def from_db(cls, db, field_names, values):
        instancia = super().from_db(db, field_names, values)
        instancia._rol_previo = instancia.__dict__.get("rol")
        return instancia

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        super().save(*args, **kwargs)
        if update_fields is None or "rol" in update_fields:
            self._sincronizar_rol_principal()

    def _sincronizar_rol_principal(self):
        """Mantiene USUARIO_HAS_ROL coherente con `rol`: añade el principal y, si cambió,
        retira el anterior para que un cambio de rol nunca deje permisos viejos activos."""
        # `Rol` es el modelo del módulo (no `Usuario.Rol`, que solo son las opciones del campo).
        from .rbac import asegurar_rol_sistema
        principal = asegurar_rol_sistema(self.rol)
        previo = getattr(self, "_rol_previo", None)
        if previo and previo != self.rol:
            self.roles.remove(*Rol.objects.filter(nombre=previo))
        self.roles.add(principal)
        self._rol_previo = self.rol


class PermisoRol(models.Model):
    """Permiso por negocio, módulo y rol. 0=ninguno, 1=lectura, 2=escritura."""
    centro = models.ForeignKey(Centro, on_delete=models.CASCADE, related_name="permisos_rol")
    rol = models.CharField(max_length=15, choices=Usuario.Rol.choices)
    modulo = models.CharField(max_length=20)
    nivel = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "permiso_rol"
        constraints = [
            models.UniqueConstraint(fields=["centro", "rol", "modulo"], name="permiso_rol_unico"),
            models.CheckConstraint(condition=models.Q(nivel__in=[0, 1, 2]), name="permiso_rol_nivel_valido"),
        ]


class PermisoUsuario(models.Model):
    """Permiso personalizado de una persona. Si existe, reemplaza al de su rol para ese módulo."""
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="permisos_personales")
    modulo = models.CharField(max_length=20)
    nivel = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "permiso_usuario"
        constraints = [
            models.UniqueConstraint(fields=["usuario", "modulo"], name="permiso_usuario_unico"),
            models.CheckConstraint(condition=models.Q(nivel__in=[0, 1, 2]), name="permiso_usuario_nivel_valido"),
        ]
