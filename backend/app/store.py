"""FR-2.3 merchandise store: concurrency-safe reservation, mock payment gateway, signed PDF receipts."""
import base64
import threading
from datetime import datetime, timezone

from .util import ApiError, canonical, conflict, is_id, is_int, not_found, now_iso, sign, validation_error

DISCOUNTS = {"WELCOME10": 10}  # percent off subtotal
ORDER_TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"packed", "refunded", "cancelled"},
    "packed": {"shipped", "refunded"},
    "shipped": {"delivered"},
    "delivered": {"refunded"},
    "cancelled": set(),
    "refunded": set(),
}


class MockGateway:
    """Self-built mock payment gateway: authorize, capture, void, refund."""

    def __init__(self):
        self._lock = threading.Lock()
        self._n = 0

    def _next(self):
        with self._lock:
            self._n += 1
            return self._n

    def authorize(self, token, amount):
        if token == "tok_success" or token == "tok_capture_fail":
            return {"ok": True, "authorization_id": f"auth_{self._next()}"}
        return {"ok": False}

    def capture(self, token, authorization_id):
        if token == "tok_capture_fail":
            return {"ok": False}
        return {"ok": True, "capture_id": f"cap_{self._next()}"}

    def void(self, authorization_id):
        return {"ok": True}

    def refund(self, capture_id):
        return {"ok": True, "refund_id": f"ref_{self._next()}"}

    def reset(self):
        with self._lock:
            self._n = 0


def current_price(variant, at=None):
    price = variant["price_minor"]
    at = at or now_iso()
    for change in sorted(variant.get("price_schedule", []), key=lambda c: c["effective_at"]):
        if change["effective_at"] <= at:
            price = change["price_minor"]
    return price


def validate_checkout(body):
    if not isinstance(body, dict):
        raise validation_error("body")
    bad = []
    if not is_id(body.get("order_id")):
        bad.append("order_id")
    if not isinstance(body.get("customer_id"), str) or not body["customer_id"]:
        bad.append("customer_id")
    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        bad.append("items")
    else:
        seen = set()
        for it in items:
            if (not isinstance(it, dict) or not isinstance(it.get("variant_id"), str)
                    or not is_int(it.get("quantity")) or not 1 <= it["quantity"] <= 10 or it["variant_id"] in seen):
                bad.append("items")
                break
            seen.add(it["variant_id"])
    dc = body.get("discount_code")
    if dc is not None and not isinstance(dc, str):
        bad.append("discount_code")
    pay = body.get("payment")
    if not isinstance(pay, dict) or not isinstance(pay.get("token"), str):
        bad.append("payment")
    if bad:
        raise validation_error(bad)
    return {"order_id": body["order_id"], "customer_id": body["customer_id"],
            "items": [{"variant_id": i["variant_id"], "quantity": i["quantity"]} for i in items],
            "discount_code": dc, "payment": {"token": pay["token"]}}


