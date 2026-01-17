"""
GeoIP 服务模块
用于查询 IP 地址的地理位置
"""

import socket
import ipaddress
from bisect import bisect_right
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger

try:
    import geoip2.database
    GEOIP2_AVAILABLE = True
except ImportError:
    GEOIP2_AVAILABLE = False
    logger.warning("geoip2 库未安装，GeoIP 功能将受限")


class GeoIPService:
    """GeoIP 服务"""
    
    def __init__(self, geoip_file_path: str, cn_ipv4_file_path: Optional[str] = None):
        self.geoip_file = Path(geoip_file_path)
        self.cn_ipv4_file = Path(cn_ipv4_file_path) if cn_ipv4_file_path else None
        self.reader = None
        self._cn_ipv4_ranges = []
        self._cn_ipv4_range_starts = []
        self._load_data()
    
    def _load_data(self):
        """加载 GeoIP 数据"""
        try:
            if not GEOIP2_AVAILABLE:
                logger.warning("geoip2 库未安装，将使用中国 IPv4 CIDR 列表检查")
            elif not self.geoip_file.exists():
                logger.warning(f"GeoIP 数据库文件不存在: {self.geoip_file}")
            else:
                # 打开 MaxMind DB
                self.reader = geoip2.database.Reader(str(self.geoip_file))
                logger.info(f"GeoIP 数据库加载成功: {self.geoip_file}")

            self._load_cn_ipv4()
            
        except Exception as e:
            logger.error(f"加载 GeoIP 数据失败: {e}")
    
    def get_country_code(self, ip: str) -> Optional[str]:
        """获取 IP 的国家代码"""
        try:
            # 验证 IP 格式
            socket.inet_aton(ip)
            
            # 如果有真实的 GeoIP2 数据库
            if self.reader:
                try:
                    response = self.reader.country(ip)
                    country_code = response.country.iso_code
                    if not country_code:
                        country_code = (
                            response.registered_country.iso_code
                            or response.represented_country.iso_code
                        )
                    if country_code:
                        return country_code
                except geoip2.errors.AddressNotFoundError:
                    logger.debug(f"IP {ip} 未在 GeoIP 数据库中找到")
                except Exception as e:
                    logger.warning(f"GeoIP 查询失败: {e}")
                # 数据库缺失记录或查询失败时，回退到简化的中国 IP 段判断
                return self._fallback_china_check(ip)
            
            # 回退到简化的中国 IP 段检查（仅作为备用）
            return self._fallback_china_check(ip)
            
        except Exception as e:
            logger.error(f"查询 IP 地理位置失败: {e}")
            return None
    
    def _fallback_china_check(self, ip: str) -> Optional[str]:
        """备用方案：使用中国 IPv4 CIDR 列表检查"""
        try:
            if not self._cn_ipv4_ranges:
                return None

            ip_int = int(ipaddress.IPv4Address(ip))
            index = bisect_right(self._cn_ipv4_range_starts, ip_int) - 1
            if index >= 0 and ip_int <= self._cn_ipv4_ranges[index][1]:
                return "CN"
            return None
            
        except Exception:
            return None

    def _load_cn_ipv4(self):
        """加载中国 IPv4 CIDR 列表"""
        if not self.cn_ipv4_file:
            return
        if not self.cn_ipv4_file.exists():
            logger.warning(f"中国 IPv4 CIDR 文件不存在: {self.cn_ipv4_file}")
            return

        try:
            ranges = []
            with open(self.cn_ipv4_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    try:
                        network = ipaddress.ip_network(line, strict=False)
                    except ValueError:
                        logger.debug(f"无效的 CIDR 记录: {line}")
                        continue
                    if isinstance(network, ipaddress.IPv4Network):
                        start = int(network.network_address)
                        end = int(network.broadcast_address)
                        ranges.append((start, end))

            if not ranges:
                logger.warning("中国 IPv4 CIDR 数据为空，回退检查不可用")
                return

            ranges.sort(key=lambda item: item[0])
            merged = []
            for start, end in ranges:
                if not merged or start > merged[-1][1] + 1:
                    merged.append([start, end])
                else:
                    merged[-1][1] = max(merged[-1][1], end)

            self._cn_ipv4_ranges = [(start, end) for start, end in merged]
            self._cn_ipv4_range_starts = [start for start, _ in self._cn_ipv4_ranges]
            logger.info("中国 IPv4 CIDR 数据加载完成: {} 段", len(self._cn_ipv4_ranges))
        except Exception as e:
            logger.error(f"加载中国 IPv4 CIDR 数据失败: {e}")
    
    def is_china_ip(self, ip: str) -> bool:
        """检查是否为中国 IP"""
        country_code = self.get_country_code(ip)
        return country_code == "CN"
    
    def get_location_info(self, ip: str) -> Dict[str, Any]:
        """获取 IP 的详细位置信息"""
        try:
            country_code = self.get_country_code(ip)
            
            # 如果使用真实数据库且找到结果
            if self.reader and country_code:
                try:
                    response = self.reader.country(ip)
                    country_name = response.country.names.get('zh-CN') or response.country.name or "未知"
                    
                    return {
                        "ip": ip,
                        "country_code": country_code,
                        "country_name": country_name,
                        "is_china": country_code == "CN"
                    }
                except Exception:
                    pass
            
            # 回退到简单映射
            country_names = {
                "CN": "中国",
                "US": "美国",
                "JP": "日本",
                "KR": "韩国",
                "SG": "新加坡",
                "HK": "香港",
                "TW": "台湾",
                "GB": "英国",
                "DE": "德国",
                "FR": "法国",
            }
            
            return {
                "ip": ip,
                "country_code": country_code,
                "country_name": country_names.get(country_code, "未知" if country_code else "未知"),
                "is_china": country_code == "CN" if country_code else False
            }
            
        except Exception as e:
            logger.error(f"获取 IP 位置信息失败: {e}")
            return {
                "ip": ip,
                "country_code": None,
                "country_name": "未知",
                "is_china": False
            }
    
    def __del__(self):
        """关闭数据库连接"""
        if self.reader:
            try:
                self.reader.close()
            except Exception:
                pass
 
