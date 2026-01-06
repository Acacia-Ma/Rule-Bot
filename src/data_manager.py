"""
数据管理模块
负责下载和管理GeoIP、GeoSite数据
"""

import asyncio
import aiohttp
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set, List, Pattern
from loguru import logger

from .config import Config


class DataManager:
    """数据管理器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.geosite_domains: Set[str] = set()
        self.geosite_keywords: List[str] = []
        self.geosite_regex_patterns: List[Pattern[str]] = []
        self.geosite_includes: List[str] = []
        self._data_lock = threading.RLock()
        self._update_lock = threading.Lock()
        # 使用临时目录，不需要持久化
        import tempfile
        self.data_dir = Path(tempfile.gettempdir()) / "rule-bot"
        self.geoip_file = self.data_dir / "geoip" / "Country-without-asn.mmdb"
        self.geosite_file = self.data_dir / "geosite" / "direct-list.txt"
        
        # 确保目录存在
        self.data_dir.mkdir(exist_ok=True)
        (self.data_dir / "geoip").mkdir(exist_ok=True)
        (self.data_dir / "geosite").mkdir(exist_ok=True)
    
    async def initialize(self):
        """初始化数据管理器"""
        try:
            # 初始下载数据
            await self._download_initial_data()
            
            # 启动定时更新任务
            self._start_scheduled_updates()
            
            logger.info("数据管理器初始化完成")
            
        except Exception as e:
            logger.error(f"数据管理器初始化失败: {e}")
            raise
    
    async def _download_initial_data(self):
        """初始下载数据"""
        try:
            # 检查是否需要下载
            need_geoip = not self.geoip_file.exists() or self._is_file_outdated(
                self.geoip_file,
                self.config.DATA_UPDATE_INTERVAL
            )
            need_geosite = not self.geosite_file.exists() or self._is_file_outdated(
                self.geosite_file,
                self.config.DATA_UPDATE_INTERVAL
            )
            
            if need_geoip:
                logger.info("下载GeoIP数据...")
                await self._download_geoip()
            
            if need_geosite:
                logger.info("下载GeoSite数据...")
                await self._download_geosite()
            
            # 加载GeoSite数据到内存
            await self._load_geosite_data()
            
        except Exception as e:
            logger.error(f"初始数据下载失败: {e}")
            raise
    
    async def _download_geoip(self):
        """下载GeoIP数据"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.config.GEOIP_URL) as response:
                    if response.status == 200:
                        with open(self.geoip_file, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        logger.info("GeoIP数据下载完成")
                    else:
                        raise Exception(f"下载失败，状态码: {response.status}")
        except Exception as e:
            logger.error(f"GeoIP数据下载失败: {e}")
            raise
    
    async def _download_geosite(self):
        """下载GeoSite数据"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.config.GEOSITE_URL) as response:
                    if response.status == 200:
                        with open(self.geosite_file, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        logger.info("GeoSite数据下载完成")
                    else:
                        raise Exception(f"下载失败，状态码: {response.status}")
        except Exception as e:
            logger.error(f"GeoSite数据下载失败: {e}")
            raise
    
    async def _load_geosite_data(self):
        """加载GeoSite数据到内存"""
        try:
            if not self.geosite_file.exists():
                logger.warning("GeoSite文件不存在，跳过加载")
                return
            
            logger.info("加载GeoSite数据到内存...")
            domains: Set[str] = set()
            keywords: List[str] = []
            regex_patterns: List[Pattern[str]] = []
            includes: List[str] = []
            
            with open(self.geosite_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        domain = ""
                        if line.startswith('full:'):
                            domain = line[5:]
                        elif line.startswith('domain:'):
                            domain = line[7:]
                        elif line.startswith('keyword:'):
                            keyword = line[8:].strip()
                            if keyword:
                                keywords.append(keyword.lower())
                        elif line.startswith('regexp:'):
                            pattern = line[7:].strip()
                            if pattern:
                                try:
                                    regex_patterns.append(re.compile(pattern, re.IGNORECASE))
                                except re.error as e:
                                    logger.warning(f"无效的 GeoSite 正则: {pattern} ({e})")
                        elif line.startswith('include:') or line.startswith('geosite:'):
                            include_item = line.split(':', 1)[1].strip()
                            if include_item:
                                includes.append(include_item)
                        else:
                            domain = line
                        
                        if domain:
                            domains.add(domain.lower())
                    
                    # 每10000行输出一次进度
                    if line_num % 10000 == 0:
                        logger.info(f"已处理 {line_num} 行GeoSite数据")
            
            with self._data_lock:
                self.geosite_domains = domains
                self.geosite_keywords = keywords
                self.geosite_regex_patterns = regex_patterns
                self.geosite_includes = includes
            
            logger.info(
                "GeoSite数据加载完成，域名: {}, 关键字: {}, 正则: {}, include: {}",
                len(domains),
                len(keywords),
                len(regex_patterns),
                len(includes)
            )
            if includes:
                logger.warning("检测到 GeoSite include 规则，当前未展开解析")
            
        except Exception as e:
            logger.error(f"GeoSite数据加载失败: {e}")
            raise
    
    async def is_domain_in_geosite(self, domain: str) -> bool:
        """检查域名是否在GeoSite中"""
        try:
            domain = domain.lower().strip()
            if not domain:
                return False

            with self._data_lock:
                domain_set = self.geosite_domains
                keywords = self.geosite_keywords
                regex_patterns = self.geosite_regex_patterns
            
            # 1. 直接检查完整域名
            if domain in domain_set:
                return True
            
            # 2. 检查是否为GeoSite中域名的子域名
            # 例如：查询 sub.example.com，检查 example.com 是否在GeoSite中
            parts = domain.split('.')
            for i in range(1, len(parts)):
                parent_domain = '.'.join(parts[i:])
                if parent_domain in domain_set:
                    return True

            for keyword in keywords:
                if keyword and keyword in domain:
                    return True

            for pattern in regex_patterns:
                if pattern.search(domain):
                    return True
            
            # 注意：不做反向检查，因为GeoSite通常只包含具体域名，不需要检查子域名覆盖父域名的情况
            
            return False
            
        except Exception as e:
            logger.error(f"检查GeoSite域名失败: {e}")
            return False
    
    def _is_file_outdated(self, file_path: Path, max_age_seconds: int) -> bool:
        """检查文件是否过期"""
        if not file_path.exists():
            return True
        
        file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
        return datetime.now() - file_time > timedelta(seconds=max_age_seconds)
    
    def _start_scheduled_updates(self):
        """启动定时更新任务"""
        def run_scheduler():
            update_interval = self.config.DATA_UPDATE_INTERVAL
            while True:
                time.sleep(update_interval)
                self._update_data_sync()
        
        # 在单独线程中运行调度器
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("定时更新任务已启动")
    
    def _update_data_sync(self):
        """同步版本的数据更新（用于scheduler）"""
        if not self._update_lock.acquire(blocking=False):
            logger.info("已有更新任务在执行，跳过本次更新")
            return
        try:
            asyncio.run(self._update_data())
        except Exception as e:
            logger.error(f"同步更新执行失败: {e}")
        finally:
            self._update_lock.release()
    
    async def _update_data(self):
        """更新数据"""
        try:
            logger.info("开始定时更新数据...")
            
            # 下载新数据
            await self._download_geoip()
            await self._download_geosite()
            
            # 重新加载GeoSite数据
            await self._load_geosite_data()
            
            logger.info("定时更新完成")
            
        except Exception as e:
            logger.error(f"定时更新失败: {e}") 
