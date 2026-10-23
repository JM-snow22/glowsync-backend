from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="usuario", name="rol",
            field=models.CharField(max_length=15, choices=[
                ("ADMIN_SAAS", "Administrador SaaS"),
                ("ADMIN_NEGOCIO", "Administrador de negocio"),
                ("RECEPCIONISTA", "Recepcionista"),
                ("ESTETICISTA", "Esteticista"),
            ]),
        ),
    ]
