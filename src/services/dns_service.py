"""
DNS服务模块
使用DoH (DNS over HTTPS) 查询域名解析
"""

import aiohttp
import asyncio
import base64
import struct
import socket
from typing import List, Optional, Dict, Any
from loguru import logger


class DNSService:
    """DNS服务"""
    
    def __init__(self, doh_servers: Dict[str, str], ns_doh_servers: Dict[str, str] = None):
        self.doh_servers = doh_servers
        self.ns_doh_servers = ns_doh_servers or doh_servers
    
    async def query_a_record(self, domain: str, use_edns_china: bool = True) -> List[str]:
        """查询A记录，返回IP地址列表（并发查询所有DoH服务器）"""
        try:
            # 构建DNS查询数据包
            query_data = self._build_dns_query(domain, use_edns_china)
            
            # 创建所有DoH服务器的查询任务
            tasks = []
            for server_name, server_url in self.doh_servers.items():
                task = asyncio.create_task(
                    self._perform_doh_query(server_name, server_url, query_data, self._parse_dns_response_a)
                )
                tasks.append(task)
            
            # 等待所有任务完成，并获取第一个成功的结果
            # 注意：这里我们使用 as_completed 来获取最快的结果
            for future in asyncio.as_completed(tasks):
                try:
                    ips = await future
                    if ips:
                        logger.debug(f"DoH查询 {domain} 成功，获得 {len(ips)} 个IP")
                        # 取消其他未完成的任务
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        return ips
                except Exception:
                    # 单个任务失败不影响其他任务
                    continue
            
            logger.warning(f"所有DoH服务器查询域名 {domain} 都失败")
            return []
            
        except Exception as e:
            logger.error(f"DNS查询失败: {e}")
            return []
    
    async def query_ns_records(self, domain: str) -> List[str]:
        """查询NS记录，返回权威域名服务器列表（并发查询）"""
        try:
            # 构建NS查询数据包（不使用EDNS中国客户端，避免被过滤）
            query_data = self._build_dns_query(domain, False, record_type=2)  # NS记录类型为2
            
            # 创建所有NS DoH服务器的查询任务
            tasks = []
            for server_name, server_url in self.ns_doh_servers.items():
                task = asyncio.create_task(
                    self._perform_doh_query(server_name, server_url, query_data, self._parse_dns_response_ns)
                )
                tasks.append(task)
            
            # 等待最快的结果
            for future in asyncio.as_completed(tasks):
                try:
                    ns_servers = await future
                    if ns_servers:
                        logger.debug(f"DoH查询 {domain} NS记录成功")
                        # 取消其他任务
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        return ns_servers
                except Exception:
                    continue
            
            # DoH查询失败时，尝试使用系统DNS作为备用
            logger.info(f"DoH查询NS记录失败，尝试使用系统DNS查询 {domain}")
            ns_servers = await self._query_ns_system_dns(domain)
            if ns_servers:
                logger.debug(f"使用系统DNS查询 {domain} NS记录成功")
                return ns_servers
            
            logger.warning(f"所有NS记录查询方法都失败，域名: {domain}")
            return []
            
        except Exception as e:
            logger.error(f"NS记录查询失败: {e}")
            return []
    
    async def _perform_doh_query(self, server_name: str, server_url: str, query_data: bytes, parser_func) -> List[str]:
        """执行DoH查询通用方法"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                encoded_query = base64.urlsafe_b64encode(query_data).decode().rstrip('=')
                url = f"{server_url}?dns={encoded_query}"
                
                connector = aiohttp.TCPConnector(
                    limit=10,
                    limit_per_host=5,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                    ssl=False # 某些环境下可能需要忽略SSL验证，或者使用默认SSL上下文
                )
                
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(
                        url,
                        headers={
                            'Accept': 'application/dns-message',
                            'User-Agent': 'Rule-Bot DNS Client/1.0'
                        },
                        timeout=aiohttp.ClientTimeout(total=10, connect=3)
                    ) as response:
                        if response.status == 200:
                            response_data = await response.read()
                            result = parser_func(response_data)
                            if result:
                                return result
                            # 如果解析结果为空但状态码200，可能是没有该记录，不一定是错误，但也重试一下
                        else:
                            # logger.warning(f"{server_name} HTTP error: {response.status}")
                            pass
                            
            except asyncio.CancelledError:
                raise # 允许被取消
            except Exception as e:
                # logger.debug(f"{server_name} query failed (attempt {attempt+1}): {e}")
                pass
            
            # 如果不是最后一次尝试，等待一小会儿
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
        
        # 所有重试失败后抛出异常，以便外层捕捉
        raise Exception(f"{server_name} query failed after retries")
    
    def _parse_dns_response_a(self, response_data: bytes) -> List[str]:
        """解析DNS响应中的A记录"""
        try:
            if len(response_data) < 12:
                return []
            
            # 解析头部
            header = struct.unpack('!HHHHHH', response_data[:12])
            answer_count = header[3]
            
            if answer_count == 0:
                return []
            
            # 跳过查询部分
            offset = 12
            
            # 跳过查询名称
            while offset < len(response_data) and response_data[offset] != 0:
                length = response_data[offset]
                if length > 63:  # 压缩指针
                    offset += 2
                    break
                offset += length + 1
            
            if offset < len(response_data) and response_data[offset] == 0:
                offset += 1
            
            offset += 4  # 跳过Type和Class
            
            # 解析答案
            ips = []
            for _ in range(answer_count):
                if offset >= len(response_data):
                    break
                
                # 跳过名称
                if response_data[offset] & 0xC0:  # 压缩指针
                    offset += 2
                else:
                    while offset < len(response_data) and response_data[offset] != 0:
                        offset += response_data[offset] + 1
                    offset += 1
                
                if offset + 10 > len(response_data):
                    break
                
                # 读取Type, Class, TTL, RDLength
                rr_data = struct.unpack('!HHIH', response_data[offset:offset+10])
                rr_type = rr_data[0]
                rd_length = rr_data[3]
                offset += 10
                
                # 如果是A记录 (Type 1) 且长度为4
                if rr_type == 1 and rd_length == 4 and offset + 4 <= len(response_data):
                    ip_bytes = response_data[offset:offset+4]
                    ip = '.'.join(str(b) for b in ip_bytes)
                    ips.append(ip)
                
                offset += rd_length
            
            return ips
            
        except Exception as e:
            logger.error(f"解析DNS响应失败: {e}")
            return []
    
    def _parse_dns_response_ns(self, response_data: bytes) -> List[str]:
        """解析DNS响应中的NS记录"""
        try:
            if len(response_data) < 12:
                return []
            
            # 解析头部
            header = struct.unpack('!HHHHHH', response_data[:12])
            answer_count = header[3]
            
            if answer_count == 0:
                return []
            
            # 跳过查询部分
            offset = 12
            
            # 跳过查询名称
            while offset < len(response_data) and response_data[offset] != 0:
                length = response_data[offset]
                if length > 63:  # 压缩指针
                    offset += 2
                    break
                offset += length + 1
            
            if offset < len(response_data) and response_data[offset] == 0:
                offset += 1
            
            offset += 4  # 跳过Type和Class
            
            # 解析答案
            ns_servers = []
            for _ in range(answer_count):
                if offset >= len(response_data):
                    break
                
                # 跳过名称
                if offset < len(response_data) and response_data[offset] & 0xC0:  # 压缩指针
                    offset += 2
                else:
                    while offset < len(response_data) and response_data[offset] != 0:
                        offset += response_data[offset] + 1
                    if offset < len(response_data):
                        offset += 1
                
                if offset + 10 > len(response_data):
                    break
                
                # 读取Type, Class, TTL, RDLength
                rr_data = struct.unpack('!HHIH', response_data[offset:offset+10])
                rr_type = rr_data[0]
                rd_length = rr_data[3]
                offset += 10
                
                # 如果是NS记录 (Type 2)
                if rr_type == 2 and offset + rd_length <= len(response_data):
                    ns_name = self._parse_domain_name(response_data, offset)
                    if ns_name:
                        ns_servers.append(ns_name)
                
                offset += rd_length
            
            return ns_servers
            
        except Exception as e:
            logger.error(f"解析NS记录失败: {e}")
            return []
    
    def _parse_domain_name(self, data: bytes, offset: int) -> str:
        """解析DNS响应中的域名（处理压缩指针）"""
        try:
            labels = []
            original_offset = offset
            jumped = False
            
            while offset < len(data):
                length = data[offset]
                
                if length == 0:
                    break
                elif length & 0xC0 == 0xC0:  # 压缩指针
                    if not jumped:
                        original_offset = offset + 2
                        jumped = True
                    # 计算指针位置
                    pointer = ((length & 0x3F) << 8) | data[offset + 1]
                    offset = pointer
                    continue
                else:
                    offset += 1
                    if offset + length > len(data):
                        break
                    label = data[offset:offset + length].decode('ascii', errors='ignore')
                    labels.append(label)
                    offset += length
            
            domain = '.'.join(labels)
            return domain if domain else ""
            
        except Exception as e:
            logger.error(f"解析域名失败: {e}")
            return "" 