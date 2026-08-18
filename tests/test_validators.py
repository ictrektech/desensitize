import unittest

from app.services.validators import VALIDATORS, china_id_checksum, cn_mobile, luhn_valid


class ChinaIdTest(unittest.TestCase):
    def test_valid_checksum(self):
        self.assertTrue(china_id_checksum("11010519491231002X"))
        self.assertTrue(china_id_checksum(" 11010519491231002x "))

    def test_invalid_checksum(self):
        self.assertFalse(china_id_checksum("110105194912310021"))
        self.assertFalse(china_id_checksum("110105194912310028"))

    def test_malformed(self):
        self.assertFalse(china_id_checksum("1101051949123100"))
        self.assertFalse(china_id_checksum("11010519491231002Y"))
        self.assertFalse(china_id_checksum(""))

    def test_digit_checksum_character(self):
        self.assertTrue(china_id_checksum("110105194912310003"))
        self.assertFalse(china_id_checksum("110105194912310002"))


class LuhnTest(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(luhn_valid("4111111111111111"))
        self.assertTrue(luhn_valid("6222600260001072444"))

    def test_invalid(self):
        self.assertFalse(luhn_valid("4111111111111112"))

    def test_malformed(self):
        self.assertFalse(luhn_valid(""))
        self.assertFalse(luhn_valid("4111a11111111111"))


class MobileTest(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(cn_mobile("13800138000"))
        self.assertTrue(cn_mobile("+8613800138000"))
        self.assertTrue(cn_mobile("8613800138000"))

    def test_invalid(self):
        self.assertFalse(cn_mobile("12800138000"))
        self.assertFalse(cn_mobile("1380013800"))
        self.assertFalse(cn_mobile(""))


class RegistryTest(unittest.TestCase):
    def test_registry_contains_builtin_validators(self):
        self.assertEqual(set(VALIDATORS), {"china_id", "luhn", "cn_mobile"})


if __name__ == "__main__":
    unittest.main()
