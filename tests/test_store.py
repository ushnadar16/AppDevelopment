import base64
import threading

from app.store import receipt_pdf
from app.util import sign


def buy(c, oid, token="tok_success", code=None, variant="var-jersey-001-M", qty=1, cust="cust-001"):
    return c.post("/audit/v1/checkout", json={"order_id": oid, "customer_id": cust,
                                              "items": [{"variant_id": variant, "quantity": qty}],
                                              "discount_code": code, "payment": {"token": token}})


def test_checkout_success_and_receipt(client):
    r = buy(client, "ord-001")
    assert r.status_code == 201
    b = r.json()
    assert b["total_minor"] == 450000 and b["payment"]["state"] == "captured"
    assert b["receipt"]["signature"] == sign("ord-001", b["receipt"]["payload"])
    pdf = base64.b64decode(b["receipt"]["pdf_base64"])
    assert pdf.startswith(b"%PDF") and b"PKR 4500.00" in pdf and b"ord-001" in pdf
    assert buy(client, "ord-001").status_code == 200
    assert buy(client, "ord-001", qty=2).json()["error"]["code"] == "DUPLICATE_ORDER_ID"
    assert client.get("/audit/v1/inventory/var-jersey-001-M").json() == {"variant_id": "var-jersey-001-M",
                                                                       "stock": 0, "reserved": 0}
    assert buy(client, "ord-002").json()["error"]["code"] == "OUT_OF_STOCK"


def test_discount_and_failures(client):
    client.post("/audit/v1/reset", json={"stock": {"var-jersey-001-L": 3}})
    r = buy(client, "o1", code="WELCOME10", variant="var-jersey-001-L", qty=1).json()
    assert r["discount_minor"] == 45000 and r["total_minor"] == 405000
    assert buy(client, "o2", code="BOGUS", variant="var-jersey-001-L").json()["error"]["code"] == \
        "INVALID_DISCOUNT_CODE"
    assert buy(client, "o3", token="tok_declined", variant="var-jersey-001-L").status_code == 402
    assert buy(client, "o4", token="tok_capture_fail", variant="var-jersey-001-L").json()["error"]["code"] == \
        "PAYMENT_CAPTURE_FAILED"
    assert client.get("/audit/v1/inventory/var-jersey-001-L").json()["stock"] == 2
    assert buy(client, "o5", variant="nope").json()["error"]["code"] == "VARIANT_NOT_FOUND"
    assert client.get("/audit/v1/inventory/nope").status_code == 404
    assert buy(client, "o6", qty=11).status_code == 400
    assert buy(client, "o7", cust="<script>alert('x')</script> \"q\"", variant="var-jersey-001-L").status_code == 201


def test_concurrent_last_unit(client):
    client.post("/audit/v1/reset", json={"stock": {"var-jersey-001-M": 1}})
    barrier = threading.Barrier(20)
    codes = []

    def go(i):
        barrier.wait()
        codes.append(buy(client, f"burst-{i}").status_code)

    ts = [threading.Thread(target=go, args=(i,)) for i in range(20)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(codes) == [201] + [409] * 19
    assert client.get("/audit/v1/inventory/var-jersey-001-M").json() == {"variant_id": "var-jersey-001-M",
                                                                       "stock": 0, "reserved": 0}


def test_pdf_escaping():
    pdf = receipt_pdf({"order_id": "o(1)", "customer_id": "a\\b", "paid_at": "x", "items": [],
                       "subtotal_minor": 5, "discount_minor": 0, "total_minor": 5})
    assert b"o\\(1\\)" in pdf and b"PKR 0.05" in pdf
