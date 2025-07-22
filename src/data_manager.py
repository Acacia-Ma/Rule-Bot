"""
数据管理模块
负责下载和管理GeoIP、GeoSite数据
"""

import asyncio
import aiohttp
import schedule
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set, List
from loguru import logger

from .config import Config
from .utils.domain_utils import extract_domain, extract_second_level_domain


class DataManager:
    """数据管理器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.geosite_domains: Set[str] = set()
        self.geosite_index: dict = {}  # 简单的内存索引
        # 使用临时目录，不需要持久化
        import tempfile
        self.data_dir = Path(tempfile.gettempdir()) / "rule-bot"
        self.geoip_file = self.data_dir / "geoip" / "geoip.dat"
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
            need_geoip = not self.geoip_file.exists() or self._is_file_outdated(self.geoip_file)
            need_geosite = not self.geosite_file.exists() or self._is_file_outdated(self.geosite_file)
            
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
        """加载GeoSite数据到内存并建立Redis索引"""
        try:
            if not self.geosite_file.exists():
                logger.warning("GeoSite文件不存在，跳过加载")
                return
            
            logger.info("加载GeoSite数据到内存...")
            domains = set()
            
            with open(self.geosite_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # 提取域名
                        if line.startswith('full:'):
                            domain = line[5:]
                        elif line.startswith('domain:'):
                            domain = line[7:]
                        else:
                            domain = line
                        
                        if domain:
                            domains.add(domain.lower())
                    
                    # 每10000行输出一次进度
                    if line_num % 10000 == 0:
                        logger.info(f"已处理 {line_num} 行GeoSite数据")
            
            self.geosite_domains = domains
            
            # 建立内存索引以便快速查询
            self._build_geosite_index()
            
            logger.info(f"GeoSite数据加载完成，共 {len(domains)} 个域名")
            
        except Exception as e:
            logger.error(f"GeoSite数据加载失败: {e}")
            raise
    
    def _build_geosite_index(self):
        """建立GeoSite内存索引"""
        try:
            logger.info("建立GeoSite内存索引...")
            
            # 清空旧索引
            self.geosite_index.clear()
            
            # 只为完整域名建立索引，不包括父域名
            for domain in self.geosite_domains:
                self.geosite_index[domain] = True
            
            logger.info(f"GeoSite内存索引建立完成，索引条目: {len(self.geosite_index)}")
            
        except Exception as e:
            logger.error(f"建立GeoSite索引失败: {e}")
    
    async def is_domain_in_geosite(self, domain: str) -> bool:
        """检查域名是否在GeoSite中"""
        try:
            domain = domain.lower().strip()
            
            # 1. 直接检查完整域名
            if domain in self.geosite_index:
                return True
            
            # 2. 检查是否为GeoSite中域名的子域名
            # 例如：查询 sub.example.com，检查 example.com 是否在GeoSite中
            parts = domain.split('.')
            for i in range(1, len(parts)):
                parent_domain = '.'.join(parts[i:])
                if parent_domain in self.geosite_index:
                    return True
            
            # 注意：不做反向检查，因为GeoSite通常只包含具体域名，不需要检查子域名覆盖父域名的情况
            
            return False
            
        except Exception as e:
            logger.error(f"检查GeoSite域名失败: {e}")
            return False
    
    def _is_file_outdated(self, file_path: Path, hours: int = 6) -> bool:
        """检查文件是否过期"""
        if not file_path.exists():
            return True
        
        file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
        return datetime.now() - file_time > timedelta(hours=hours)
    
    def _start_scheduled_updates(self):
        """启动定时更新任务"""
        def run_scheduler():
            schedule.every(6).hours.do(self._update_data_sync)
            
            while True:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
        
        # 在单独线程中运行调度器
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("定时更新任务已启动")
    
    def _update_data_sync(self):
        """同步版本的数据更新（用于scheduler）"""
        asyncio.create_task(self._update_data())
    
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