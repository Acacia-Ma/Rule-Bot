import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.domain_utils import (
    extract_domain,
    extract_second_level_domain,
    extract_second_level_domain_for_rules,
    normalize_domain,
)


class TestDomainUtils(unittest.TestCase):
    def test_extract_domain(self):
        self.assertEqual(
            extract_domain("https://www.example.com/path?x=1"),
            "example.com"
        )
        self.assertEqual(extract_domain("example.com:8080"), "example.com")
        self.assertEqual(extract_domain("www.Example.com"), "example.com")

    def test_extract_second_level_domain(self):
        self.assertEqual(extract_second_level_domain("sub.example.com"), "example.com")
        self.assertEqual(extract_second_level_domain("a.b.example.co.uk"), "example.co.uk")
        self.assertEqual(extract_second_level_domain("a.b.c.com.cn"), "c.com.cn")

    def test_extract_second_level_domain_for_rules_cn(self):
        self.assertIsNone(extract_second_level_domain_for_rules("example.cn"))
        self.assertIsNone(extract_second_level_domain_for_rules("http://www.example.com.cn/path"))

    def test_normalize_domain(self):
        self.assertEqual(normalize_domain("HTTP://WWW.Example.Com"), "example.com")


if __name__ == '__main__':
    unittest.main()
