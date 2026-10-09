from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agenda.models import Cita
from apps.core.permissions import CentroPermission
from apps.pagos.models import Pago
from apps.reasignacion.models import OfertaReasignacion


class ResumenView(APIView):
    """KPIs del centro. ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD (por defecto, últimos 30 días)."""

    permission_classes = [CentroPermission]

    def get(self, request):
        hoy = timezone.localdate()
        try:
            desde = timezone.datetime.fromisoformat(request.GET["desde"]).date() if "desde" in request.GET else hoy - timedelta(days=30)
            hasta = timezone.datetime.fromisoformat(request.GET["hasta"]).date() if "hasta" in request.GET else hoy
        except ValueError:
            return Response({"detail": _("Formato de fecha inválido (YYYY-MM-DD).")}, status=400)

        centro = request.user.centro_id
        citas = Cita.objects.filter(centro_id=centro, hora_inicio__date__gte=desde, hora_inicio__date__lte=hasta)
        por_estado = dict(citas.values_list("estado").annotate(n=Count("id")))
        E = Cita.Estado
        atendibles = sum(por_estado.get(e, 0) for e in (E.COMPLETADA, E.NO_ASISTIO))
        no_asistio = por_estado.get(E.NO_ASISTIO, 0)

        reasignadas = citas.filter(origen=Cita.Origen.REASIGNACION).exclude(estado=E.CANCELADA)
        recuperado = reasignadas.aggregate(t=Sum("servicio__precio"))["t"] or Decimal("0")
        ingresos = (Pago.objects.filter(centro_id=centro, estado=Pago.Estado.APROBADO,
                                        tipo__in=[Pago.Tipo.SENA, Pago.Tipo.SALDO],
                                        creado_en__date__gte=desde, creado_en__date__lte=hasta)
                    .aggregate(t=Sum("monto"))["t"] or Decimal("0"))
        ofertas = OfertaReasignacion.objects.filter(espera__centro_id=centro, enviada_en__date__gte=desde, enviada_en__date__lte=hasta)

        return Response({
            "desde": desde, "hasta": hasta,
            "citas_total": citas.count(),
            "citas_por_estado": por_estado,
            "tasa_inasistencia": round(no_asistio / atendibles, 4) if atendibles else 0,
            "citas_reasignadas": reasignadas.count(),
            "dinero_recuperado": recuperado,
            "ingresos_aprobados": ingresos,
            "ofertas_enviadas": ofertas.count(),
            "ofertas_aceptadas": ofertas.filter(estado=OfertaReasignacion.Estado.ACEPTADA).count(),
        })
