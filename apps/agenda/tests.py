import hashlib
import hmac
import json
from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITransactionTestCase

from apps.agenda import services
from apps.agenda.models import Cabina, Cita, DisponibilidadProfesional, Profesional, Servicio
from apps.clientas.models import Clienta
from apps.core.models import Centro, Usuario
from apps.pagos.models import Pago
from apps.reasignacion import services as reasignacion
from apps.reasignacion.models import ListaEspera, OfertaReasignacion

PASSWORD = "Clave12345!"


def manana(hora=10, minuto=0):
    d = timezone.localdate() + timedelta(days=1)
    return timezone.make_aware(datetime.combine(d, time(hora, minuto)))


def crear_centro(prefijo="a"):
    centro = Centro.objects.create(nombre=f"Centro {prefijo}", fecha_vencimiento=timezone.localdate() + timedelta(days=30))
    recep = Usuario.objects.create_user(f"recep-{prefijo}@x.co", PASSWORD, nombre="Recep", rol=Usuario.Rol.RECEPCIONISTA, centro=centro)
    estet = Usuario.objects.create_user(f"estet-{prefijo}@x.co", PASSWORD, nombre="Estet", rol=Usuario.Rol.ESTETICISTA, centro=centro)
    cab1 = Cabina.objects.create(centro=centro, nombre="C1")
    cab2 = Cabina.objects.create(centro=centro, nombre="C2")
    serv = Servicio.objects.create(centro=centro, nombre="Facial", duracion_minutos=60, precio=Decimal("100000"))
    prof1 = Profesional.objects.create(centro=centro, nombre="P1")
    prof2 = Profesional.objects.create(centro=centro, nombre="P2")
    for p in (prof1, prof2):
        for dia in range(7):
            DisponibilidadProfesional.objects.create(profesional=p, dia_semana=dia, hora_desde=time(0, 0), hora_hasta=time(23, 59))
    clientas = [Clienta.objects.create(centro=centro, nombre=f"Clienta {i}", telefono_whatsapp=f"57300000000{i}") for i in range(4)]
    return SimpleNamespace(centro=centro, recep=recep, estet=estet, cab1=cab1, cab2=cab2, serv=serv,
                           prof1=prof1, prof2=prof2, clientas=clientas)


