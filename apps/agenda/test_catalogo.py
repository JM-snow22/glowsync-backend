from rest_framework.test import APITestCase

from apps.core.models import Usuario
from apps.core.tests import cliente, crear_centro, crear_usuario

from .models import Cabina, Profesional, Servicio


class CatalogoTest(APITestCase):
    def setUp(self):
        self.A, self.B = crear_centro("A"), crear_centro("B")
        self.admin = crear_usuario("admin@x.co", Usuario.Rol.ADMIN_SAAS)
        self.recA = crear_usuario("reca@x.co", Usuario.Rol.RECEPCIONISTA, self.A)
        self.recB = crear_usuario("recb@x.co", Usuario.Rol.RECEPCIONISTA, self.B)
        self.estA = crear_usuario("esta@x.co", Usuario.Rol.ESTETICISTA, self.A)
        self.cabB = Cabina.objects.create(centro=self.B, nombre="Sala B")
        self.profB = Profesional.objects.create(centro=self.B, nombre="Prof B")
        self.profA = Profesional.objects.create(centro=self.A, nombre="Prof A")

    # ---------- crear y centro automático ----------
    def test_crear_cabina_servicio_y_profesional(self):
        c = cliente(self.recA)
        r = c.post("/api/cabinas/", {"nombre": "Cabina 1"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Cabina.objects.get(pk=r.data["id"]).centro_id, self.A.id)

        r = c.post("/api/servicios/", {"nombre": "Limpieza facial", "duracion_minutos": 60, "precio": "90000"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["porcentaje_sena"], 30)  # valor por defecto

        r = c.post("/api/profesionales/", {"nombre": "Daniela", "telefono": "573001112233"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    # ---------- aislamiento entre centros ----------
    def test_cada_centro_ve_solo_su_catalogo(self):
        nombres = [x["nombre"] for x in cliente(self.recA).get("/api/profesionales/").data["results"]]
        self.assertEqual(nombres, ["Prof A"])
        self.assertEqual(cliente(self.recA).get("/api/cabinas/").data["count"], 0)

    def test_no_puede_leer_ni_modificar_el_catalogo_de_otro_centro(self):
        c = cliente(self.recA)
        self.assertEqual(c.get(f"/api/cabinas/{self.cabB.id}/").status_code, 404)
        self.assertEqual(c.patch(f"/api/cabinas/{self.cabB.id}/", {"nombre": "x"}, format="json").status_code, 404)
        self.assertEqual(c.delete(f"/api/profesionales/{self.profB.id}/").status_code, 404)
        self.assertTrue(Profesional.objects.filter(pk=self.profB.pk).exists())

    def test_no_puede_crear_turnos_ni_bloqueos_para_profesionales_de_otro_centro(self):
        c = cliente(self.recA)
        turno = {"profesional": self.profB.id, "dia_semana": 0, "hora_desde": "08:00", "hora_hasta": "12:00"}
        self.assertEqual(c.post("/api/disponibilidades/", turno, format="json").status_code, 400)
        bloqueo = {"profesional": self.profB.id, "inicio": "2030-01-01T08:00:00Z", "fin": "2030-01-01T10:00:00Z"}
        self.assertEqual(c.post("/api/bloqueos/", bloqueo, format="json").status_code, 400)

    def test_los_turnos_de_otro_centro_no_aparecen(self):
        cliente(self.recB).post("/api/disponibilidades/", {"profesional": self.profB.id, "dia_semana": 1, "hora_desde": "08:00", "hora_hasta": "12:00"}, format="json")
        self.assertEqual(cliente(self.recA).get("/api/disponibilidades/").data["count"], 0)
        self.assertEqual(cliente(self.recB).get("/api/disponibilidades/").data["count"], 1)

    # ---------- roles ----------
    def test_esteticista_consulta_pero_no_modifica(self):
        c = cliente(self.estA)
        self.assertEqual(c.get("/api/profesionales/").status_code, 200)
        self.assertEqual(c.post("/api/cabinas/", {"nombre": "X"}, format="json").status_code, 403)
        self.assertEqual(c.delete(f"/api/profesionales/{self.profA.id}/").status_code, 403)

    def test_admin_saas_no_usa_el_catalogo_de_un_centro(self):
        self.assertEqual(cliente(self.admin).get("/api/cabinas/").status_code, 403)

    # ---------- validaciones ----------
    def test_nombre_de_cabina_repetido_da_400_y_en_otro_centro_si_se_permite(self):
        c = cliente(self.recA)
        self.assertEqual(c.post("/api/cabinas/", {"nombre": "Sala 1"}, format="json").status_code, 201)
        r = c.post("/api/cabinas/", {"nombre": "sala 1"}, format="json")  # mayúsculas distintas
        self.assertEqual(r.status_code, 400)
        self.assertIn("Ya existe", str(r.data["nombre"]))
        self.assertEqual(cliente(self.recB).post("/api/cabinas/", {"nombre": "Sala 1"}, format="json").status_code, 201)

    def test_editar_una_cabina_con_su_propio_nombre_no_da_error(self):
        c = cliente(self.recA)
        id_ = c.post("/api/cabinas/", {"nombre": "Sala 1"}, format="json").data["id"]
        r = c.patch(f"/api/cabinas/{id_}/", {"nombre": "Sala 1", "activa": False}, format="json")
        self.assertEqual((r.status_code, r.data["activa"]), (200, False))

    def test_validaciones_de_servicio(self):
        c = cliente(self.recA)
        base = {"nombre": "S", "duracion_minutos": 60, "precio": "1000"}
        self.assertEqual(c.post("/api/servicios/", {**base, "duracion_minutos": 3}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/servicios/", {**base, "precio": "-5"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/servicios/", {**base, "porcentaje_sena": 150}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/servicios/", {**base, "porcentaje_sena": 100}, format="json").status_code, 201)

    def test_validaciones_de_turnos(self):
        c = cliente(self.recA)
        base = {"profesional": self.profA.id, "dia_semana": 0, "hora_desde": "08:00", "hora_hasta": "12:00"}
        self.assertEqual(c.post("/api/disponibilidades/", {**base, "hora_hasta": "07:00"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/disponibilidades/", {**base, "hora_hasta": "08:00"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/disponibilidades/", {**base, "dia_semana": 7}, format="json").status_code, 400)
        r = c.post("/api/disponibilidades/", base, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        # PATCH parcial: solo cambia una hora y se valida contra la otra, sin romperse
        id_ = r.data["id"]
        self.assertEqual(c.patch(f"/api/disponibilidades/{id_}/", {"hora_hasta": "18:00"}, format="json").status_code, 200)
        self.assertEqual(c.patch(f"/api/disponibilidades/{id_}/", {"hora_hasta": "07:00"}, format="json").status_code, 400)

    def test_bloqueos(self):
        c = cliente(self.recA)
        malo = {"inicio": "2030-01-01T10:00:00Z", "fin": "2030-01-01T08:00:00Z", "motivo": "x"}
        self.assertEqual(c.post("/api/bloqueos/", malo, format="json").status_code, 400)
        general = {"inicio": "2030-01-01T08:00:00Z", "fin": "2030-01-01T10:00:00Z", "motivo": "Festivo"}
        r = c.post("/api/bloqueos/", general, format="json")  # sin profesional: bloquea a todo el centro
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(r.data["profesional"])
        personal = {**general, "profesional": self.profA.id, "motivo": "Vacaciones"}
        self.assertEqual(c.post("/api/bloqueos/", personal, format="json").status_code, 201)
        id_ = r.data["id"]
        self.assertEqual(c.patch(f"/api/bloqueos/{id_}/", {"fin": "2029-12-31T00:00:00Z"}, format="json").status_code, 400)

    def test_filtros(self):
        c = cliente(self.recA)
        c.post("/api/cabinas/", {"nombre": "Activa", "activa": True}, format="json")
        c.post("/api/cabinas/", {"nombre": "Inactiva", "activa": False}, format="json")
        self.assertEqual([x["nombre"] for x in c.get("/api/cabinas/?activa=true").data["results"]], ["Activa"])
        self.assertEqual(c.get("/api/cabinas/").data["count"], 2)

    def test_el_error_respeta_el_idioma_pedido(self):
        c = cliente(self.recA)
        c.post("/api/cabinas/", {"nombre": "Sala 1"}, format="json")
        r = c.post("/api/cabinas/", {"nombre": "Sala 1"}, format="json", HTTP_ACCEPT_LANGUAGE="en")
        self.assertEqual((r.status_code, r["Content-Language"]), (400, "en"))  # el texto en inglés llega en el paso 14