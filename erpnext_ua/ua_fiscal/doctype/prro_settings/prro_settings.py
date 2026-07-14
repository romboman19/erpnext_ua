import frappe
from urllib.parse import urlparse
from frappe.model.document import Document


class PRROSettings(Document):
	def get_fiscal_server_url(self) -> str:
		# ЄВПЕЗ: один REST-ендпоінт для тесту й бою; режим керує лише прапорцем
		# <TESTING> у документах, а не адресою сервера.
		if not self.fiscal_server_url:
			frappe.throw("Не задано URL фіскального сервера ДПС")
		url = self.fiscal_server_url.rstrip("/")
		parsed = urlparse(url)
		if parsed.scheme not in {"https", "http"} or not parsed.hostname:
			frappe.throw("URL фіскального сервера має бути абсолютною HTTP(S)-адресою")
		if self.mode == "Бойовий":
			if parsed.scheme != "https":
				frappe.throw("У бойовому режимі фіскальний сервер має використовувати HTTPS")
			if parsed.hostname != "fs.tax.gov.ua" and not self.allow_custom_fiscal_server:
				frappe.throw(
					"Бойовий режим дозволяє лише офіційний хост fs.tax.gov.ua. "
					"Нестандартний сервер потребує окремого явного дозволу."
				)
		return url

	def validate(self):
		if int(self.request_timeout or 0) < 3 or int(self.request_timeout or 0) > 120:
			frappe.throw("Таймаут ДПС має бути від 3 до 120 секунд")
		if self.enabled:
			self.get_fiscal_server_url()
			if not self.signservice_url or not self.get_password("signservice_api_key", raise_exception=False):
				frappe.throw("Для ввімкнення фіскалізації налаштуйте URL та API-ключ prro-signer")
