"""Клієнт фіскального сервера ДПС (Опис АРІ ЄВПЕЗ, версія 08.08.2025).

Ендпоінти: <база>/cmd (JSON-команди), <база>/doc (підписані документи),
<база>/pck (пакети офлайн документів).

Підпис документів — через сервіс prro-signer (jkurwa, attached CMS ДСТУ-4145).
"""

import base64
import uuid

import frappe
import requests

REQUEST_UID_NS = uuid.NAMESPACE_URL


class FiscalServerError(frappe.ValidationError):
	pass


class FiscalClient:
	def __init__(self):
		self.settings = frappe.get_single("PRRO Settings")
		self.base_url = self.settings.get_fiscal_server_url()
		self.timeout = self.settings.request_timeout or 15

	# --- Підпис ---

	def sign(self, data: bytes, kep_key: str) -> bytes:
		"""Підписує дані ключем UA KEP Key через prro-signer (attached CMS)."""
		key_doc = frappe.get_doc("UA KEP Key", kep_key)
		if key_doc.status != "Active":
			frappe.throw(f"Ключ КЕП {kep_key} має статус {key_doc.status}", FiscalServerError)

		file_doc = frappe.get_doc("File", {"file_url": key_doc.key_file})
		key_content = file_doc.get_content()
		if isinstance(key_content, str):
			key_content = key_content.encode()

		signservice_url = (self.settings.signservice_url or "").rstrip("/")
		if not signservice_url:
			frappe.throw("Не налаштовано URL сервісу підпису в PRRO Settings", FiscalServerError)

		resp = requests.post(
			f"{signservice_url}/api/sign",
			json={
				"key": base64.b64encode(key_content).decode(),
				"password": key_doc.get_password("key_password"),
				"data": base64.b64encode(data).decode(),
				"detached": False,
			},
			headers={"x-api-key": self.settings.get_password("signservice_api_key") or ""},
			timeout=self.timeout,
		)
		if resp.status_code != 200:
			frappe.throw(f"Сервіс підпису повернув {resp.status_code}: {resp.text[:300]}", FiscalServerError)
		return base64.b64decode(resp.json()["signature"])

	# --- Транспорт ---

	def send_document(self, signed_document: bytes) -> bytes:
		"""POST /doc — надсилання підписаного документа. Повертає квитанцію (XML)."""
		resp = requests.post(
			f"{self.base_url}/doc",
			data=signed_document,
			headers={"Content-Type": "application/octet-stream"},
			timeout=self.timeout,
		)
		if resp.status_code != 200:
			raise_fiscal_error(resp)
		return resp.content

	def send_package(self, signed_package: bytes) -> dict | str:
		"""POST /pck — пакет офлайн документів."""
		resp = requests.post(
			f"{self.base_url}/pck",
			data=signed_package,
			headers={"Content-Type": "application/octet-stream"},
			timeout=self.timeout,
		)
		if resp.status_code != 200:
			raise_fiscal_error(resp)
		try:
			return resp.json()
		except ValueError:
			return resp.text

	def command(self, payload: dict, signed_by: str | None = None) -> requests.Response:
		"""POST /cmd — команда. Якщо signed_by заданий, JSON засвідчується КЕП."""
		payload.setdefault("UID", str(uuid.uuid4()))
		if signed_by:
			body = self.sign(frappe.as_json(payload).encode("utf-8"), signed_by)
			headers = {"Content-Type": "application/octet-stream"}
		else:
			body = frappe.as_json(payload).encode("utf-8")
			headers = {"Content-Type": "application/json; charset=UTF-8"}

		resp = requests.post(
			f"{self.base_url}/cmd?resultAsJson=true",
			data=body,
			headers=headers,
			timeout=self.timeout,
		)
		if resp.status_code not in (200, 204):
			raise_fiscal_error(resp)
		return resp

	# --- Команди ---

	def server_state(self) -> dict:
		return self.command({"Command": "ServerState"}).json()

	def objects(self, kep_key: str) -> dict | None:
		"""Перелік доступних госп. одиниць і ПРРО для власника ключа."""
		resp = self.command({"Command": "Objects"}, signed_by=kep_key)
		return resp.json() if resp.status_code == 200 else None

	def operators(self, kep_key: str) -> dict | None:
		resp = self.command({"Command": "Operators"}, signed_by=kep_key)
		return resp.json() if resp.status_code == 200 else None

	def registrar_state(self, fiscal_number: str, kep_key: str, **extra) -> dict | None:
		payload = {"Command": "TransactionsRegistrarState", "NumFiscal": fiscal_number, **extra}
		resp = self.command(payload, signed_by=kep_key)
		return resp.json() if resp.status_code == 200 else None

	def last_shift_totals(self, fiscal_number: str, kep_key: str) -> dict | None:
		resp = self.command(
			{"Command": "LastShiftTotals", "NumFiscal": fiscal_number}, signed_by=kep_key
		)
		return resp.json() if resp.status_code == 200 else None

	def device_register(self, fiscal_number: str, device_id: str, kep_key: str, forced=False) -> dict:
		return self.command(
			{
				"Command": "DeviceRegister",
				"NumFiscal": fiscal_number,
				"DeviceId": device_id,
				"Forced": bool(forced),
			},
			signed_by=kep_key,
		).json()


def raise_fiscal_error(resp):
	frappe.throw(
		f"Фіскальний сервер: HTTP {resp.status_code} — {resp.text[:500]}",
		FiscalServerError,
	)


@frappe.whitelist()
def check_server_state():
	"""Перевірка звʼязку з фіскальним сервером (кнопка в PRRO Settings)."""
	state = FiscalClient().server_state()
	return state
