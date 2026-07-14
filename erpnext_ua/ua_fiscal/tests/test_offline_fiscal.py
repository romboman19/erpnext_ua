import hashlib
import struct
import unittest

from erpnext_ua.ua_fiscal.offline_fiscal import (
	build_offline_package,
	control_number,
	doc_hash,
	offline_fiscal_number,
)


class TestOfflineFiscalPrimitives(unittest.TestCase):
	def test_official_crc32_vector(self):
		"""Контрольний приклад з опису API Фіскального сервера від 08.08.2025."""
		self.assertEqual(
			control_number(
				"179625192271939",
				"20082020",
				"142338",
				10,
				"4000002411",
				10,
				prev_doc_hash="cdd68bb111f8993f3603f0179341571b35b73a07d5acee9b28fbfb714698e1b3",
			),
			4758,
		)

	def test_offline_fiscal_number(self):
		self.assertEqual(offline_fiscal_number(5008, 3, 4758), "5008.3.4758")

	def test_hash_is_lowercase_sha256(self):
		payload = b"signed-document"
		self.assertEqual(doc_hash(payload), hashlib.sha256(payload).hexdigest())

	def test_package_is_little_endian_length_prefixed(self):
		documents = [b"one", b"two-two"]
		packet = build_offline_package(documents)
		offset = 0
		decoded = []
		while offset < len(packet):
			size = struct.unpack_from("<I", packet, offset)[0]
			offset += 4
			decoded.append(packet[offset : offset + size])
			offset += size
		self.assertEqual(decoded, documents)
		self.assertEqual(offset, len(packet))

	def test_package_rejects_more_than_100_documents(self):
		with self.assertRaises(ValueError):
			build_offline_package([b"x"] * 101)


if __name__ == "__main__":
	unittest.main()
