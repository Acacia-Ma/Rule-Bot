"""
GeoIP 服务模块
用于查询 IP 地址的地理位置
"""

import socket
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
    
    def __init__(self, geoip_file_path: str):
        self.geoip_file = Path(geoip_file_path)
        self.reader = None
        self._load_data()
    
    def _load_data(self):
        """加载 GeoIP 数据"""
        try:
            if not GEOIP2_AVAILABLE:
                logger.warning("geoip2 库未安装，将使用简化的 IP 范围检查")
                return
                
            if not self.geoip_file.exists():
                logger.warning(f"GeoIP 数据库文件不存在: {self.geoip_file}")
                logger.info("提示：请从 https://dev.maxmind.com/geoip/geolite2-free-geolocation-data 下载 GeoLite2-Country.mmdb")
                return
            
            # 打开 MaxMind DB
            self.reader = geoip2.database.Reader(str(self.geoip_file))
            logger.info(f"GeoIP 数据库加载成功: {self.geoip_file}")
            
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
                    return response.country.iso_code
                except geoip2.errors.AddressNotFoundError:
                    logger.debug(f"IP {ip} 未在 GeoIP 数据库中找到")
                    return None
                except Exception as e:
                    logger.warning(f"GeoIP 查询失败: {e}")
                    return None
            
            # 回退到简化的中国 IP 段检查（仅作为备用）
            return self._fallback_china_check(ip)
            
        except Exception as e:
            logger.error(f"查询 IP 地理位置失败: {e}")
            return None
    
    def _fallback_china_check(self, ip: str) -> Optional[str]:
        """备用方案：简化的中国 IP 段检查"""
        try:
            ip_parts = list(map(int, ip.split('.')))
            first_octet = ip_parts[0]
            
            # 扩展的中国 IP 段列表（第一个八位字节）
            china_first_octets = [
                1, 2, 14, 27, 36, 39, 42, 43, 45, 46, 47, 49,
                58, 59, 60, 61, 101, 103, 106, 110, 111, 112, 113, 114, 115,
                116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 130, 131,
                133, 134, 137, 139, 140, 144, 150, 153, 157, 159, 161, 163,
                166, 167, 168, 169, 171, 175, 180, 182, 183, 202, 203, 210,
                211, 218, 219, 220, 221, 222, 223
            ]
            
            if first_octet in china_first_octets:
                return "CN"
            
            # 默认返回 None 表示未知
            return None
            
        except Exception:
            return None
    
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
 
