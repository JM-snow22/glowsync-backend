from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .models import Centro, Usuario

CLAVE = "Clave12345!"


def crear_centro(nombre):
    return Centro.objects.create(nombre=nombre, fecha_vencimiento=timezone.localdate() + timedelta(days=30))


def crear_usuario(email, rol, centro=None):
    return Usuario.objects.create_user(email, CLAVE, nombre=email.split("@")[0], rol=rol, centro=centro)


def cliente(usuario, **extra):
    cache.clear()
    c = APIClient()
    r = c.post("/api/auth/login/", {"email": usuario.email, "password": CLAVE}, format="json")
    assert r.status_code == 200, r.content
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}", **extra)
    return c


class AuthYRolesTest(APITestCase):
    def setUp(self):
        self.A, self.B = crear_centro("A"), crear_centro("B")
        self.admin = crear_usuario("admin@x.co", Usuario.Rol.ADMIN_SAAS)
        self.recA = crear_usuario("reca@x.co", Usuario.Rol.RECEPCIONISTA, self.A)
        self.recB = crear_usuario("recb@x.co", Usuario.Rol.RECEPCIONISTA, self.B)
        self.estA = crear_usuario("esta@x.co", Usuario.Rol.ESTETICISTA, self.A)

    # ---------- login ----------
    def test_login_devuelve_tokens_y_el_token_lleva_rol_y_centro(self):
        r = APIClient().post("/api/auth/login/", {"email": "reca@x.co", "password": CLAVE}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["usuario"]["rol"], "RECEPCIONISTA")
        token = AccessToken(r.data["access"])
        self.assertEqual((token["rol"], token["centro_id"]), ("RECEPCIONISTA", self.A.id))

    def test_login_con_clave_incorrecta(self):
        r = APIClient().post("/api/auth/login/", {"email": "reca@x.co", "password": "mala"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_sin_token_no_hay_acceso(self):
        self.assertEqual(APIClient().get("/api/auth/me/").status_code, 401)
        self.assertEqual(APIClient().get("/api/usuarios/").status_code, 401)

    def test_refresh_entrega_un_nuevo_access(self):
        login = APIClient().post("/api/auth/login/", {"email": "reca@x.co", "password": CLAVE}, format="json")
        r = APIClient().post("/api/auth/refresh/", {"refresh": login.data["refresh"]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)

    def test_me(self):
        r = cliente(self.recA).get("/api/auth/me/")
        self.assertEqual((r.data["email"], r.data["centro"], r.data["rol"]), ("reca@x.co", "A", "RECEPCIONISTA"))

    # ---------- aislamiento entre centros ----------
    def test_recepcionista_solo_ve_usuarios_de_su_centro(self):
        emails = {u["email"] for u in cliente(self.recA).get("/api/usuarios/").data["results"]}
        self.assertEqual(emails, {"reca@x.co", "esta@x.co"})
        self.assertNotIn("recb@x.co", emails)

    def test_no_puede_tocar_usuarios_de_otro_centro(self):
        c = cliente(self.recA)
        self.assertEqual(c.get(f"/api/usuarios/{self.recB.id}/").status_code, 404)
        self.assertEqual(c.patch(f"/api/usuarios/{self.recB.id}/", {"nombre": "hack"}, format="json").status_code, 404)
        self.assertEqual(c.delete(f"/api/usuarios/{self.recB.id}/").status_code, 404)

    def test_el_usuario_creado_queda_en_el_centro_de_quien_lo_crea(self):
        c = cliente(self.recA)
        r = c.post("/api/usuarios/", {"email": "nueva@x.co", "nombre": "Nueva", "rol": "ESTETICISTA", "password": "Clave12345!", "centro": self.B.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Usuario.objects.get(email="nueva@x.co").centro_id, self.A.id)  # ignora el 'centro' del body

    # ---------- roles ----------
    def test_no_se_puede_crear_un_admin_saas_por_la_api(self):
        r = cliente(self.recA).post("/api/usuarios/", {"email": "x@x.co", "nombre": "X", "rol": "ADMIN_SAAS", "password": "Clave12345!"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_esteticista_no_administra_usuarios(self):
        c = cliente(self.estA)
        self.assertEqual(c.get("/api/usuarios/").status_code, 403)
        self.assertEqual(c.post("/api/usuarios/", {}, format="json").status_code, 403)

    def test_solo_el_admin_saas_gestiona_centros(self):
        self.assertEqual(cliente(self.recA).get("/api/centros/").status_code, 403)
        c = cliente(self.admin)
        self.assertEqual(c.get("/api/centros/").data["count"], 2)
        nuevo = c.post("/api/centros/", {"nombre": "C", "fecha_vencimiento": "2030-01-01"}, format="json")
        self.assertEqual(nuevo.status_code, 201, nuevo.content)

    def test_admin_saas_crea_el_primer_usuario_de_un_centro(self):
        r = cliente(self.admin).post(f"/api/centros/{self.B.id}/usuarios/", {
            "email": "primera@x.co", "nombre": "Primera", "rol": "RECEPCIONISTA", "password": "Clave12345!"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Usuario.objects.get(email="primera@x.co").centro_id, self.B.id)

    def test_admin_saas_no_usa_los_endpoints_de_un_centro(self):
        self.assertEqual(cliente(self.admin).get("/api/usuarios/").status_code, 403)

    def test_clave_debil_es_rechazada(self):
        r = cliente(self.recA).post("/api/usuarios/", {"email": "d@x.co", "nombre": "D", "rol": "ESTETICISTA","password": "12345678"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.data)

    # ---------- suscripción ----------
    def test_suscripcion_vencida_bloquea_login_y_tokens_ya_emitidos(self):
        c = cliente(self.recA)  # token válido emitido antes de vencer
        Centro.objects.filter(pk=self.A.pk).update(fecha_vencimiento=timezone.localdate() - timedelta(days=1))
        self.assertEqual(c.get("/api/usuarios/").status_code, 403)
        r = APIClient().post("/api/auth/login/", {"email": "reca@x.co", "password": CLAVE}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_suscripcion_suspendida_bloquea_el_acceso(self):
        c = cliente(self.recA)
        Centro.objects.filter(pk=self.A.pk).update(estado_suscripcion="SUSPENDIDA")
        self.assertEqual(c.get("/api/usuarios/").status_code, 403)

    # ---------- idioma ----------
    def test_cambiar_idioma_y_prioridad_de_la_cabecera(self):
        c = cliente(self.recA)
        self.assertEqual(c.patch("/api/auth/me/", {"idioma": "en"}, format="json").data["idioma"], "en")
        # sin cabecera: usa el idioma del perfil (inglés)
        r = c.post("/api/usuarios/", {"email": "d@x.co", "nombre": "D", "rol": "ESTETICISTA", "password": "12345678"}, format="json")
        self.assertEqual(r["Content-Language"], "en")
        # con cabecera explícita: manda la cabecera
        r = cliente(self.recA).post("/api/usuarios/", {}, format="json", HTTP_ACCEPT_LANGUAGE="es")
        self.assertEqual(r["Content-Language"], "es")

    def test_idioma_no_soportado(self):
        self.assertEqual(cliente(self.recA).patch("/api/auth/me/", {"idioma": "fr"}, format="json").status_code, 400)

    def test_login_se_limita_a_20_intentos_por_minuto(self):
        from django.core.cache import cache
        cache.clear()
        codigos = [APIClient().post("/api/auth/login/", {"email": "a@x.co", "password": "x"}, format="json").status_code
                for _ in range(22)]
        self.assertEqual(codigos[-1], 429)
        cache.clear()