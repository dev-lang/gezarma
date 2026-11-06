"""Regresión de la revisión de integridad de datos (CONTEXTO.md, sección 5.2)."""
import threading
import time
import uuid
from datetime import timedelta

import pytest

from backend.app import database, models
from backend.app.services import sla, ticket_service
from backend.app.timeutils import now_local
from test_stock import _presupuesto, _stock, make_part  # noqa: F401  (fixture)


# ── N° de RMA ────────────────────────────────────────────────────────────────
def test_rma_sin_repetidos_con_altas_simultaneas(client):
    resultados, errores = [], []

    def alta():
        db = database.SessionLocal()
        try:
            n = ticket_service.generate_rma_number(db, "cliente", year=2098)
            time.sleep(0.2)            # la transacción queda abierta: la otra tiene que esperar
            db.commit()
            resultados.append(n)
        except Exception as e:         # pragma: no cover - lo que se quiere evitar
            errores.append(repr(e))
        finally:
            db.close()

    hilos = [threading.Thread(target=alta) for _ in range(6)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert errores == []
    assert sorted(resultados) == [f"RMA-2098-CLAA{i:03d}" for i in range(1, 7)]


def test_rma_pasa_de_serie_despues_del_999(client):
    db = database.SessionLocal()
    try:
        db.add(models.RmaCounter(year=2097, rol_prefix="CL", serie="AB", last_seq=999))
        db.commit()
        assert ticket_service.generate_rma_number(db, "cliente", year=2097) == "RMA-2097-CLAC001"
        assert ticket_service.generate_rma_number(db, "cliente", year=2097) == "RMA-2097-CLAC002"
        db.commit()
    finally:
        db.close()


# ── Stock ────────────────────────────────────────────────────────────────────
def _movs(client, admin, part_id):
    return client.get(f"/stock/history?repuesto_id={part_id}", headers=admin).json()


def test_anular_un_consumo_corrige_el_ticket_y_no_desfasa(client, admin, make_part, make_user, make_ticket):
    """El caso de la revisión: stock 10, consumo 3, borrar el movimiento y quitar el repuesto → quedaba 13."""
    p = make_part(stock=10)
    cli, _ = make_user()
    t = make_ticket(cli)
    client.post(f"/tickets/{t['id']}/parts", headers=admin, json={"part_id": p["id"], "cantidad": 3})
    assert _stock(client, admin, p["id"]) == 7
    consumo = _movs(client, admin, p["id"])[0]
    r = client.delete(f"/stock/history/{consumo['id']}", headers=admin)        # el endpoint viejo ahora anula
    assert r.status_code == 200 and r.json()["tipo"] == "anulacion" and r.json()["anula_id"] == consumo["id"]
    assert _stock(client, admin, p["id"]) == 10
    assert client.get(f"/tickets/{t['id']}", headers=admin).json()["repuestos_usados"] == []
    assert client.delete(f"/tickets/{t['id']}/parts/{p['id']}", headers=admin).status_code == 404
    assert _stock(client, admin, p["id"]) == 10
    movs = _movs(client, admin, p["id"])
    assert any(m["id"] == consumo["id"] and m["anulado"] for m in movs)        # queda el registro, marcado
    assert client.post(f"/stock/history/{consumo['id']}/anular", headers=admin).status_code == 400   # una sola vez
    assert client.post(f"/stock/history/{r.json()['id']}/anular", headers=admin).status_code == 400  # ni la anulación


def test_movimientos_de_ticket_que_no_son_consumo_se_corrigen_desde_el_ticket(client, admin, make_part, make_user, make_ticket):
    p = make_part(stock=10)
    cli, _ = make_user()
    t = make_ticket(cli)
    client.post(f"/tickets/{t['id']}/parts", headers=admin, json={"part_id": p["id"], "cantidad": 2})
    client.patch(f"/tickets/{t['id']}/parts/{p['id']}", headers=admin, json={"cantidad": 4})
    ajuste = _movs(client, admin, p["id"])[0]
    assert ajuste["tipo"] == "ajuste"
    r = client.post(f"/stock/history/{ajuste['id']}/anular", headers=admin)
    assert r.status_code == 400 and "desde el ticket" in r.json()["detail"]


def test_anular_una_recepcion_de_pedido_reabre_el_pedido(client, admin, make_part):
    p = make_part(stock=0, minimo=2)
    ped = client.post("/pedidos/", headers=admin, json={"proveedor": "Prov", "items": [{"repuesto_id": p["id"], "cantidad": 5}]}).json()
    client.post(f"/pedidos/{ped['id']}/enviar", headers=admin, json={})
    item = ped["items"][0]["id"]
    ped = client.post(f"/pedidos/{ped['id']}/recibir", headers=admin, json={"items": [{"item_id": item, "cantidad": 5}]}).json()
    assert ped["estado"] == "recibido" and _stock(client, admin, p["id"]) == 5
    recepcion = _movs(client, admin, p["id"])[0]
    assert client.post(f"/stock/history/{recepcion['id']}/anular", headers=admin).status_code == 200
    ped = client.get(f"/pedidos/{ped['id']}", headers=admin).json()
    assert ped["estado"] == "enviado" and ped["items"][0]["recibido"] == 0 and _stock(client, admin, p["id"]) == 0


def test_cambio_de_stock_a_mano_queda_en_el_historial(client, admin, make_part):
    p = make_part(stock=5)
    body = {k: p[k] for k in ("nombre", "codigo", "proveedor", "precio", "categoria", "stock_minimo")}
    client.put(f"/parts/{p['id']}", headers=admin, json={**body, "stock": 12})
    m = _movs(client, admin, p["id"])[0]
    assert (m["tipo"], m["cantidad"], m["stock_anterior"], m["stock_nuevo"]) == ("ajuste", 7, 5, 12)


def test_stock_insuficiente_no_toca_nada(client, admin, make_part, make_user, make_ticket):
    p = make_part(stock=2)
    cli, _ = make_user()
    t = make_ticket(cli)
    r = client.post(f"/tickets/{t['id']}/parts", headers=admin, json={"part_id": p["id"], "cantidad": 3})
    assert r.status_code == 400 and "disponible: 2" in r.json()["detail"]
    assert _stock(client, admin, p["id"]) == 2 and client.get(f"/tickets/{t['id']}", headers=admin).json()["repuestos_usados"] == []


def test_presupuesto_no_descuenta_dos_veces_lo_ya_cargado(client, admin, make_part, make_user, make_ticket):
    p = make_part(stock=10)
    tec, _ = make_user("tecnico")
    cli, _ = make_user()
    t = make_ticket(cli)
    client.post(f"/tickets/{t['id']}/parts", headers=tec, json={"part_id": p["id"], "cantidad": 1})   # a mano, al diagnosticar
    _presupuesto(client, tec, t["id"], [{"repuesto_id": p["id"], "cantidad": 3, "costo_interno": 1, "precio_cliente": 2}])
    client.patch(f"/budget/tickets/{t['id']}/presupuesto/estado", headers=cli, json={"estado": "aprobado"})
    assert _stock(client, admin, p["id"]) == 7                      # 3 en total, no 1 + 3
    usados = client.get(f"/tickets/{t['id']}", headers=tec).json()["repuestos_usados"]
    assert [(u["id"], u["cantidad"]) for u in usados] == [(p["id"], 3)]


# ── Estados ──────────────────────────────────────────────────────────────────
@pytest.fixture
def estado_entregado(client, admin):
    valor = f"Entregado {uuid.uuid4().hex[:4]}"
    r = client.post("/config/estados", headers=admin, json={"valor": valor, "etiqueta": "Entregado", "color": "#16a34a",
                                                            "orden": 20, "activo": True, "es_final": True})
    assert r.status_code == 200, r.text
    return r.json()


def test_estado_configurable_se_puede_usar_y_cierra(client, admin, make_user, make_ticket, estado_entregado):
    cli, _ = make_user()
    t = make_ticket(cli)
    r = client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": estado_entregado["valor"]})
    assert r.status_code == 200 and r.json()["fecha_cierre"]               # es_final → cierra
    r = client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "En reparación"})
    assert r.json()["fecha_cierre"] is None                                # reabierto
    body = {**estado_entregado, "activo": False}
    body.pop("id")
    client.patch(f"/config/estados/{estado_entregado['id']}", headers=admin, json=body)
    assert client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": estado_entregado["valor"]}).status_code == 400
    assert client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Inventado"}).status_code == 400