def cliente_de(usuario):
    cache.clear()
    c = APIClient()
    r = c.post("/api/auth/login/", {"email": usuario.email, "password": PASSWORD}, format="json")
    assert r.status_code == 200, r.content
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    return c


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, WHATSAPP_APP_SECRET="secreto-wa", PAGOS_WEBHOOK_SECRET="secreto-pagos")
class FlujosTest(APITransactionTestCase):
    def setUp(self):
        p = mock.patch("apps.whatsapp.client._post", return_value="wamid.TEST")
        self.wa = p.start()
        self.addCleanup(p.stop)
        self.A = crear_centro("a")
        self.B = crear_centro("b")

    def _cita(self, ctx=None, cab=None, prof=None, clienta=None, inicio=None, **kw):
        ctx = ctx or self.A
        return services.crear_cita(
            centro=ctx.centro, clienta=clienta or ctx.clientas[0], servicio=ctx.serv,
            profesional=prof or ctx.prof1, cabina=cab or ctx.cab1, hora_inicio=inicio or manana(), **kw)

    # ---------- Multitenant y permisos ----------
    def test_aislamiento_entre_centros(self):
        cb = cliente_de(self.B.recep)
        self.assertEqual(cb.get("/api/clientas/").data["count"], 4)  # solo las del centro B
        ids_a = {c.id for c in self.A.clientas}
        ids_vistos = {c["id"] for c in cb.get("/api/clientas/").data["results"]}
        self.assertFalse(ids_a & ids_vistos)
        # No puede crear una cita usando datos del centro A
        r = cb.post("/api/citas/", {"clienta": self.A.clientas[0].id, "servicio": self.B.serv.id,
                                    "profesional": self.B.prof1.id, "cabina": self.B.cab1.id,
                                    "hora_inicio": manana().isoformat()}, format="json")
        self.assertEqual(r.status_code, 400)
        # Tampoco puede leer una cita del centro A por id
        cita_a = self._cita()
        self.assertEqual(cb.get(f"/api/citas/{cita_a.id}/").status_code, 404)

    def test_suscripcion_vencida_bloquea(self):
        Centro.objects.filter(pk=self.A.centro.pk).update(estado_suscripcion="VENCIDA")
        r = APIClient().post("/api/auth/login/", {"email": self.A.recep.email, "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_esteticista_es_solo_lectura_en_citas(self):
        c = cliente_de(self.A.estet)
        self.assertEqual(c.get("/api/citas/").status_code, 200)
        r = c.post("/api/citas/", {}, format="json")
        self.assertEqual(r.status_code, 403)

    # ---------- Anti-solapamiento (PB-05) ----------
    def test_cruce_cabina_409(self):
        c = cliente_de(self.A.recep)
        pay = {"clienta": self.A.clientas[0].id, "servicio": self.A.serv.id, "hora_inicio": manana(10).isoformat()}
        self.assertEqual(c.post("/api/citas/", {**pay, "profesional": self.A.prof1.id, "cabina": self.A.cab1.id}, format="json").status_code, 201)
        # misma cabina, otro profesional, cruce parcial (10:30)
        r = c.post("/api/citas/", {**pay, "hora_inicio": manana(10, 30).isoformat(), "profesional": self.A.prof2.id, "cabina": self.A.cab1.id}, format="json")
        self.assertEqual(r.status_code, 409)
        # mismo profesional, otra cabina
        r = c.post("/api/citas/", {**pay, "hora_inicio": manana(10, 30).isoformat(), "profesional": self.A.prof1.id, "cabina": self.A.cab2.id}, format="json")
        self.assertEqual(r.status_code, 409)
        # citas contiguas (11:00) sí se permiten
        r = c.post("/api/citas/", {**pay, "hora_inicio": manana(11).isoformat(), "profesional": self.A.prof1.id, "cabina": self.A.cab1.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_la_base_de_datos_garantiza_el_no_cruce(self):
        """Aunque alguien se salte la capa de servicio, PostgreSQL rechaza el cruce."""
        c1 = self._cita()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cita.objects.create(centro=self.A.centro, clienta=self.A.clientas[1], servicio=self.A.serv,
                                profesional=self.A.prof2, cabina=self.A.cab1,
                                hora_inicio=c1.hora_inicio + timedelta(minutes=15), hora_fin=c1.hora_fin + timedelta(minutes=15))

    def test_cita_cancelada_libera_el_horario(self):
        c1 = self._cita()
        services.cambiar_estado(c1, Cita.Estado.CANCELADA)
        self._cita(clienta=self.A.clientas[1])  # mismo horario: ahora sí se puede

    # ---------- Reasignación exprés (PB-09 / PB-10) ----------
    def _espera(self, clienta, desde=9, hasta=12, creado_delta=0):
        e = ListaEspera.objects.create(centro=self.A.centro, clienta=clienta, servicio=self.A.serv,
                                       fecha_deseada=manana().date(), hora_desde=time(desde), hora_hasta=time(hasta))
        ListaEspera.objects.filter(pk=e.pk).update(creado_en=timezone.now() + timedelta(seconds=creado_delta))
        return e

    def test_reasignacion_completa(self):
        cita = self._cita(clienta=self.A.clientas[0])
        e1 = self._espera(self.A.clientas[1], creado_delta=-30)
        e2 = self._espera(self.A.clientas[2], creado_delta=-10)
        self._espera(self.A.clientas[3], desde=14, hasta=18)  # fuera del rango: no debe recibir oferta

        c = cliente_de(self.A.recep)
        self.assertEqual(c.post(f"/api/citas/{cita.id}/cancelar/").status_code, 200)

        o1 = OfertaReasignacion.objects.get(cita_liberada=cita, orden=1)
        self.assertEqual(o1.espera_id, e1.id)  # la más antigua, compatible
        self.assertEqual(o1.estado, "PENDIENTE")
        self.assertTrue(timedelta(minutes=11) < o1.expira_en - timezone.now() <= timedelta(minutes=12))

        # La primera rechaza -> pasa a la siguiente
        self.assertEqual(reasignacion.responder_oferta(o1.id, aceptar=False), "rechazada")
        o2 = OfertaReasignacion.objects.get(cita_liberada=cita, orden=2)
        self.assertEqual(o2.espera_id, e2.id)

        # La segunda acepta -> se crea la nueva cita confirmada
        self.assertEqual(reasignacion.responder_oferta(o2.id, aceptar=True), "aceptada")
        nueva = Cita.objects.get(clienta=self.A.clientas[2], origen=Cita.Origen.REASIGNACION)
        self.assertEqual(nueva.estado, Cita.Estado.CONFIRMADA)
        self.assertEqual(nueva.hora_inicio, cita.hora_inicio)
        e2.refresh_from_db()
        self.assertEqual(e2.estado, ListaEspera.Estado.ATENDIDA)
        # Aceptar de nuevo (doble clic) no duplica nada
        self.assertEqual(reasignacion.responder_oferta(o2.id, aceptar=True), "expirada")
        self.assertEqual(Cita.objects.filter(origen=Cita.Origen.REASIGNACION).count(), 1)

    def test_oferta_vencida_pasa_a_la_siguiente(self):
        cita = self._cita()
        self._espera(self.A.clientas[1], creado_delta=-30)
        self._espera(self.A.clientas[2], creado_delta=-10)
        services.cambiar_estado(cita, Cita.Estado.CANCELADA)  # dispara la oferta 1
        o1 = OfertaReasignacion.objects.get(cita_liberada=cita, orden=1)
        self.assertFalse(reasignacion.vencer_oferta(o1.id))  # aún no vence
        OfertaReasignacion.objects.filter(pk=o1.pk).update(expira_en=timezone.now() - timedelta(seconds=1))
        self.assertTrue(reasignacion.vencer_oferta(o1.id))
        o1.refresh_from_db()
        self.assertEqual(o1.estado, "VENCIDA")
        self.assertTrue(OfertaReasignacion.objects.filter(cita_liberada=cita, orden=2).exists())
        # Responder tarde a una oferta vencida no sirve
        self.assertEqual(reasignacion.responder_oferta(o1.id, aceptar=True), "expirada")

    def test_oferta_no_se_acepta_si_el_hueco_fue_ocupado(self):
        cita = self._cita()
        self._espera(self.A.clientas[1])
        services.cambiar_estado(cita, Cita.Estado.CANCELADA)
        o = OfertaReasignacion.objects.get(cita_liberada=cita)  # creada al cancelar (modo eager)
        self._cita(clienta=self.A.clientas[3])  # recepción lo reserva manualmente mientras tanto
        self.assertEqual(reasignacion.responder_oferta(o.id, aceptar=True), "no_disponible")

    # ---------- Webhooks ----------
    def _firmar(self, body, secreto="secreto-wa", prefijo="sha256="):
        return prefijo + hmac.new(secreto.encode(), body, hashlib.sha256).hexdigest()

    def _evento_boton(self, telefono, payload):
        return json.dumps({"entry": [{"changes": [{"value": {"messages": [
            {"from": telefono, "type": "button", "button": {"payload": payload}}]}}]}]}).encode()

    def test_webhook_whatsapp_valida_firma_y_confirma_cita(self):
        cita = self._cita()
        body = self._evento_boton(self.A.clientas[0].telefono_whatsapp, f"cita:{cita.id}:confirmar")
        c = APIClient()
        r = c.post("/api/webhooks/whatsapp/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256="sha256=falsa")
        self.assertEqual(r.status_code, 403)
        r = c.post("/api/webhooks/whatsapp/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=self._firmar(body))
        self.assertEqual(r.status_code, 200, r.content)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CONFIRMADA)

    def test_webhook_ignora_boton_de_otra_persona(self):
        cita = self._cita()
        body = self._evento_boton("573999999999", f"cita:{cita.id}:cancelar")
        APIClient().post("/api/webhooks/whatsapp/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=self._firmar(body))
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.PENDIENTE)

    def test_webhook_whatsapp_verificacion_inicial(self):
        r = APIClient().get("/api/webhooks/whatsapp/", {"hub.mode": "subscribe", "hub.verify_token": "glowsync-verify", "hub.challenge": "1234"})
        self.assertEqual((r.status_code, r.content), (200, b"1234"))

    def test_cancelar_por_whatsapp_dispara_reasignacion(self):
        cita = self._cita()
        self._espera(self.A.clientas[1])
        body = self._evento_boton(self.A.clientas[0].telefono_whatsapp, f"cita:{cita.id}:cancelar")
        APIClient().post("/api/webhooks/whatsapp/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=self._firmar(body))
        self.assertTrue(OfertaReasignacion.objects.filter(cita_liberada=cita, estado="PENDIENTE").exists())

    def test_pago_webhook_es_idempotente_y_confirma_la_cita(self):
        cita = self._cita()
        c = cliente_de(self.A.recep)
        r = c.post("/api/pagos/", {"cita": cita.id, "tipo": "SENA"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Decimal(r.data["monto"]), Decimal("30000.00"))  # 30 % de 100.000
        # segunda seña mientras hay una pendiente: rechazada
        self.assertEqual(c.post("/api/pagos/", {"cita": cita.id, "tipo": "SENA"}, format="json").status_code, 400)

        body = json.dumps({"referencia": r.data["referencia"], "estado": "APROBADO"}).encode()
        firma = self._firmar(body, "secreto-pagos", prefijo="")
        w = APIClient()
        self.assertEqual(w.post("/api/webhooks/pagos/", body, content_type="application/json", HTTP_X_SIGNATURE="mala").status_code, 403)
        self.assertEqual(w.post("/api/webhooks/pagos/", body, content_type="application/json", HTTP_X_SIGNATURE=firma).data, {"ok": True})
        self.assertEqual(w.post("/api/webhooks/pagos/", body, content_type="application/json", HTTP_X_SIGNATURE=firma).data, {"duplicado": True})
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CONFIRMADA)
        self.assertEqual(Pago.objects.filter(cita=cita).count(), 1)

    def test_dashboard(self):
        c1 = self._cita(inicio=manana(9)); c2 = self._cita(inicio=manana(11), clienta=self.A.clientas[1])
        for c, e in ((c1, Cita.Estado.COMPLETADA), (c2, Cita.Estado.NO_ASISTIO)):
            Cita.objects.filter(pk=c.pk).update(estado=e)
        r = cliente_de(self.A.recep).get("/api/dashboard/resumen/", {"hasta": (timezone.localdate() + timedelta(days=3)).isoformat()})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["tasa_inasistencia"], 0.5)

    # ---------- Multilenguaje (es / en) ----------
    def _cruce(self, c, **headers):
        pay = {"clienta": self.A.clientas[0].id, "servicio": self.A.serv.id, "hora_inicio": manana(10).isoformat(),
               "profesional": self.A.prof1.id, "cabina": self.A.cab1.id}
        c.post("/api/citas/", pay, format="json", **headers)  # primera: OK (o ya existe)
        return c.post("/api/citas/", {**pay, "clienta": self.A.clientas[1].id}, format="json", **headers)

    def test_errores_segun_accept_language(self):
        c = cliente_de(self.A.recep)
        r_en = self._cruce(c, HTTP_ACCEPT_LANGUAGE="en")
        self.assertEqual(r_en.status_code, 409)
        self.assertIn("already taken", r_en.data["detail"])
        self.assertEqual(r_en["Content-Language"], "en")
        r_es = c.post("/api/citas/", {"clienta": self.A.clientas[1].id, "servicio": self.A.serv.id, "hora_inicio": manana(10).isoformat(),
                                      "profesional": self.A.prof1.id, "cabina": self.A.cab1.id}, format="json", HTTP_ACCEPT_LANGUAGE="es")
        self.assertIn("ocupado", r_es.data["detail"])
        self.assertEqual(r_es["Content-Language"], "es")

    def test_idioma_del_perfil_se_usa_sin_cabecera_y_la_cabecera_manda(self):
        c = cliente_de(self.A.recep)
        r = c.patch("/api/auth/me/", {"idioma": "en"}, format="json")
        self.assertEqual((r.status_code, r.data["idioma"]), (200, "en"))
        self.assertEqual(cliente_de(self.A.recep).get("/api/auth/me/").data["idioma"], "en")  # persistió
        r = self._cruce(c)  # sin Accept-Language: usa el idioma del perfil
        self.assertIn("already taken", r.data["detail"])
        r = self._cruce(c, HTTP_ACCEPT_LANGUAGE="es")  # la cabecera explícita tiene prioridad
        self.assertIn("ocupado", r.data["detail"])

    def test_idioma_no_soportado(self):
        r = cliente_de(self.A.recep).patch("/api/auth/me/", {"idioma": "fr"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_mensajes_de_validacion_de_drf_estan_traducidos(self):
        c = cliente_de(self.A.recep)
        en = str(c.post("/api/clientas/", {}, format="json", HTTP_ACCEPT_LANGUAGE="en").data)
        es = str(c.post("/api/clientas/", {}, format="json", HTTP_ACCEPT_LANGUAGE="es").data)
        self.assertIn("This field is required", en)
        self.assertNotIn("This field is required", es)

    def test_etiquetas_de_estados_traducidas(self):
        from django.utils import translation
        with translation.override("en"):
            self.assertEqual(str(Cita.Estado.NO_ASISTIO.label), "No-show")
        with translation.override("es"):
            self.assertEqual(str(Cita.Estado.NO_ASISTIO.label), "No asistió")

    def _plantillas_enviadas(self):
        return [c.args[0] for c in self.wa.call_args_list if c.args[0]["type"] == "template"]

    def test_oferta_whatsapp_en_el_idioma_de_la_clienta(self):
        import re
        Clienta.objects.filter(pk=self.A.clientas[1].pk).update(idioma="en")
        cita = self._cita()
        self._espera(self.A.clientas[1])
        services.cambiar_estado(cita, Cita.Estado.CANCELADA)
        env = self._plantillas_enviadas()[-1]
        self.assertEqual(env["template"]["language"]["code"], "en")
        fecha = env["template"]["components"][0]["parameters"][2]["text"]
        self.assertRegex(fecha, r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ")

        # y una clienta en español recibe la plantilla 'es' con día en español
        cita2 = self._cita(inicio=manana(15), clienta=self.A.clientas[0])
        self._espera(self.A.clientas[2], desde=14, hasta=18)
        services.cambiar_estado(cita2, Cita.Estado.CANCELADA)
        env2 = self._plantillas_enviadas()[-1]
        self.assertEqual(env2["template"]["language"]["code"], "es")
        self.assertRegex(env2["template"]["components"][0]["parameters"][2]["text"], r"^(lun|mar|mié|jue|vie|sáb|dom) ")

    def test_respuesta_whatsapp_en_el_idioma_de_la_clienta(self):
        Clienta.objects.filter(pk=self.A.clientas[1].pk).update(idioma="en")
        c_en = self._cita(clienta=self.A.clientas[1])
        c_es = self._cita(clienta=self.A.clientas[0], inicio=manana(13))
        for cita, clienta in ((c_en, self.A.clientas[1]), (c_es, self.A.clientas[0])):
            body = self._evento_boton(clienta.telefono_whatsapp, f"cita:{cita.id}:confirmar")
            APIClient().post("/api/webhooks/whatsapp/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=self._firmar(body))
        textos = [c.args[0]["text"]["body"] for c in self.wa.call_args_list if c.args[0]["type"] == "text"]
        self.assertEqual(textos, ["Done! Your appointment is confirmed ✅", "¡Listo! Tu cita quedó confirmada ✅"])

    # ---------- Borrado seguro ----------
    def test_no_se_puede_borrar_lo_que_tiene_citas(self):
        self._cita()
        c = cliente_de(self.A.recep)
        self.assertEqual(c.delete(f"/api/cabinas/{self.A.cab1.id}/").status_code, 409)
        self.assertEqual(c.delete(f"/api/profesionales/{self.A.prof1.id}/").status_code, 409)
        self.assertEqual(c.delete(f"/api/servicios/{self.A.serv.id}/").status_code, 409)
        self.assertEqual(c.delete(f"/api/clientas/{self.A.clientas[0].id}/").status_code, 409)
        self.assertEqual(c.delete(f"/api/cabinas/{self.A.cab2.id}/").status_code, 204)  # sin citas: sí se borra
