"""Reglas de negocio de la agenda. Las vistas, el seed y los webhooks pasan por aquí."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from .exceptions import ConflictoAgenda
from .models import BloqueoAgenda, Cita, DisponibilidadProfesional, Recordatorio

ESTADOS_ACTIVOS = (Cita.Estado.PENDIENTE, Cita.Estado.CONFIRMADA)

TRANSICIONES = {
    Cita.Estado.PENDIENTE: {Cita.Estado.CONFIRMADA, Cita.Estado.CANCELADA},
    Cita.Estado.CONFIRMADA: {Cita.Estado.COMPLETADA, Cita.Estado.NO_ASISTIO, Cita.Estado.CANCELADA},
}


def validar_agenda(*, centro, clienta, servicio, profesional, cabina, inicio, fin):
    for objeto, nombre in ((clienta, "clienta"), (servicio, "servicio"), (profesional, "profesional"), (cabina, "cabina")):
        if objeto.centro_id != centro.id:
            raise ValidationError({nombre: _("No pertenece a este centro.")})
    if not cabina.activa:
        raise ValidationError({"cabina": _("La cabina está inactiva.")})
    if not profesional.activo:
        raise ValidationError({"profesional": _("El profesional está inactivo.")})
    if not servicio.activo:
        raise ValidationError({"servicio": _("El servicio está inactivo.")})

    ini, fi = timezone.localtime(inicio), timezone.localtime(fin)
    if ini.date() != fi.date():
        raise ValidationError(_("La cita no puede cruzar de un día a otro."))

    atiende = DisponibilidadProfesional.objects.filter(
        profesional=profesional, dia_semana=ini.weekday(), hora_desde__lte=ini.time(), hora_hasta__gte=fi.time()
    ).exists()
    if not atiende:
        raise ValidationError(_("El profesional no atiende en ese día/horario."))

    bloqueado = (
        BloqueoAgenda.objects.filter(centro=centro, inicio__lt=fin, fin__gt=inicio)
        .filter(Q(profesional__isnull=True) | Q(profesional=profesional))
        .exists()
    )
    if bloqueado:
        raise ValidationError(_("Ese horario está bloqueado en la agenda."))


def crear_cita(
    *, centro, clienta, servicio, profesional, cabina, hora_inicio,
    estado=Cita.Estado.PENDIENTE, origen=Cita.Origen.NORMAL,
    permitir_pasado=False, programar=True,
):
    if not permitir_pasado and hora_inicio <= timezone.now():
        raise ValidationError({"hora_inicio": _("La cita debe ser a futuro.")})
    hora_fin = hora_inicio + timedelta(minutes=servicio.duracion_minutos)
    validar_agenda(centro=centro, clienta=clienta, servicio=servicio, profesional=profesional,
                   cabina=cabina, inicio=hora_inicio, fin=hora_fin)
    try:
        with transaction.atomic():
            cita = Cita.objects.create(
                centro=centro, clienta=clienta, servicio=servicio, profesional=profesional, cabina=cabina,
                hora_inicio=hora_inicio, hora_fin=hora_fin, estado=estado, origen=origen,
            )
    except IntegrityError as exc:
        if "sin_cruce" in str(exc):
            raise ConflictoAgenda() from exc
        raise
    if programar and estado in ESTADOS_ACTIVOS:
        transaction.on_commit(lambda: programar_recordatorios(cita.id))
    return cita


def programar_recordatorios(cita_id):
    from .tasks import enviar_recordatorio

    cita = Cita.objects.get(pk=cita_id)
    ahora = timezone.now()
    for tipo, horas in ((Recordatorio.Tipo.H48, 48), (Recordatorio.Tipo.H24, 24)):
        cuando = cita.hora_inicio - timedelta(hours=horas)
        if cuando <= ahora:
            continue
        rec, creado = Recordatorio.objects.get_or_create(cita=cita, tipo=tipo, defaults={"programado_para": cuando})
        if creado:
            enviar_recordatorio.apply_async(args=[rec.id], eta=cuando)


def cambiar_estado(cita, nuevo):
    permitidos = TRANSICIONES.get(cita.estado, set())
    if nuevo not in permitidos:
        raise ValidationError(_("No se puede pasar de %(origen)s a %(destino)s.") % {"origen": cita.get_estado_display(), "destino": Cita.Estado(nuevo).label})
    cita.estado = nuevo
    cita.save(update_fields=["estado"])
    if nuevo == Cita.Estado.CANCELADA:
        # Dispara la reasignación exprés al instante (RNF-02: < 3 s).
        from apps.reasignacion.tasks import iniciar_reasignacion

        transaction.on_commit(lambda: iniciar_reasignacion.delay(cita.id))
    return cita