def checkout(state, body):
    req = validate_checkout(body)
    fp = canonical(req)
    oid = req["order_id"]
    with state.lock:
        prior = state.orders.get(oid)
        if prior is not None:
            if prior["fingerprint"] != fp:
                raise conflict("DUPLICATE_ORDER_ID", f"Order {oid} already exists with a different body.", order_id=oid)
            if prior["error"] is not None:
                raise prior["error"]
            return 200, prior["response"]
        for it in req["items"]:
            if it["variant_id"] not in state.variants:
                raise not_found("VARIANT_NOT_FOUND", f"Variant {it['variant_id']} not found.",
                                variant_id=it["variant_id"])
        if req["discount_code"] is not None and req["discount_code"] not in DISCOUNTS:
            raise ApiError(400, "INVALID_DISCOUNT_CODE", f"Discount code {req['discount_code']} is not valid.",
                           {"discount_code": req["discount_code"]})
        # Atomic all-or-nothing reservation.
        for it in req["items"]:
            v = state.variants[it["variant_id"]]
            if v["stock"] < it["quantity"]:
                raise conflict("OUT_OF_STOCK", f"Variant {it['variant_id']} has no stock left.",
                               variant_id=it["variant_id"])
        lines = []
        for it in req["items"]:
            v = state.variants[it["variant_id"]]
            v["stock"] -= it["quantity"]
            v["reserved"] += it["quantity"]
            lines.append({"variant_id": it["variant_id"], "quantity": it["quantity"], "unit_price_minor": current_price(v)})
        state.orders[oid] = {"fingerprint": fp, "status": "pending", "response": None, "error": None, "in_flight": True}
        state.emit("order.status_changed", {"order_id": oid, "from": None, "to": "pending"})

    subtotal = sum(l["quantity"] * l["unit_price_minor"] for l in lines)
    pct = DISCOUNTS.get(req["discount_code"], 0)
    discount = subtotal * pct // 100
    total = subtotal - discount
    gw = state.gateway
    token = req["payment"]["token"]
    auth = gw.authorize(token, total)
    error = None
    cap = None
    if not auth["ok"]:
        error = ApiError(402, "PAYMENT_DECLINED", "The payment was declined by the card issuer.", {"order_id": oid})
    else:
        cap = gw.capture(token, auth["authorization_id"])
        if not cap["ok"]:
            gw.void(auth["authorization_id"])
            error = ApiError(402, "PAYMENT_CAPTURE_FAILED", "The payment could not be captured; no money was taken.",
                             {"order_id": oid, "authorization_id": auth["authorization_id"]})

    with state.lock:
        order = state.orders[oid]
        for l in lines:
            v = state.variants[l["variant_id"]]
            v["reserved"] -= l["quantity"]
            if error is not None:
                v["stock"] += l["quantity"]  # release the reservation
        if error is not None:
            order.update({"status": "cancelled", "error": error, "in_flight": False})
            state.emit("order.status_changed", {"order_id": oid, "from": "pending", "to": "cancelled",
                                                "reason": error.code})
            state.persist("order", {"order_id": oid, "status": "cancelled", "customer_id": req["customer_id"],
                                    "total_minor": total, "error": error.code})
            raise error
        paid_at = now_iso()
        payload = {"order_id": oid, "customer_id": req["customer_id"], "items": lines, "subtotal_minor": subtotal,
                   "discount_minor": discount, "total_minor": total, "currency": "PKR", "paid_at": paid_at}
        resp = {"order_id": oid, "status": "paid", "currency": "PKR", "items": lines, "subtotal_minor": subtotal,
                "discount_minor": discount, "total_minor": total,
                "payment": {"authorization_id": auth["authorization_id"], "capture_id": cap["capture_id"],
                            "state": "captured"},
                "receipt": {"payload": payload, "signature": sign(oid, payload),
                            "pdf_base64": base64.b64encode(receipt_pdf(payload)).decode("ascii")}}
        order.update({"status": "paid", "response": resp, "in_flight": False, "customer_id": req["customer_id"]})
        state.emit("order.status_changed", {"order_id": oid, "from": "pending", "to": "paid"})
        state.persist("order", {"order_id": oid, "status": "paid", "customer_id": req["customer_id"],
                                "total_minor": total, "receipt": payload})
    return 201, resp


def transition_order(state, order_id, to):
    order = state.orders.get(order_id)
    if order is None or order["response"] is None:
        raise not_found("ORDER_NOT_FOUND", f"Order {order_id} not found.", order_id=order_id)
    if to not in ORDER_TRANSITIONS.get(order["status"], set()):
        raise conflict("ILLEGAL_TRANSITION", f"Order cannot move from {order['status']} to {to}.",
                       order_id=order_id, status=order["status"])
    frm = order["status"]
    if to == "refunded":
        state.gateway.refund(order["response"]["payment"]["capture_id"])
    order["status"] = to
    state.emit("order.status_changed", {"order_id": order_id, "from": frm, "to": to})
    return {"order_id": order_id, "status": to}


def inventory(state, variant_id):
    v = state.variants.get(variant_id)
    if v is None:
        raise not_found("VARIANT_NOT_FOUND", f"Variant {variant_id} not found.", variant_id=variant_id)
    return {"variant_id": variant_id, "stock": v["stock"], "reserved": v["reserved"]}


def fmt_pkr(minor):
    return f"PKR {minor // 100}.{minor % 100:02d}"


def _pdf_escape(s):
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def receipt_pdf(payload):
    """Minimal hand-built PDF (Helvetica text) generated server-side."""
    lines = ["NaSCon Club Store - Payment Receipt", "",
             f"Order ID: {payload['order_id']}", f"Customer: {payload['customer_id']}",
             f"Paid at: {payload['paid_at']}", ""]
    for it in payload["items"]:
        lines.append(f"{it['variant_id']}  x{it['quantity']}  @ {fmt_pkr(it['unit_price_minor'])}")
    lines += ["", f"Subtotal: {fmt_pkr(payload['subtotal_minor'])}",
              f"Discount: {fmt_pkr(payload['discount_minor'])}",
              f"Total: {fmt_pkr(payload['total_minor'])}", "", "Payment state: captured (mock gateway)"]
    ops = ["BT", "/F1 12 Tf", "16 TL", "50 790 Td"]
    for ln in lines:
        ops.append(f"({_pdf_escape(ln)}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
