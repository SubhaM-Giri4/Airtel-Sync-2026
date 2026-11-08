from __future__ import annotations

import csv
import json
import secrets
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATIC = ROOT / "static"
HOST = "127.0.0.1"
PORT = 8000

SEGMENTS = {
    "micro": "Micro retail & services",
    "professional": "Professional offices",
    "multi": "Small multi-site businesses",
    "manufacturing": "Small manufacturers",
}
CATALOGUE_SEGMENTS = {
    "micro": "micro",
    "professional": "prof",
    "multi": "multi",
    "manufacturing": "mfg",
}

BUNDLE_PLANS = {
    "micro": [("P04", 1), ("P07", 1), ("P19", 1)],
    "professional": [("P02", 1), ("P07", 2), ("P16", 5), ("P17", 1), ("P20", 5), ("P11", 1), ("P12", 1)],
    "multi": [("P02", 1), ("P09", 1), ("P07", 1), ("P12", 1), ("P23", 2), ("P25", 1)],
    "manufacturing": [("P05", 1), ("P08", 5), ("P16", 5), ("P20", 10), ("P21", 1), ("P24", 5)],
}


def read_csv(filename: str) -> list[dict[str, str]]:
    with (DATA / filename).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


PRODUCTS = {row["product_id"]: row for row in read_csv("product_catalogue.csv")}
LEADS = read_csv("smb_leads.csv")
GSTIN_REGISTRY = {row["gstin"].upper(): row for row in read_csv("mock_gstin_registry.csv")}
UDYAM_REGISTRY = {row["udyam_number"].upper(): row for row in read_csv("mock_udyam_registry.csv")}

STAGE_ORDER = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]


