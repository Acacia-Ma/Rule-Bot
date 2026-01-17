"""
配置管理模块
"""

import os
from typing import Optional, Dict
from loguru import logger


class Config:
    """配置类"""
    
    def __init__(self):
        # Telegram配置
        self.TELEGRAM_BOT_TOKEN = self._get_env_required("TELEGRAM_BOT_TOKEN")
        
        # GitHub配置
        self.GITHUB_TOKEN = self._get_env_required("GITHUB_TOKEN")
        self.GITHUB_REPO = self._get_env_required("GITHUB_REPO")
        # 强制使用Rule-Bot身份，只允许自定义邮箱
        self.GITHUB_COMMIT_NAME = "Rule-Bot"
        self.GITHUB_COMMIT_EMAIL = os.getenv("GITHUB_COMMIT_EMAIL", "noreply@users.noreply.github.com")
        
        # 规则文件配置
        self.DIRECT_RULE_FILE = self._get_env_required("DIRECT_RULE_FILE")
        self.PROXY_RULE_FILE = os.getenv("PROXY_RULE_FILE", "")  # 可选，暂未启用
        
        # 日志配置
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

        # 数据目录（可选）
        self.DATA_DIR = os.getenv("DATA_DIR", "").strip()
        
        # 群组验证配置（用于私聊模式下验证用户是否在群组中）
        required_group_id_raw = os.getenv("REQUIRED_GROUP_ID", "").strip()
        self.REQUIRED_GROUP_NAME = os.getenv("REQUIRED_GROUP_NAME", "").strip()
        self.REQUIRED_GROUP_LINK = os.getenv("REQUIRED_GROUP_LINK", "").strip()
        self.REQUIRED_GROUP_ID = self._parse_required_group_id(required_group_id_raw)
        self.GROUP_CHECK_ENABLED = bool(
            self.REQUIRED_GROUP_ID and self.REQUIRED_GROUP_NAME and self.REQUIRED_GROUP_LINK
        )
        if required_group_id_raw and not self.REQUIRED_GROUP_ID:
            logger.warning(f"无效的 REQUIRED_GROUP_ID: {required_group_id_raw}")
        if self.REQUIRED_GROUP_ID and not self.GROUP_CHECK_ENABLED:
            logger.warning("群组验证已关闭：REQUIRED_GROUP_NAME 或 REQUIRED_GROUP_LINK 未配置")
        
        # 群组工作模式配置（允许机器人在这些群组中直接响应 @提及）
        # 支持逗号分隔的多个群组 ID，例如：-1001234567890,-1009876543210
        self.ALLOWED_GROUP_IDS = self._parse_group_ids(os.getenv("ALLOWED_GROUP_IDS", ""))
        
        # 数据源URL
        # 使用 Aethersailor GeoIP 数据库
        self.GEOIP_URLS = [
            "https://gcore.jsdelivr.net/gh/Aethersailor/geoip@release/Country-without-asn.mmdb",
            "https://testingcf.jsdelivr.net/gh/Aethersailor/geoip@release/Country-without-asn.mmdb",
            "https://raw.githubusercontent.com/Aethersailor/geoip/release/Country-without-asn.mmdb",
        ]
        self.CN_IPV4_URLS = [
            "https://raw.githubusercontent.com/Aethersailor/geoip/refs/heads/release/text/cn-ipv4.txt",
            "https://gcore.jsdelivr.net/gh/Aethersailor/geoip@release/text/cn-ipv4.txt",
            "https://testingcf.jsdelivr.net/gh/Aethersailor/geoip@release/text/cn-ipv4.txt",
        ]
        self.GEOSITE_URL = "https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/refs/heads/release/direct-list.txt"
        
        # DoH服务器配置
        # 用于A记录查询（使用国内服务器获得准确的中国IP）
        default_doh_servers = {
            "alibaba": "https://dns.alidns.com/dns-query",
            "tencent": "https://doh.pub/dns-query",
            "cloudflare": "https://cloudflare-dns.com/dns-query"
        }
        self.DOH_SERVERS = self._parse_doh_servers(
            os.getenv("DOH_SERVERS", ""),
            default_doh_servers
        )
        
        # 用于NS记录查询（使用国际服务器避免审查）
        default_ns_doh_servers = {
            "cloudflare": "https://cloudflare-dns.com/dns-query",
            "google": "https://dns.google/dns-query",
            "quad9": "https://dns.quad9.net/dns-query"
        }
        self.NS_DOH_SERVERS = self._parse_doh_servers(
            os.getenv("NS_DOH_SERVERS", ""),
            default_ns_doh_servers
        )
        
        # 数据更新间隔（秒）
        self.DATA_UPDATE_INTERVAL = self._parse_update_interval(
            os.getenv("DATA_UPDATE_INTERVAL", "")
        )
    
    def _get_env_required(self, key: str) -> str:
        """获取必需的环境变量"""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    def _parse_group_ids(self, ids_str: str) -> list:
        """解析群组 ID 列表
        
        Args:
            ids_str: 逗号分隔的群组 ID 字符串
            
        Returns:
            群组 ID 整数列表
        """
        if not ids_str.strip():
            return []

        group_ids = []
        for raw_id in ids_str.split(","):
            raw_id = raw_id.strip()
            if not raw_id:
                continue
            try:
                group_ids.append(int(raw_id))
            except ValueError:
                logger.warning(f"无效的 ALLOWED_GROUP_IDS: {raw_id}")
        return group_ids

    def _parse_required_group_id(self, group_id_raw: str) -> Optional[int]:
        """解析必需群组 ID"""
        if not group_id_raw:
            return None
        try:
            return int(group_id_raw)
        except ValueError:
            return None

    def _parse_update_interval(self, value: str) -> int:
        """解析数据更新间隔（秒）"""
        default_interval = 6 * 60 * 60
        if not value:
            return default_interval
        try:
            interval = int(value)
            if interval <= 0:
                raise ValueError
            return interval
        except ValueError:
            logger.warning(f"无效的 DATA_UPDATE_INTERVAL: {value}，使用默认值 {default_interval}")
            return default_interval

    def _parse_doh_servers(self, value: str, defaults: Dict[str, str]) -> Dict[str, str]:
        """解析 DOH 服务器配置"""
        if not value.strip():
            return defaults

        servers: Dict[str, str] = {}
        parts = [item.strip() for item in value.split(",") if item.strip()]
        for index, part in enumerate(parts, 1):
            if "=" in part:
                name, url = part.split("=", 1)
                name = name.strip() or f"server{index}"
            else:
                name = f"server{index}"
                url = part

            url = url.strip()
            if not url.startswith("https://"):
                logger.warning(f"无效的 DOH 服务器地址（必须是 https://）: {url}")
                continue
            servers[name] = url

        if not servers:
            logger.warning("未解析到有效 DOH 服务器配置，使用默认值")
            return defaults

        return servers
