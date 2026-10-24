from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0002_admin_negocio")]

    operations = [
        migrations.CreateModel(
            name="PermisoRol",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rol", models.CharField(choices=[("ADMIN_SAAS", "Administrador SaaS"), ("ADMIN_NEGOCIO", "Administrador de negocio"), ("RECEPCIONISTA", "Recepcionista"), ("ESTETICISTA", "Esteticista")], max_length=15)),
                ("modulo", models.CharField(max_length=20)),
                ("nivel", models.PositiveSmallIntegerField()),
                ("centro", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="permisos_rol", to="core.centro")),
            ],
            options={"db_table": "permiso_rol"},
        ),
        migrations.AddConstraint(model_name="permisorol", constraint=models.UniqueConstraint(fields=("centro", "rol", "modulo"), name="permiso_rol_unico")),
        migrations.AddConstraint(model_name="permisorol", constraint=models.CheckConstraint(condition=models.Q(nivel__in=[0, 1, 2]), name="permiso_rol_nivel_valido")),
    ]