def test_valor_de_estados_protegido(client, admin, make_user, make_ticket, estado_entregado):
    estados = client.get("/config/estados", headers=admin).json()
    reparado = next(e for e in estados if e["valor"] == "Reparado")
    body = {k: reparado[k] for k in ("valor", "etiqueta", "color", "orden", "activo", "es_final")}
    assert client.patch(f"/config/estados/{reparado['id']}", headers=admin, json={**body, "valor": "Listo"}).status_code == 400
    r = client.patch(f"/config/estados/{reparado['id']}", headers=admin, json={**body, "etiqueta": "Listo para retirar"})
    assert r.status_code == 200                                            # la etiqueta sí
    client.patch(f"/config/estados/{reparado['id']}", headers=admin, json=body)
    assert client.delete(f"/config/estados/{reparado['id']}", headers=admin).status_code == 400
    # Uno propio en uso no cambia de valor
    cli, _ = make_user()
    t = make_ticket(cli)
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": estado_entregado["valor"]})
    body = {k: estado_entregado[k] for k in ("valor", "etiqueta", "color", "orden", "activo", "es_final")}
    assert client.patch(f"/config/estados/{estado_entregado['id']}", headers=admin,
                        json={**body, "valor": body["valor"] + "x"}).status_code == 400


def test_dashboard_no_cuenta_cancelados_como_abiertos(client, admin, make_user, make_ticket):
    antes = client.get("/tickets/stats/dashboard", headers=admin).json()
    cli, _ = make_user()
    t = make_ticket(cli)
    client.put(f"/tickets/{t['id']}/status", headers=admin, json={"estado": "Cancelado"})
    d = client.get("/tickets/stats/dashboard", headers=admin).json()
    assert d["total_tickets"] == antes["total_tickets"] + 1
    assert d["abiertos"] == antes["abiertos"] and d["cerrados"] == antes["cerrados"]


