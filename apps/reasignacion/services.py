"""Reasignación exprés: cancelación -> oferta a la primera clienta compatible -> siguiente si rechaza o vence."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import translation
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.agenda import services as agenda
from apps.agenda.exceptions import ConflictoAgenda
from apps.agenda.models import Cita
from apps.agenda.tasks import formatear_fecha
from apps.whatsapp import client

from .models import ListaEspera, OfertaReasignacion


def _hueco_libre(cita):
    """El hueco sigue libre si ninguna cita activa se cruza con él (cabina o profesional)."""
    from django.db.models import Q

    return not Cita.objects.filter(
        estado__in=agenda.ESTADOS_ACTIVOS, hora_inicio__lt=cita.hora_fin, hora_fin__gt=cita.hora_inicio
    ).filter(Q(cabina=cita.cabina) | Q(profesional=cita.profesional)).exists()


def iniciar_oferta(cita_id):
    """Crea y envía una oferta a la primera candidata. Devuelve la oferta o None."""
    cita = Cita.objects.select_related("servicio", "centro").get(pk=cita_id)
    ahora = timezone.now()
    if cita.estado != Cita.Estado.CANCELADA or cita.hora_inicio <= ahora or not _hueco_libre(cita):
        return None

    ini, fin = timezone.localtime(cita.hora_inicio), timezone.localtime(cita.hora_fin)
    candidata = (
        ListaEspera.objects.select_related("clienta")
        .filter(centro=cita.centro, estado=ListaEspera.Estado.ACTIVA, servicio=cita.servicio,
                fecha_deseada=ini.date(), hora_desde__lte=ini.time(), hora_hasta__gte=fin.time())
        .exclude(ofertas__cita_liberada=cita)
        .order_by("creado_en")
        .first()
    )
    if not candidata:
        return None

    minutos = settings.OFERTA_MINUTOS
    with transaction.atomic():
        orden = cita.ofertas.count() + 1
        oferta = OfertaReasignacion.objects.create(
            cita_liberada=cita, espera=candidata, orden=orden, expira_en=ahora + timedelta(minutes=minutos)
        )
    # Notificar y programar el vencimiento una vez confirmada la transacción.
    transaction.on_commit(lambda: _notificar_y_programar(oferta.id, cita, candidata, minutos))
    return oferta


def _notificar_y_programar(oferta_id, cita, candidata, minutos):
    from .tasks import expirar_oferta

    idioma = candidata.clienta.idioma
    with translation.override(idioma):
        fecha = formatear_fecha(cita.hora_inicio)
    client.send_template(
        candidata.clienta.telefono_whatsapp,
        settings.WHATSAPP_TEMPLATE_OFERTA,
        [candidata.clienta.nombre.split()[0], cita.servicio.nombre, fecha, minutos],
        [f"oferta:{oferta_id}:aceptar", f"oferta:{oferta_id}:rechazar"],
        idioma=idioma,
    )
    oferta = OfertaReasignacion.objects.get(pk=oferta_id)
    expirar_oferta.apply_async(args=[oferta_id], eta=oferta.expira_en)


def responder_oferta(oferta_id, aceptar):
    """Devuelve: 'aceptada' | 'rechazada' | 'no_disponible' | 'expirada'. Seguro ante concurrencia."""
    siguiente_de = None
    with transaction.atomic():
        oferta = (OfertaReasignacion.objects.select_for_update()
                  .select_related("cita_liberada__servicio", "espera").get(pk=oferta_id))
        if oferta.estado != OfertaReasignacion.Estado.PENDIENTE or oferta.expira_en <= timezone.now():
            return "expirada"
        liberada = oferta.cita_liberada
        oferta.respondida_en = timezone.now()

        if not aceptar:
            oferta.estado = OfertaReasignacion.Estado.RECHAZADA
            oferta.save(update_fields=["estado", "respondida_en"])
            resultado, siguiente_de = "rechazada", liberada.id
        else:
            try:
                agenda.crear_cita(
                    centro=liberada.centro, clienta=oferta.espera.clienta, servicio=liberada.servicio,
                    profesional=liberada.profesional, cabina=liberada.cabina, hora_inicio=liberada.hora_inicio,
                    estado=Cita.Estado.CONFIRMADA, origen=Cita.Origen.REASIGNACION,
                )
            except (ConflictoAgenda, ValidationError):
                oferta.estado = OfertaReasignacion.Estado.VENCIDA
                oferta.save(update_fields=["estado", "respondida_en"])
                return "no_disponible"
            oferta.estado = OfertaReasignacion.Estado.ACEPTADA
            oferta.save(update_fields=["estado", "respondida_en"])
            ListaEspera.objects.filter(pk=oferta.espera_id).update(estado=ListaEspera.Estado.ATENDIDA)
            resultado = "aceptada"

    if siguiente_de:
        iniciar_oferta(siguiente_de)
    return resultado


def vencer_oferta(oferta_id):
    """Llamado por Celery en expira_en: si nadie respondió, vence y se ofrece a la siguiente."""
    with transaction.atomic():
        oferta = OfertaReasignacion.objects.select_for_update().get(pk=oferta_id)
        if oferta.estado != OfertaReasignacion.Estado.PENDIENTE or oferta.expira_en > timezone.now():
            return False
        oferta.estado = OfertaReasignacion.Estado.VENCIDA
        oferta.save(update_fields=["estado"])
        cita_id = oferta.cita_liberada_id
    iniciar_oferta(cita_id)
    return True
