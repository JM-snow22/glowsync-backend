import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.agenda.exceptions import ConflictoAgenda
from apps.agenda.models import Cabina, Cita, DisponibilidadProfesional, Profesional, Recordatorio, Servicio, BloqueoAgenda
from apps.agenda import services
from apps.clientas.models import Clienta, FichaEstetica
from apps.core.models import Centro, Usuario
from apps.pagos.models import Pago
from apps.reasignacion.models import ListaEspera
from rest_framework.exceptions import ValidationError

NOMBRES = ["María", "Laura", "Valentina", "Camila", "Daniela", "Sofía", "Isabella", "Mariana", "Juliana", "Paula", "Andrea", "Carolina", "Natalia", "Luisa", "Sara", "Karen", "Diana", "Lina", "Angie", "Yenny","Gabriela", "Alejandra", "Stefanía", "Mónica", "Ximena", "Tatiana", "Verónica", "Johana", "Ana", "Claudia"]
APELLIDOS = ["Gómez", "Rodríguez", "Martínez", "López", "García", "Pérez", "Sánchez", "Ramírez", "Torres", "Díaz", "Fernández", "Vargas", "Castro", "Ortiz", "Rojas", "Mejía", "Herrera", "Medina", "Cardona", "Pinto","Epieyú", "Uriana", "Pushaina", "Iguarán", "Brito", "Arévalo", "Salcedo", "Mendoza", "Jiménez", "Ruiz"]
CUTIS = ["Normal", "Seco", "Graso", "Mixto", "Sensible", "Acneico"]
ALERGIAS = ["", "", "", "Látex", "Fragancias", "Ácido salicílico", "Níquel", "Parabenos", "Retinol"]
SERVICIOS = [
    ("Limpieza facial profunda", 60, 90000), ("Hidratación facial", 45, 75000), ("Masaje relajante", 60, 110000),
    ("Drenaje linfático", 50, 100000), ("Depilación láser (zona)", 30, 85000), ("Manicure semipermanente", 60, 55000),
    ("Pedicure spa", 75, 65000), ("Peeling químico", 45, 130000),
]
PROFESIONALES = ["Daniela Vergara", "Carolina Pinto", "Laura Medina", "Andrea Salcedo", "Natalia Brito"]


