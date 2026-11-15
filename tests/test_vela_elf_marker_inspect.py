"""Test fixed-category ELF marker reporting without exposing or storing secrets."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "elf_marker", ROOT / "deploy/vela/ci_elf_marker_inspect.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def fake_elf(payload):
    result = bytearray(512 + len(payload))
    result[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<Q", result, 40, 128)
    struct.pack_into("<HHH", result, 58, 64, 3, 1)
    names = b"\x00.shstrtab\x00.rodata\x00"
    result[64:64 + len(names)] = names
    struct.pack_into("<IIQQQQIIQQ", result, 128 + 64, 1, 3, 0, 0, 64, len(names), 0, 0, 1, 0)
    struct.pack_into("<IIQQQQIIQQ", result, 128 + 128, 11, 1, 0, 0, 512, len(payload), 0, 0, 1, 0)
    result[512:] = payload
    return bytes(result)

class ELFMarkerInventoryTests(unittest.TestCase):
    def test_isolated_header_is_only_a_count(self):
        header = b"-----BEGIN " + b"PRIVATE KEY-----"
        counters = mod.classify(fake_elf(header))
        self.assertEqual(counters["readonly_constants"], 1)
        self.assertEqual(counters["unpaired_header_within_bound"], 1)
        self.assertEqual(sum(counters.values()), 2)
        self.assertNotIn("PRIVATE KEY", repr(counters))

    def test_header_and_footer_both_reported(self):
        header = b"-----BEGIN " + b"PRIVATE KEY-----"
        footer = b"-----END " + b"PRIVATE KEY-----"
        c = mod.classify(fake_elf(header + b"\nNOT_A_REAL_KEY\n" + footer))
        self.assertEqual(c["readonly_constants"], 1)
        self.assertEqual(c["paired_header_within_bound"], 1)

    def test_corrupt_elf_fails_closed(self):
        with self.assertRaises(ValueError):
            mod.classify(b"\x7fELF")
        with self.assertRaises(ValueError):
            mod.classify(fake_elf(b"hello")[:190])

if __name__ == "__main__":
    unittest.main()