def number(value: str, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_active_gstin(identifier: str) -> bool:
    record = GSTIN_REGISTRY.get(identifier.strip().upper())
    return bool(record and record.get("status", "").lower() == "active")


def make_dashboard() -> dict:
    activated = [lead for lead in LEADS if lead["outcome"] == "Activated"]
    stage_positions = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    stage_counts = {
        stage: sum(1 for lead in LEADS if stage_positions[lead["stage_reached"]] >= stage_positions[stage])
        for stage in STAGE_ORDER
    }
    count = len(activated)
    average = lambda key: round(sum(number(lead[key]) for lead in activated) / count, 1) if count else 0
    cac = round(sum(number(lead["acquisition_cost_inr"]) for lead in LEADS) / count) if count else 0
    churned = sum(1 for lead in activated if lead["churned_within_6_months"].upper() == "Y")
    return {
        "lead_count": len(LEADS),
        "activated_count": count,
        "conversion_rate": round(count / len(LEADS) * 100, 1) if LEADS else 0,
        "average_days": average("days_lead_to_activation"),
        "average_followups": average("customer_follow_up_calls"),
        "acquisition_cost": cac,
        "churn_rate": round(churned / count * 100, 1) if count else 0,
        "stages": [{"name": stage, "count": stage_counts[stage]} for stage in STAGE_ORDER],
    }


def recommend(profile: dict) -> dict:
    segment = str(profile.get("segment", ""))
    if segment not in SEGMENTS:
        raise ValueError("Choose one of the listed business segments.")

    try:
        tier = int(profile.get("city_tier", 0))
        employees = int(profile.get("employees", 0))
        sites = int(profile.get("sites", 0))
    except (TypeError, ValueError):
        raise ValueError("City tier, employee count, and site count must be numbers.") from None
    if tier not in (1, 2) or not 1 <= employees <= 100000 or not 1 <= sites <= 1000:
        raise ValueError("Use city tier 1 or 2, at least 1 employee, and at least 1 site.")

    gstin = str(profile.get("gstin", "")).strip().upper()
    gstin_active = is_active_gstin(gstin) if gstin else False
    chosen = []
    for product_id, base_quantity in BUNDLE_PLANS[segment]:
        product = PRODUCTS[product_id]
        if CATALOGUE_SEGMENTS[segment] not in product["target_segments"].split(";"):
            continue
        if str(tier) not in product["available_city_tiers"].split(";"):
            continue
        if employees < int(product["min_employees"]) or sites < int(product["min_sites"]):
            continue
        if product["requires_gstin"] == "Y" and not gstin_active:
            continue

        dependencies = [item for item in product["requires_one_of"].split("|") if item]
        already_selected = {item["product_id"] for item in chosen}
        if dependencies and not already_selected.intersection(dependencies):
            continue
        quantity = sites if product["unit"].lower() in ("per site", "per location") else base_quantity
        chosen.append({
            "product_id": product_id,
            "name": product["product_name"],
            "category": product["category"],
            "quantity": quantity,
            "unit": product["unit"],
            "monthly_min": int(product["price_min_inr_per_month"]) * quantity,
            "monthly_max": int(product["price_max_inr_per_month"]) * quantity,
            "setup": int(product["one_time_setup_inr"]) * quantity,
            "install_days": int(product["typical_install_days"]),
        })

    monthly_min = sum(item["monthly_min"] for item in chosen)
    monthly_max = sum(item["monthly_max"] for item in chosen)
    setup = sum(item["setup"] for item in chosen)
    if not chosen:
        raise ValueError("No products in this bundle meet the selected location and eligibility rules.")
    if segment == "manufacturing" and not gstin_active:
        explanation = "A valid, active GSTIN is needed for the leased-line and managed-security options. This is a preliminary eligible-products quote."
    else:
        explanation = "This bundle uses catalogue prices and filters products by segment, city tier, size, GSTIN status, and dependencies."
    return {
        "segment": SEGMENTS[segment],
        "segment_key": segment,
        "products": chosen,
        "monthly_min": monthly_min,
        "monthly_max": monthly_max,
        "setup": setup,
        "install_days": max(item["install_days"] for item in chosen),
        "gstin_active": gstin_active,
        "explanation": explanation,
        "profile": {"city_tier": tier, "employees": employees, "sites": sites},
    }


def lookup_registry(body: dict) -> dict:
    if body.get("consent") is not True:
        raise ValueError("Consent is required before a registry lookup.")
    kind = str(body.get("type", ""))
    identifier = str(body.get("identifier", "")).strip().upper()
    if not identifier:
        raise ValueError("Enter a GSTIN or Udyam number.")
    if len(identifier) > 40:
        raise ValueError("The identifier is too long.")

    if kind == "gstin":
        record = GSTIN_REGISTRY.get(identifier)
        masked = f"{identifier[:2]}{'*' * max(0, len(identifier) - 6)}{identifier[-4:]}" if len(identifier) >= 6 else "****"
        if not record:
            return {"found": False, "type": kind, "masked_identifier": masked, "message": "No match in the synthetic GSTIN registry."}
        return {
            "found": True,
            "type": kind,
            "masked_identifier": masked,
            "business_name": record["trade_name"],
            "legal_name": record["legal_name"],
            "state": record["state"],
            "status": record["status"],
        }
    if kind == "udyam":
        record = UDYAM_REGISTRY.get(identifier)
        masked = f"{identifier[:9]}{'*' * max(0, len(identifier) - 13)}{identifier[-4:]}" if len(identifier) >= 13 else "****"
        if not record:
            return {"found": False, "type": kind, "masked_identifier": masked, "message": "No match in the synthetic Udyam registry."}
        return {
            "found": True,
            "type": kind,
            "masked_identifier": masked,
            "business_name": record["enterprise_name"],
            "enterprise_type": record["enterprise_type"],
            "activity": record["major_activity"],
            "state": record["state"],
            "city": record["city"],
        }
    raise ValueError("Choose GSTIN or Udyam for the lookup.")


def ranked_leads() -> list[dict]:
    candidates = []
    for lead in LEADS:
        if lead["outcome"] == "Activated":
            continue
        segment_key = next((key for key, label in SEGMENTS.items() if label == lead["segment"]), "")
        score = 0
        reasons = []
        if segment_key in ("professional", "multi"):
            score += 30
            reasons.append("priority segment")
        if int(number(lead["num_sites"])) > 1:
            score += 25
            reasons.append("multi-site")
        if lead["stage_reached"] in ("Quote accepted", "KYC complete"):
            score += 30
            reasons.append("near activation")
        if lead["has_gstin"] == "Y":
            score += 10
            reasons.append("GSTIN on file")
        if lead["lead_source"] in ("Referral", "Website form", "WhatsApp campaign"):
            score += 5
            reasons.append("low-touch source")
        candidates.append({
            "lead_id": lead["lead_id"],
            "segment": lead["segment"],
            "city": lead["city"],
            "stage": lead["stage_reached"],
            "sites": int(number(lead["num_sites"])),
            "score": score,
            "reason": ", ".join(reasons) or "follow-up needed",
        })
    return sorted(candidates, key=lambda item: (-item["score"], item["lead_id"]))[:12]


ORDERS: dict[str, dict] = {}


class UdyamHandler(BaseHTTPRequestHandler):
    server_version = "UdyamDigital/1.0"

    def log_message(self, _format: str, *args) -> None:
        return

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid request length.") from None
        if length < 1 or length > 8192:
            raise ValueError("Request body must be between 1 and 8192 bytes.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Request body must be valid JSON.") from None
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/health":
            self.send_json(200, {"ok": True, "mode": "synthetic local prototype"})
        elif route == "/api/dashboard":
            self.send_json(200, make_dashboard())
        elif route == "/api/products":
            self.send_json(200, {"products": list(PRODUCTS.values())})
        elif route == "/api/leads":
            self.send_json(200, {"leads": ranked_leads()})
        elif route.startswith("/api/orders/"):
            order_id = unquote(route.rsplit("/", 1)[-1])
            order = ORDERS.get(order_id)
            if not order:
                self.send_json(404, {"error": "Order not found. It may have expired when the server restarted."})
            else:
                self.send_json(200, order)
        else:
            self.serve_static(route)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        try:
            body = self.read_body()
            if route == "/api/recommend":
                self.send_json(200, recommend(body))
            elif route == "/api/lookup":
                self.send_json(200, lookup_registry(body))
            elif route == "/api/orders":
                quote = recommend(body)
                order_id = f"UD-{secrets.token_hex(3).upper()}"
                created = datetime.now(timezone.utc)
                days = quote["install_days"]
                order = {
                    "order_id": order_id,
                    "created_at": created.isoformat(timespec="minutes"),
                    "expected_activation": (date.today() + timedelta(days=days)).isoformat(),
                    "install_days": days,
                    "status": "Order created",
                    "steps": [
                        {"name": "Quote prepared", "state": "complete"},
                        {"name": "KYC consent & verification", "state": "next"},
                        {"name": "Order review", "state": "pending"},
                        {"name": "Installation & activation", "state": "pending"},
                    ],
                    "products": quote["products"],
                    "monthly_min": quote["monthly_min"],
                    "monthly_max": quote["monthly_max"],
                    "setup": quote["setup"],
                }
                ORDERS[order_id] = order
                self.send_json(201, order)
            else:
                self.send_json(404, {"error": "API route not found."})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})

    def serve_static(self, route: str) -> None:
        requested = "index.html" if route == "/" else route.removeprefix("/")
        path = (STATIC / requested).resolve()
        if STATIC.resolve() not in path.parents or not path.is_file():
            self.send_error(404)
            return
        content_type = "text/html; charset=utf-8" if path.suffix == ".html" else (
            "text/css; charset=utf-8" if path.suffix == ".css" else
            "text/javascript; charset=utf-8" if path.suffix == ".js" else
            "application/octet-stream"
        )
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    try:
        server = ThreadingHTTPServer((HOST, PORT), UdyamHandler)
    except OSError as error:
        if error.errno in (48, 98, 10048):
            raise SystemExit(f"Port {PORT} is already in use. Close the other app or change PORT in server.py.") from error
        raise
    print(f"Udyam Digital is ready at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