class Command(BaseCommand):
    help = "Carga datos de ejemplo (por defecto 100 clientas y 100 citas)."

    def add_arguments(self, parser):
        parser.add_argument("--n", type=int, default=100, help="Cantidad de clientas y de citas")
        parser.add_argument("--reset", action="store_true", help="Borra el centro demo antes de crear")
        parser.add_argument("--seed", type=int, default=42)

    @transaction.atomic
    def handle(self, *args, n, reset, seed, **opts):
        rnd = random.Random(seed)
        if reset:
            Centro.objects.filter(nombre="Glow Estética Riohacha").delete()
        if Centro.objects.filter(nombre="Glow Estética Riohacha").exists():
            self.stdout.write(self.style.WARNING("El centro demo ya existe. Usa --reset para recrearlo."))
            return

        admin, _ = Usuario.objects.get_or_create(
            email="admin@glowsync.co",
            defaults={"nombre": "Admin GlowSync", "rol": Usuario.Rol.ADMIN_SAAS, "is_staff": True, "is_superuser": True})
        admin.set_password("Admin12345!"); admin.save()

        centro = Centro.objects.create(
            nombre="Glow Estética Riohacha", nit="900123456-7", ciudad="Riohacha", telefono_whatsapp="573001112233",
            plan=Centro.Plan.PRO, fecha_vencimiento=timezone.localdate() + timedelta(days=365))
        recep = Usuario.objects.create_user("recepcion@glowsync.co", "Recep12345!", nombre="Recepción Glow",
                                            rol=Usuario.Rol.RECEPCIONISTA, centro=centro)

        cabinas = [Cabina.objects.create(centro=centro, nombre=f"Cabina {i}") for i in range(1, 5)]
        servicios = [Servicio.objects.create(centro=centro, nombre=nom, duracion_minutos=d, precio=Decimal(p)) for nom, d, p in SERVICIOS]
        profesionales = []
        for i, nom in enumerate(PROFESIONALES):
            user = Usuario.objects.create_user(f"esteticista{i + 1}@glowsync.co", "Estet12345!", nombre=nom, rol=Usuario.Rol.ESTETICISTA, centro=centro)
            prof = Profesional.objects.create(centro=centro, usuario=user, nombre=nom, telefono=f"57300{rnd.randint(1000000, 9999999)}")
            for dia in range(0, 6):  # lunes a sábado
                hasta = time(13, 0) if dia == 5 else time(18, 0)
                DisponibilidadProfesional.objects.create(profesional=prof, dia_semana=dia, hora_desde=time(8, 0), hora_hasta=hasta)
            profesionales.append(prof)

        # Un bloqueo de ejemplo en el futuro (todo el centro)
        dia_bloq = timezone.localdate() + timedelta(days=10)
        BloqueoAgenda.objects.create(
            centro=centro, motivo="Capacitación del equipo",
            inicio=timezone.make_aware(datetime.combine(dia_bloq, time(14, 0))),
            fin=timezone.make_aware(datetime.combine(dia_bloq, time(16, 0))))

        # ---- Clientas + fichas ----
        clientas, tels = [], set()
        for _ in range(n):
            while True:
                tel = f"573{rnd.choice('0125')}{rnd.randint(0, 9)}{rnd.randint(1000000, 9999999)}"[:12]
                if tel not in tels:
                    tels.add(tel); break
            nombre = f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}"
            c = Clienta.objects.create(centro=centro, nombre=nombre, telefono_whatsapp=tel, idioma=rnd.choices(["es", "en"], [85, 15])[0], creado_en=timezone.now() - timedelta(days=rnd.randint(0, 365)))
            FichaEstetica.objects.create(clienta=c, tipo_cutis=rnd.choice(CUTIS), alergias=rnd.choice(ALERGIAS), observaciones=rnd.choice(["", "", "Piel sensible al sol", "Embarazada (consultar)", "Prefiere citas en la mañana"]))
            clientas.append(c)

        # ---- Citas (60 % pasadas, 40 % futuras) ----
        hoy = timezone.localdate()
        creadas = 0
        intentos = 0
        while creadas < n and intentos < n * 200:
            intentos += 1
            pasada = creadas < int(n * 0.6)
            dias = -rnd.randint(1, 30) if pasada else rnd.randint(1, 14)
            fecha = hoy + timedelta(days=dias)
            if fecha.weekday() == 6:
                continue
            inicio = timezone.make_aware(datetime.combine(fecha, time(rnd.randint(8, 16), rnd.choice([0, 30]))))
            if pasada:
                estado = rnd.choices([Cita.Estado.COMPLETADA, Cita.Estado.NO_ASISTIO, Cita.Estado.CANCELADA], [70, 15, 15])[0]
            else:
                estado = rnd.choices([Cita.Estado.CONFIRMADA, Cita.Estado.PENDIENTE], [60, 40])[0]
            try:
                cita = services.crear_cita(
                    centro=centro, clienta=rnd.choice(clientas), servicio=rnd.choice(servicios),
                    profesional=rnd.choice(profesionales), cabina=rnd.choice(cabinas), hora_inicio=inicio,
                    estado=estado, permitir_pasado=True, programar=False)
            except (ValidationError, ConflictoAgenda):
                continue
            creadas += 1
            self._pagos_y_recordatorios(cita, rnd)

        # ---- Lista de espera (futuro) ----
        for _ in range(max(5, n // 10)):
            desde = rnd.choice([8, 9, 10, 13, 14])
            ListaEspera.objects.create(
                centro=centro, clienta=rnd.choice(clientas), servicio=rnd.choice(servicios),
                fecha_deseada=hoy + timedelta(days=rnd.randint(1, 14)), hora_desde=time(desde, 0), hora_hasta=time(desde + 4, 0))

        self.stdout.write(self.style.SUCCESS(
            f"Listo: {len(clientas)} clientas, {creadas} citas, {Pago.objects.count()} pagos, "
            f"{Recordatorio.objects.count()} recordatorios, {ListaEspera.objects.count()} en lista de espera."))
        self.stdout.write("Usuarios (solo desarrollo):\n"
                    "  admin@glowsync.co / Admin12345!        (ADMIN_SAAS)\n"
                    "  recepcion@glowsync.co / Recep12345!    (RECEPCIONISTA)\n"
                    "  esteticista1@glowsync.co / Estet12345! (ESTETICISTA)")

    def _pagos_y_recordatorios(self, cita, rnd):
        E, P = Cita.Estado, Pago
        sena = (cita.servicio.precio * Decimal(cita.servicio.porcentaje_sena) / 100).quantize(Decimal("0.01"))
        saldo = cita.servicio.precio - sena
        ref = f"DEMO-{cita.id}"
        if cita.estado == E.COMPLETADA:
            Pago.objects.create(centro=cita.centro, cita=cita, tipo=P.Tipo.SENA, estado=P.Estado.APROBADO, monto=sena, pasarela="WOMPI", referencia=f"{ref}-S")
            Pago.objects.create(centro=cita.centro, cita=cita, tipo=P.Tipo.SALDO, estado=P.Estado.APROBADO, monto=saldo, pasarela="WOMPI", referencia=f"{ref}-R")
            # ~12 % de las completadas vienen de reasignación exprés (alimenta "dinero recuperado")
            if rnd.random() < 0.12:
                Cita.objects.filter(pk=cita.pk).update(origen=Cita.Origen.REASIGNACION)
        elif cita.estado == E.NO_ASISTIO:
            Pago.objects.create(centro=cita.centro, cita=cita, tipo=P.Tipo.SENA, estado=P.Estado.APROBADO, monto=sena, pasarela="WOMPI", referencia=f"{ref}-S")
        elif cita.estado == E.CANCELADA:
            Pago.objects.create(centro=cita.centro, cita=cita, tipo=P.Tipo.SENA, estado=P.Estado.REEMBOLSADO, monto=sena, pasarela="WOMPI", referencia=f"{ref}-S")
        elif cita.estado == E.CONFIRMADA:
            Pago.objects.create(centro=cita.centro, cita=cita, tipo=P.Tipo.SENA, estado=P.Estado.APROBADO, monto=sena, pasarela="WOMPI", referencia=f"{ref}-S")
        else:  # PENDIENTE
            Pago.objects.create(centro=cita.centro, cita=cita, tipo=P.Tipo.SENA, estado=P.Estado.PENDIENTE, monto=sena, pasarela="WOMPI", referencia=f"{ref}-S")

        if cita.estado in (E.CONFIRMADA, E.PENDIENTE):
            ahora = timezone.now()
            for tipo, h in ((Recordatorio.Tipo.H48, 48), (Recordatorio.Tipo.H24, 24)):
                cuando = cita.hora_inicio - timedelta(hours=h)
                enviado = cuando if cuando <= ahora else None
                resp = Recordatorio.Respuesta.CONFIRMA if (enviado and cita.estado == E.CONFIRMADA) else Recordatorio.Respuesta.SIN_RESPUESTA
                Recordatorio.objects.create(cita=cita, tipo=tipo, programado_para=cuando, enviado_en=enviado, respuesta=resp)
