"""HTTP clients for the backing microservices. Errors surface as ServiceError with the service's own message."""

import httpx

from .config import settings


class ServiceError(Exception):
    def __init__(self, service: str, status: int, detail: str):
        super().__init__(f"{service} returned {status}: {detail}")
        self.status = status
        self.detail = detail


_http = httpx.AsyncClient(timeout=30.0)


async def _call(service: str, method: str, url: str, **kwargs):
    try:
        resp = await _http.request(method, url, **kwargs)
    except httpx.HTTPError as e:
        raise ServiceError(service, 503, f"service unavailable ({e.__class__.__name__})")
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ServiceError(service, resp.status_code, str(detail))
    if resp.headers.get("content-type", "").startswith("application/pdf"):
        return resp.content
    return resp.json()


class CoreBanking:
    base = settings.core_banking_url

    async def search_cnp(self, cnp):
        return await _call("core-banking", "GET", f"{self.base}/clients/search", params={"cnp": cnp})

    async def search_name(self, name):
        return await _call("core-banking", "GET", f"{self.base}/clients/search", params={"name": name})

    async def search_cnps(self, cnps):
        return await _call("core-banking", "POST", f"{self.base}/clients/search-by-cnps", json={"cnps": cnps})

    async def client(self, client_id):
        return await _call("core-banking", "GET", f"{self.base}/clients/{client_id}")

    async def clients(self):
        return await _call("core-banking", "GET", f"{self.base}/clients")

    async def snapshot(self, client_id):
        return await _call("core-banking", "GET", f"{self.base}/clients/{client_id}/snapshot")

    async def garnishments(self, client_id, status=None):
        params = {"status": status} if status else {}
        return await _call("core-banking", "GET", f"{self.base}/clients/{client_id}/garnishments", params=params)

    async def garnishments_by_case(self, case_ref):
        return await _call("core-banking", "GET", f"{self.base}/garnishments", params={"case_ref": case_ref})

    async def create_garnishment(self, body):
        return await _call("core-banking", "POST", f"{self.base}/garnishments", json=body)

    async def lift_garnishment(self, garnishment_id):
        return await _call("core-banking", "POST", f"{self.base}/garnishments/{garnishment_id}/lift")

    async def holds(self, client_id):
        return await _call("core-banking", "GET", f"{self.base}/clients/{client_id}/holds")

    async def replace_holds(self, client_id, holds):
        return await _call("core-banking", "PUT", f"{self.base}/clients/{client_id}/holds", json={"holds": holds})

    async def simulate_incoming(self, body):
        return await _call("core-banking", "POST", f"{self.base}/simulate/incoming", json=body)

    async def reset(self):
        return await _call("core-banking", "POST", f"{self.base}/admin/reset")


class RulesEngine:
    base = settings.rules_engine_url

    async def validate_cnp(self, cnp):
        return await _call("rules-engine", "POST", f"{self.base}/cnp/validate", json={"cnp": cnp})

    async def suggest_cnp(self, cnp):
        return await _call("rules-engine", "POST", f"{self.base}/cnp/suggest", json={"cnp": cnp})

    async def allocate(self, accounts, garnishments):
        return await _call("rules-engine", "POST", f"{self.base}/allocate",
                           json={"accounts": accounts, "garnishments": garnishments})

    async def rules(self):
        return await _call("rules-engine", "GET", f"{self.base}/rules")


class Documents:
    base = settings.document_service_url

    async def extract(self, filename, data: bytes):
        return await _call("document-service", "POST", f"{self.base}/extract",
                           files={"file": (filename, data, "application/pdf")})

    async def render_letter(self, body):
        return await _call("document-service", "POST", f"{self.base}/render/letter", json=body)


class Fx:
    base = settings.fx_service_url

    async def rates(self):
        return await _call("fx-service", "GET", f"{self.base}/rates")


core = CoreBanking()
rules = RulesEngine()
docs = Documents()
fx = Fx()
