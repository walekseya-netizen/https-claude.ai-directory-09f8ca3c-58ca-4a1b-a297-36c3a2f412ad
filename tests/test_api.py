"""Тесты HTTP-слоя сервиса."""

from __future__ import annotations

from urllib.parse import unquote

from tests.conftest import create_act, header_payload, ks2_payload

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_read_act(client):
    act = create_act(client)

    assert act["form"] == "KS-2"
    assert act["okud"] == "0322005"
    assert act["totals"]["net"] == "1400174.83"
    assert act["totals"]["vat"] == "280034.97"
    assert act["totals"]["gross"] == "1680209.80"

    stored = client.get(f"/api/v1/ks2/{act['id']}")
    assert stored.status_code == 200
    assert stored.json() == act


def test_preview_does_not_persist(client):
    response = client.post("/api/v1/ks2/preview", json=ks2_payload())

    assert response.status_code == 200
    assert client.get("/api/v1/ks2").json() == []


def test_act_validation_errors(client):
    payload = ks2_payload(items=[])
    assert client.post("/api/v1/ks2", json=payload).status_code == 422

    payload = ks2_payload()
    payload["items"][0]["quantity"] = "-5"
    assert client.post("/api/v1/ks2", json=payload).status_code == 422

    payload = ks2_payload(period={"start": "2026-03-31", "end": "2026-03-01"})
    assert client.post("/api/v1/ks2", json=payload).status_code == 422


def test_list_acts_filters_by_contract_and_period(client):
    create_act(client)
    create_act(
        client,
        document_number="2",
        document_date="2026-04-30",
        period={"start": "2026-04-01", "end": "2026-04-30"},
        header=header_payload(contract={"number": "СМР-99/2026", "date": "2026-02-01"}),
    )

    assert len(client.get("/api/v1/ks2").json()) == 2
    assert len(client.get("/api/v1/ks2", params={"contract_number": "СМР-15/2026"}).json()) == 1
    assert len(client.get("/api/v1/ks2", params={"period_from": "2026-04-01"}).json()) == 1
    assert len(client.get("/api/v1/ks2", params={"period_to": "2026-03-31"}).json()) == 1


def test_delete_act(client):
    act = create_act(client)

    assert client.delete(f"/api/v1/ks2/{act['id']}").status_code == 204
    assert client.get(f"/api/v1/ks2/{act['id']}").status_code == 404
    assert client.delete(f"/api/v1/ks2/{act['id']}").status_code == 404


def test_download_act_xlsx(client):
    act = create_act(client)

    response = client.get(f"/api/v1/ks2/{act['id']}/xlsx")

    assert response.status_code == 200
    assert response.headers["content-type"] == XLSX_MEDIA_TYPE
    assert "КС-2 № 1 от 31.03.2026.xlsx" in unquote(response.headers["content-disposition"])
    assert response.content.startswith(b"PK")


def test_preview_act_xlsx_without_saving(client):
    response = client.post("/api/v1/ks2/preview/xlsx", json=ks2_payload())

    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert client.get("/api/v1/ks2").json() == []


def test_certificate_from_acts_endpoint(client):
    first = create_act(client)
    second = create_act(
        client,
        document_number="2",
        document_date="2026-04-30",
        period={"start": "2026-04-01", "end": "2026-04-30"},
    )

    response = client.post(
        "/api/v1/ks3/from-acts",
        json={
            "act_ids": [first["id"], second["id"]],
            "document_number": "1",
            "document_date": "2026-04-30",
        },
    )

    assert response.status_code == 201
    certificate = response.json()
    assert certificate["form"] == "KS-3"
    assert certificate["okud"] == "0322001"
    assert certificate["period"] == {"start": "2026-03-01", "end": "2026-04-30"}
    assert certificate["rows"][0]["name"] == "Корпус 1"
    assert certificate["totals"]["net"] == "2800349.66"
    assert certificate["act_ids"] == [first["id"], second["id"]]

    download = client.get(f"/api/v1/ks3/{certificate['id']}/xlsx")
    assert download.status_code == 200
    assert "КС-3 № 1 от 30.04.2026.xlsx" in unquote(download.headers["content-disposition"])


def test_certificate_chain_uses_previous_certificate(client):
    march = create_act(client)
    first = client.post(
        "/api/v1/ks3/from-acts",
        json={"act_ids": [march["id"]], "document_number": "1", "document_date": "2026-03-31"},
    ).json()

    april = create_act(
        client,
        document_number="2",
        document_date="2026-04-30",
        period={"start": "2026-04-01", "end": "2026-04-30"},
    )
    second = client.post(
        "/api/v1/ks3/from-acts",
        json={
            "act_ids": [april["id"]],
            "document_number": "2",
            "document_date": "2026-04-30",
            "previous_certificate_id": first["id"],
        },
    ).json()

    row = second["rows"][0]
    assert row["cost_for_period"] == "1400174.83"
    assert row["cost_from_year_start"] == "2800349.66"
    assert row["cost_from_start"] == "2800349.66"


def test_certificate_from_unknown_act_returns_404(client):
    response = client.post(
        "/api/v1/ks3/from-acts",
        json={"act_ids": ["missing"], "document_number": "1", "document_date": "2026-03-31"},
    )

    assert response.status_code == 404
    assert "не найден" in response.json()["detail"]


def test_certificate_from_incompatible_acts_returns_422(client):
    first = create_act(client)
    second = create_act(
        client,
        document_number="2",
        header=header_payload(contract={"number": "СМР-99/2026", "date": "2026-02-01"}),
    )

    response = client.post(
        "/api/v1/ks3/from-acts",
        json={
            "act_ids": [first["id"], second["id"]],
            "document_number": "1",
            "document_date": "2026-03-31",
        },
    )

    assert response.status_code == 422
    assert "разным договорам" in response.json()["detail"]


def test_manual_certificate(client):
    response = client.post(
        "/api/v1/ks3",
        json={
            "header": header_payload(),
            "document_number": "7",
            "document_date": "2026-05-31",
            "period": {"start": "2026-05-01", "end": "2026-05-31"},
            "rows": [
                {
                    "name": "Строительно-монтажные работы",
                    "code": "01",
                    "cost_from_start": "3000000",
                    "cost_from_year_start": "1500000",
                    "cost_for_period": "500000",
                }
            ],
        },
    )

    assert response.status_code == 201
    certificate = response.json()
    assert certificate["totals"]["net"] == "500000.00"
    assert certificate["totals_from_start"]["gross"] == "3600000.00"
    assert certificate["totals_from_year_start"]["net"] == "1500000.00"


def test_manual_certificate_rejects_inconsistent_row(client):
    response = client.post(
        "/api/v1/ks3",
        json={
            "header": header_payload(),
            "document_number": "7",
            "document_date": "2026-05-31",
            "period": {"start": "2026-05-01", "end": "2026-05-31"},
            "rows": [
                {
                    "name": "Строительно-монтажные работы",
                    "cost_from_start": "100",
                    "cost_from_year_start": "100",
                    "cost_for_period": "200",
                }
            ],
        },
    )

    assert response.status_code == 422


def test_openapi_is_available(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/ks2" in response.json()["paths"]
    assert "/api/v1/ks3/from-acts" in response.json()["paths"]
