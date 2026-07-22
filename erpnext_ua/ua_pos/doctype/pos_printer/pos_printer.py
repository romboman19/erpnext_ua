import ipaddress
import re

import frappe
from frappe.model.document import Document


_HOSTNAME = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def is_lan_address(address: str) -> bool:
	ip = ipaddress.ip_address(address)
	return (
		(ip.version == 4 and any(ip in network for network in (
			ipaddress.ip_network("10.0.0.0/8"),
			ipaddress.ip_network("172.16.0.0/12"),
			ipaddress.ip_network("192.168.0.0/16"),
		)))
		or (ip.version == 6 and ip in ipaddress.ip_network("fc00::/7"))
	)


class POSPrinter(Document):
	def validate(self):
		self.host = (self.host or "").strip().lower()
		if not self.host or not _HOSTNAME.fullmatch(self.host):
			frappe.throw("Вкажіть коректний hostname або приватну IP-адресу принтера")
		try:
			ipaddress.ip_address(self.host)
		except ValueError:
			pass  # DNS буде повторно перевірено на приватну адресу безпосередньо перед з'єднанням.
		else:
			if not is_lan_address(self.host):
				frappe.throw("Мережевий POS-принтер повинен мати приватну LAN-адресу")
		if not 1 <= int(self.port or 0) <= 65535:
			frappe.throw("Порт принтера має бути в межах 1–65535")
		if not 16 <= int(self.characters_per_line or 0) <= 96:
			frappe.throw("Ширина чека має бути в межах 16–96 символів")
		if not 1 <= int(self.connect_timeout or 0) <= 30:
			frappe.throw("Timeout принтера має бути в межах 1–30 секунд")
		if not 1 <= int(self.max_attempts or 0) <= 10:
			frappe.throw("Кількість спроб друку має бути в межах 1–10")

	def on_trash(self):
		if frappe.db.exists("POS Print Job", {"printer": self.name}):
			frappe.throw("Принтер з історією друку не можна видалити; переведіть його у статус Disabled")
