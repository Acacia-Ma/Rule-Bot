#!/usr/bin/env python3
"""
10-minute stress simulation for Rule-Bot core logic.
Exercises GeoSite checks, DNS/NS resolution, and optional GitHub rule checks.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import time
from types import SimpleNamespace
from typing import List

from loguru import logger

from src.data_manager import DataManager
from src.services.dns_service import DNSService
from src.services.geoip_service import GeoIPService
from src.services.domain_checker import DomainChecker
from src.services.github_service import GitHubService


DEFAULT_DOMAINS = [
    "example.com",
    "www.google.com",
    "www.bing.com",
    "www.cloudflare.com",
    "github.com",
    "openai.com",
    "www.baidu.com",
    "www.qq.com",
    "www.taobao.com",
    "www.jd.com",
]


def load_domains(path: str) -> List[str]:
    if not path:
        return DEFAULT_DOMAINS
    domains = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            domains.append(line)
    return domains or DEFAULT_DOMAINS


def build_data_config() -> SimpleNamespace:
    return SimpleNamespace(
        DATA_DIR=os.getenv("DATA_DIR", "/tmp/rule-bot-data"),
        DATA_UPDATE_INTERVAL=int(os.getenv("DATA_UPDATE_INTERVAL", "21600")),
        GEOIP_URLS=[
            "https://gcore.jsdelivr.net/gh/Aethersailor/geoip@release/Country-without-asn.mmdb",
            "https://testingcf.jsdelivr.net/gh/Aethersailor/geoip@release/Country-without-asn.mmdb",
            "https://raw.githubusercontent.com/Aethersailor/geoip/release/Country-without-asn.mmdb",
        ],
        CN_IPV4_URLS=[
            "https://raw.githubusercontent.com/Aethersailor/geoip/refs/heads/release/text/cn-ipv4.txt",
            "https://gcore.jsdelivr.net/gh/Aethersailor/geoip@release/text/cn-ipv4.txt",
            "https://testingcf.jsdelivr.net/gh/Aethersailor/geoip@release/text/cn-ipv4.txt",
        ],
        GEOSITE_URL="https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/refs/heads/release/direct-list.txt",
        GEOSITE_CACHE_TTL=int(os.getenv("GEOSITE_CACHE_TTL", "3600")),
        GEOSITE_CACHE_SIZE=int(os.getenv("GEOSITE_CACHE_SIZE", "2048")),
    )


def build_dns_config() -> SimpleNamespace:
    return SimpleNamespace(
        DOH_SERVERS={
            "alibaba": "https://dns.alidns.com/dns-query",
            "tencent": "https://doh.pub/dns-query",
            "cloudflare": "https://cloudflare-dns.com/dns-query",
        },
        NS_DOH_SERVERS={
            "cloudflare": "https://cloudflare-dns.com/dns-query",
            "google": "https://dns.google/dns-query",
            "quad9": "https://dns.quad9.net/dns-query",
        },
        DNS_CACHE_TTL=int(os.getenv("DNS_CACHE_TTL", "60")),
        DNS_CACHE_SIZE=int(os.getenv("DNS_CACHE_SIZE", "1024")),
        NS_CACHE_TTL=int(os.getenv("NS_CACHE_TTL", "300")),
        NS_CACHE_SIZE=int(os.getenv("NS_CACHE_SIZE", "512")),
        DNS_MAX_CONCURRENCY=int(os.getenv("DNS_MAX_CONCURRENCY", "20")),
        DNS_CONN_LIMIT=int(os.getenv("DNS_CONN_LIMIT", "30")),
        DNS_CONN_LIMIT_PER_HOST=int(os.getenv("DNS_CONN_LIMIT_PER_HOST", "10")),
        DNS_TIMEOUT_TOTAL=int(os.getenv("DNS_TIMEOUT_TOTAL", "10")),
        DNS_TIMEOUT_CONNECT=int(os.getenv("DNS_TIMEOUT_CONNECT", "3")),
        GEOIP_CACHE_SIZE=int(os.getenv("GEOIP_CACHE_SIZE", "4096")),
        GEOIP_CACHE_TTL=int(os.getenv("GEOIP_CACHE_TTL", "21600")),
    )


def build_github_service() -> GitHubService | None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPO", "").strip()
    direct_file = os.getenv("DIRECT_RULE_FILE", "").strip()
    if not token or not repo or not direct_file:
        return None
    config = SimpleNamespace(
        GITHUB_TOKEN=token,
        GITHUB_REPO=repo,
        DIRECT_RULE_FILE=direct_file,
        GITHUB_COMMIT_NAME="Rule-Bot",
        GITHUB_COMMIT_EMAIL=os.getenv("GITHUB_COMMIT_EMAIL", "noreply@users.noreply.github.com"),
        GITHUB_FILE_CACHE_TTL=int(os.getenv("GITHUB_FILE_CACHE_TTL", "60")),
        GITHUB_FILE_CACHE_SIZE=int(os.getenv("GITHUB_FILE_CACHE_SIZE", "4")),
    )
    return GitHubService(config)


async def worker(
    worker_id: int,
    domains: List[str],
    end_time: float,
    data_manager: DataManager,
    checker: DomainChecker,
    github_service: GitHubService | None,
    pause: float,
):
    while time.time() < end_time:
        domain = random.choice(domains)
        try:
            await data_manager.is_domain_in_geosite(domain)
            await checker.check_domain_comprehensive(domain)
            if github_service:
                await github_service.check_domain_in_rules(domain)
        except Exception as e:
            logger.warning("worker {} 处理域名 {} 失败: {}", worker_id, domain, e)
        await asyncio.sleep(pause)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=600, help="Duration seconds")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent workers")
    parser.add_argument("--pause", type=float, default=0.5, help="Pause between iterations")
    parser.add_argument("--domains-file", type=str, default="", help="Optional domain list file")
    args = parser.parse_args()

    domains = load_domains(args.domains_file)

    data_cfg = build_data_config()
    dns_cfg = build_dns_config()
    data_manager = DataManager(data_cfg)
    await data_manager.initialize()

    dns_service = DNSService(
        dns_cfg.DOH_SERVERS,
        dns_cfg.NS_DOH_SERVERS,
        cache_size=dns_cfg.DNS_CACHE_SIZE,
        cache_ttl=dns_cfg.DNS_CACHE_TTL,
        ns_cache_size=dns_cfg.NS_CACHE_SIZE,
        ns_cache_ttl=dns_cfg.NS_CACHE_TTL,
        max_concurrency=dns_cfg.DNS_MAX_CONCURRENCY,
        conn_limit=dns_cfg.DNS_CONN_LIMIT,
        conn_limit_per_host=dns_cfg.DNS_CONN_LIMIT_PER_HOST,
        timeout_total=dns_cfg.DNS_TIMEOUT_TOTAL,
        timeout_connect=dns_cfg.DNS_TIMEOUT_CONNECT,
    )
    await dns_service.start()
    geoip_service = GeoIPService(
        str(data_manager.geoip_file),
        str(data_manager.cn_ipv4_file),
        cache_size=dns_cfg.GEOIP_CACHE_SIZE,
        cache_ttl=dns_cfg.GEOIP_CACHE_TTL,
    )
    checker = DomainChecker(dns_service, geoip_service)
    github_service = build_github_service()

    end_time = time.time() + args.duration
    tasks = [
        asyncio.create_task(
            worker(i, domains, end_time, data_manager, checker, github_service, args.pause)
        )
        for i in range(args.concurrency)
    ]

    await asyncio.gather(*tasks, return_exceptions=True)
    await dns_service.close()
    await data_manager.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
