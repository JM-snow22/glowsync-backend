from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0003_permisorol")]

    operations = [
        migrations.CreateModel(
            name="PermisoUsuario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("modulo", models.CharField(max_length=20)),
                ("nivel", models.PositiveSmallIntegerField()),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="permisos_personales", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "permiso_usuario"},
        ),
        migrations.AddConstraint(model_name="permisousuario", constraint=models.UniqueConstraint(fields=("usuario", "modulo"), name="permiso_usuario_unico")),
        migrations.AddConstraint(model_name="permisousuario", constraint=models.CheckConstraint(condition=models.Q(nivel__in=[0, 1, 2]), name="permiso_usuario_nivel_valido")),
    ]