# ── Clonar y garantía ────────────────────────────────────────────────────────
def test_clonar_pasa_por_el_alta_normal(client, admin, make_user, make_ticket):
    cli, _ = make_user()
    t = make_ticket(cli, serie="CLON-1")
    c = client.post(f"/tickets/{t['id']}/clone", headers=admin, json={"relacionar": True}).json()
    assert c["deadline_sla"] and c["usuario_id"] == t["usuario_id"] and c["clonado_de"] == t["id"]
    assert c["numero_rma"].split("-")[2].startswith("CL") and c["ticket_relacionado"] == t["id"]
    hist = client.get(f"/tickets/{c['id']}/history", headers=admin).json()
    assert any("clon de" in (h["detalle"] or "") for h in hist)
    assert t["id"] in [x["id"] for x in client.get("/tickets/", headers=cli).json()]


@pytest.mark.parametrize("meses,hace_meses,esperado", [(36, 24, True), (6, 8, False), (12, 11, True)])
def test_garantia_segun_el_producto(client, admin, make_user, meses, hace_meses, esperado):
    prod = client.post("/products/", headers=admin, json={"marca": "M", "modelo": f"G-{uuid.uuid4().hex[:5]}",
                                                         "categoria": "X", "periodo_garantia_meses": meses}).json()
    cli, _ = make_user()
    compra = ticket_service.sumar_meses(now_local(), -hace_meses).replace(hour=0, minute=0, second=0, microsecond=0)
    t = client.post("/tickets/", headers=cli, json={"producto_id": prod["id"], "producto": "M", "numero_serie": "G",
                                                     "fecha_compra": compra.isoformat(), "descripcion": "x"}).json()
    assert t["en_garantia"] is esperado


def test_sumar_meses_fin_de_mes():
    from datetime import datetime
    assert ticket_service.sumar_meses(datetime(2026, 1, 31), 1) == datetime(2026, 2, 28)
    assert ticket_service.sumar_meses(datetime(2028, 1, 31), 1) == datetime(2028, 2, 29)
    assert ticket_service.sumar_meses(datetime(2026, 11, 15), 14) == datetime(2028, 1, 15)


# ── Entradas validadas ───────────────────────────────────────────────────────
def test_diagnostico_y_cantidades_validados(client, admin, make_part, make_user, make_ticket):
    p = make_part(stock=10)
    cli, _ = make_user()
    t = make_ticket(cli)
    client.put(f"/tickets/{t['id']}/diagnostic", headers=admin, json={"diagnostico": "Fuente quemada"})
    assert client.put(f"/tickets/{t['id']}/diagnostic", headers=admin, json={}).status_code == 422
    assert client.get(f"/tickets/{t['id']}", headers=admin).json()["diagnostico"] == "Fuente quemada"   # no se borró
    client.post(f"/tickets/{t['id']}/parts", headers=admin, json={"part_id": p["id"], "cantidad": 1})
    for malo in ({"cantidad": "x"}, {"cantidad": 0}, {}):
        assert client.patch(f"/tickets/{t['id']}/parts/{p['id']}", headers=admin, json=malo).status_code == 422


def test_si_una_tarea_periodica_falla_las_otras_corren(client, monkeypatch):
    from backend.app.services import retiro
    llamadas = []
    monkeypatch.setattr(sla, "revisar", lambda db: (_ for _ in ()).throw(RuntimeError("falla")))
    monkeypatch.setattr(retiro, "revisar", lambda db: llamadas.append("retiro") or 0)
    assert sla._una_vuelta() >= 1
    assert llamadas == ["retiro"]
