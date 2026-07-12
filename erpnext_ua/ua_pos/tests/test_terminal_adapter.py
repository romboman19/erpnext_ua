import unittest

from erpnext_ua.ua_pos.adapters.terminal import PrivatPosAdapter


class FakeClient:
	def __init__(self, result):
		self.result = result
		self.calls = []

	def operation(self, *args, **kwargs):
		self.calls.append((args, kwargs))
		return self.result

	def status(self, *args, **kwargs):
		self.calls.append((args, kwargs))
		return self.result

	def ping(self, *args, **kwargs):
		return self.result


class TestPrivatPosAdapter(unittest.TestCase):
	def test_sale_maps_approved_response(self):
		client = FakeClient({"responseCode": "0000", "rrn": "42", "invoiceNumber": "7"})
		result = PrivatPosAdapter(client).sale({"ip": "127.0.0.1", "port": 2000}, 10, "op-1")
		self.assertEqual(result.status, "confirmed")
		self.assertEqual(result.rrn, "42")
		self.assertEqual(len(client.calls), 1)

	def test_timeout_is_unknown_and_not_retried(self):
		client = FakeClient({"error": True, "description": "timeout"})
		result = PrivatPosAdapter(client).sale({"ip": "127.0.0.1", "port": 2000}, 10, "op-2")
		self.assertEqual(result.status, "unknown")
		self.assertEqual(len(client.calls), 1)

	def test_status_uses_original_operation_id(self):
		client = FakeClient({"status": "approved"})
		result = PrivatPosAdapter(client).status({"ip": "127.0.0.1", "port": 2000}, "op-3")
		self.assertEqual(result.status, "confirmed")
		self.assertEqual(client.calls[0][0][1], "op-3")


if __name__ == "__main__":
	unittest.main()
