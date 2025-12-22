"""
配置管理模块
"""

import os
from typing import Optional


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
        self.GITHUB_COMMIT_EMAIL = os.getenv("GITHUB_COMMIT_EMAIL", "noreply@example.com")
        
        # 规则文件配置
        self.DIRECT_RULE_FILE = self._get_env_required("DIRECT_RULE_FILE")
        self.PROXY_RULE_FILE = os.getenv("PROXY_RULE_FILE", "")  # 可选，暂未启用
        
        # 日志配置
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING")
        
        # 群组验证配置
        self.REQUIRED_GROUP_ID = os.getenv("REQUIRED_GROUP_ID", "")
        self.REQUIRED_GROUP_NAME = os.getenv("REQUIRED_GROUP_NAME", "")
        self.REQUIRED_GROUP_LINK = os.getenv("REQUIRED_GROUP_LINK", "")
        
        # 数据源URL
        # 使用 Loyalsoldier GeoIP 数据库（针对中国 IP 优化）
        self.GEOIP_URL = "https://raw.githubusercontent.com/Loyalsoldier/geoip/release/Country-without-asn.mmdb"
        self.GEOSITE_URL = "https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/refs/heads/release/direct-list.txt"
        
        # DoH服务器配置
        # 用于A记录查询（使用国内服务器获得准确的中国IP）
        self.DOH_SERVERS = {
            "alibaba": "https://dns.alidns.com/dns-query",
            "tencent": "https://doh.pub/dns-query",
            "cloudflare": "https://1.1.1.1/dns-query"
        }
        
        # 用于NS记录查询（使用国际服务器避免审查）
        self.NS_DOH_SERVERS = {
            "cloudflare": "https://1.1.1.1/dns-query",
            "google": "https://8.8.8.8/dns-query",
            "quad9": "https://9.9.9.9/dns-query"
        }
        
        # 数据更新间隔（秒）
        self.DATA_UPDATE_INTERVAL = 6 * 60 * 60  # 6小时
    
    def _get_env_required(self, key: str) -> str:
        """获取必需的环境变量"""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value 