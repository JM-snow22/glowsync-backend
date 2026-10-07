import apps.core.models
import django.db.models.deletion
from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        BtreeGistExtension(),
        migrations.CreateModel(
            name='Centro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=150)),
                ('nit', models.CharField(blank=True, max_length=30)),
                ('ciudad', models.CharField(blank=True, max_length=80)),
                ('telefono_whatsapp', models.CharField(blank=True, max_length=20)),
                ('plan', models.CharField(choices=[('BASICO', 'Básico'), ('PRO', 'Pro'), ('PREMIUM', 'Premium')], default='BASICO', max_length=10)),
                ('estado_suscripcion', models.CharField(choices=[('ACTIVA', 'Activa'), ('VENCIDA', 'Vencida'), ('SUSPENDIDA', 'Suspendida')], default='ACTIVA', max_length=12)),
                ('fecha_vencimiento', models.DateField()),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'centro_estetico',
            },
        ),
        migrations.CreateModel(
            name='Usuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('nombre', models.CharField(max_length=120)),
                ('rol', models.CharField(choices=[('ADMIN_SAAS', 'Administrador SaaS'), ('RECEPCIONISTA', 'Recepcionista'), ('ESTETICISTA', 'Esteticista')], max_length=15)),
                ('idioma', models.CharField(choices=[('es', 'Español'), ('en', 'English')], default='es', max_length=2)),
                ('is_active', models.BooleanField(default=True)),
                ('is_staff', models.BooleanField(default=False)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
                ('centro', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='usuarios', to='core.centro')),
            ],
            options={
                'db_table': 'usuario',
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('centro__isnull', True), ('rol', 'ADMIN_SAAS')), models.Q(models.Q(('rol', 'ADMIN_SAAS'), _negated=True), ('centro__isnull', False)), _connector='OR'), name='usuario_rol_centro')],
            },
            managers=[
                ('objects', apps.core.models.UsuarioManager()),
            ],
        ),
    ]