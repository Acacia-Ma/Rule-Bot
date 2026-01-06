import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.services.domain_checker import DomainChecker


class DummyDNSService:
    async def query_a_record(self, domain: str, use_edns_china: bool = True):
        if domain == "ns1.example.com":
            return ["2.2.2.2"]
        return ["1.1.1.1"]

    async def query_ns_records(self, domain: str):
        return ["ns1.example.com"]


class DummyGeoIPService:
    def get_location_info(self, ip: str):
        if ip == "1.1.1.1":
            return {
                "ip": ip,
                "country_code": "CN",
                "country_name": "China",
                "is_china": True,
            }
        return {
            "ip": ip,
            "country_code": "US",
            "country_name": "United States",
            "is_china": False,
        }


class DummyDNSServiceNoChina:
    async def query_a_record(self, domain: str, use_edns_china: bool = True):
        return ["8.8.8.8"]

    async def query_ns_records(self, domain: str):
        return ["ns1.example.net"]


class DummyGeoIPServiceNoChina:
    def get_location_info(self, ip: str):
        return {
            "ip": ip,
            "country_code": "US",
            "country_name": "United States",
            "is_china": False,
        }


class TestDomainChecker(unittest.IsolatedAsyncioTestCase):
    async def test_check_domain_comprehensive_china_ip(self):
        checker = DomainChecker(DummyDNSService(), DummyGeoIPService())
        result = await checker.check_domain_comprehensive("www.example.com")

        self.assertEqual(result["second_level_domain"], "example.com")
        self.assertTrue(result["domain_china_status"] or result["second_level_china_status"])
        self.assertFalse(result["ns_china_status"])
        self.assertTrue(checker.should_add_directly(result))
        self.assertEqual(checker.get_target_domain_to_add(result), "example.com")

    async def test_check_domain_comprehensive_reject(self):
        checker = DomainChecker(DummyDNSServiceNoChina(), DummyGeoIPServiceNoChina())
        result = await checker.check_domain_comprehensive("example.net")

        self.assertTrue(checker.should_reject(result))
        self.assertIsNone(checker.get_target_domain_to_add(result))


if __name__ == '__main__':
    unittest.main()
