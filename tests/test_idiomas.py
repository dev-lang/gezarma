"""Idiomas: diccionarios, errores de la API, idioma por usuario, mails y documentos."""
import json
import re
import uuid
from pathlib import Path

import pytest

from backend.app import idiomas
from backend.app.services import email
from test_email import smtp  # noqa: F401  (fixture)

DIR = Path(idiomas.__file__).resolve().parent / "traducciones"


@pytest.mark.parametrize("codigo", ["en", "pt-BR", "es-ES"])
def test_diccionarios_validos(codigo):
    d = json.loads((DIR / f"{codigo}.json").read_text(encoding="utf-8"))
    assert len(d) > (200 if codigo == "es-ES" else 1000)
    for k, v in d.items():
        assert sorted(re.findall(r"\{\d+\}", k)) == sorted(re.findall(r"\{\d+\}", v)), k
    idiomas.diccionario(codigo)   # compila sin errores


def test_traduccion_exacta_patrones_y_partes():
    assert idiomas.tr("  Cancelar ", "en") == "  Cancel "
    assert idiomas.tr("Hace 3 días", "es-AR") == "Hace 3 días"                    # el base no cambia
    assert idiomas.tr("Te asignaron el RMA-2026-X", "en") != "Te asignaron el RMA-2026-X"
    assert idiomas.tr("Ingresó el 3/11 · en garantía", "pt-BR") == "Entrada em 3/11 · na garantia"
    assert idiomas.tr("Ingresó el 3/11 · en garantía", "en") == "Checked in on 3/11 · under warranty"
    # Lo que no está en el diccionario queda igual
    assert idiomas.tr("Placa de video", "en") == "Placa de video"
    # Un patrón con poco texto propio no se usa ("{0} de {1}" agarraría cualquier cosa)
    assert not idiomas._patron_valido("{0} de {1}") and idiomas._patron_valido("Rol: {0}")
    assert idiomas.normalizar("en-US") == "en" and idiomas.normalizar("pt") == "pt-BR"
    assert idiomas.normalizar("es-MX") == "es-AR" and idiomas.normalizar("fr") is None
    assert idiomas.desde_header("fr-FR,pt;q=0.8") == "pt-BR"


def test_errores_de_la_api_en_el_idioma_pedido(client, make_user):
    h, _ = make_user()
    cuerpo = {"current_password": "mal", "new_password": "otra123"}
    es = client.post("/users/change-password", headers=h, json=cuerpo).json()["detail"]
    en = client.post("/users/change-password", headers={**h, "Accept-Language": "en-US,en;q=0.9"}, json=cuerpo).json()["detail"]
    pt = client.post("/users/change-password", headers={**h, "Accept-Language": "pt-BR"}, json=cuerpo).json()["detail"]
    assert es == "La contraseña actual es incorrecta"
    assert en != es and pt != es and en != pt


def test_idioma_de_la_cuenta(client):
    nombre = f"idi_{uuid.uuid4().hex[:6]}"
    r = client.post("/register", json={"username": nombre, "nombre": "Ann", "email": f"{nombre}@t.com",
                                       "password": "secret1", "idioma": "en-GB"})
    assert r.json()["idioma"] == "en"
    login = client.post("/login", data={"username": nombre, "password": "secret1"}).json()
    assert login["idioma"] == "en"
    h = {"Authorization": "Bearer " + login["access_token"]}
    assert client.put("/users/me/idioma", headers=h, json={"idioma": "pt-BR"}).json() == {"idioma": "pt-BR"}
    assert client.put("/users/me/idioma", headers=h, json={"idioma": "klingon"}).status_code == 400
    assert client.put("/users/me/idioma", headers=h, json={"idioma": None}).json() == {"idioma": None}


def test_diccionario_para_el_navegador(client):
    r = client.get("/i18n/pt-BR.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.text.startswith('window.I18N_IDIOMA="pt-BR";window.I18N_DICT={')
    assert client.get("/i18n/es-AR.js").text.endswith("window.I18N_DICT={};\n")
    assert [i["codigo"] for i in client.get("/i18n/idiomas").json()] == ["es-AR", "es-ES", "en", "pt-BR"]


def _cliente_en(client, idioma):
    nombre = f"cli_{uuid.uuid4().hex[:6]}"
    mail = f"{nombre}@cliente.com"
    client.post("/register", json={"username": nombre, "nombre": "Ann Client", "email": mail,
                                   "password": "secret1", "idioma": idioma})
    h = {"Authorization": "Bearer " + client.post("/login", data={"username": nombre, "password": "secret1"}).json()["access_token"]}
    return h, mail


def test_mail_en_el_idioma_del_cliente(client, admin, smtp, make_ticket):  # noqa: F811
    h_en, mail_en = _cliente_en(client, "en")
    h_es, mail_es = _cliente_en(client, None)
    for h in (h_en, h_es):
        t = make_ticket(h)
        client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "En reparación"})
    email.esperar_envios()
    [en] = smtp.para(mail_en)
    [es] = smtp.para(mail_es)
    cuerpo_en = en.get_body(("plain",)).get_content()
    assert "Hi Ann Client," in cuerpo_en and "Hola" not in cuerpo_en
    assert "Hola Ann Client," in es.get_body(("plain",)).get_content()
    assert en["Subject"] != es["Subject"]


def test_documento_en_el_idioma_del_cliente(client, admin, make_ticket):
    h, _ = _cliente_en(client, "pt-BR")
    t = make_ticket(h, serie="DOC-PT")
    html = client.get(f"/tickets/{t['id']}/documentos/ingreso?formato=html", headers=admin).text
    assert "Comprovante de entrada" in html or "Entrada" in html
    assert "Orden de ingreso" not in html
    # La etiqueta (interna) sale en el idioma de quien la pide
    etq = client.get(f"/tickets/{t['id']}/documentos/etiqueta?formato=html", headers=admin).text
    assert t["numero_rma"] in etq
