#!/usr/bin/env python3
"""
Rule-Bot Main Entry Point
Telegram机器人用于管理GitHub规则文件
"""

import asyncio
import os
import sys
import resource
import psutil
import time
from loguru import logger

from .bot import RuleBot
from .config import Config
from .data_manager import DataManager


def _configure_logging():
    """配置日志格式和级别"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_style = os.getenv("LOG_FORMAT", "compact").strip().lower()

    if log_style in ("verbose", "full", "detail"):
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )
    else:
        log_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | "
            "{module:<16}:{line:<4} | {message}"
        )

    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format=log_format,
        enqueue=True,
        backtrace=False,
        diagnose=False
    )


def set_memory_limit():
    """设置内存限制为256MB（软限制，超出时给出警告）"""
    try:
        # 256MB = 256 * 1024 * 1024 bytes
        memory_limit = 256 * 1024 * 1024
        # 设置软限制为256MB，硬限制为512MB（给一些缓冲空间）
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit * 2))
        logger.info(f"已设置内存软限制为 256MB，硬限制为 512MB")
        
        # 记录当前内存使用情况
        try:
            process = psutil.Process()
            current_memory = process.memory_info().rss
            logger.info(f"当前内存使用: {current_memory / 1024 / 1024:.1f}MB")
        except Exception as e:
            logger.warning(f"获取当前内存使用失败: {e}")
        
    except Exception as e:
        logger.warning(f"设置内存限制失败: {e}")
        # 内存限制设置失败不影响程序运行

def log_memory_usage():
    """记录内存使用情况，接近限制时给出警告"""
    # 初始化静态变量（只初始化一次）
    if not hasattr(log_memory_usage, '_initialized'):
        log_memory_usage.last_warning_time = 0
        log_memory_usage.last_warning_level = 0
        log_memory_usage.last_normal_log = 0
        log_memory_usage._initialized = True
    
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        # 边界检查，确保内存值合理
        if memory_mb < 0 or memory_mb > 1000:  # 如果内存值异常，记录但不处理
            logger.warning(f"内存值异常: {memory_mb:.1f}MB，跳过处理")
            return
        
        current_time = time.time()
        warning_cooldown = 300  # 5分钟内不重复相同级别的警告
        
        # 检查是否接近硬限制
        if memory_mb > 480:  # 接近512MB硬限制时紧急警告
            if current_time - log_memory_usage.last_warning_time > warning_cooldown or log_memory_usage.last_warning_level != 3:
                logger.error(f"🚨 内存使用危急: {memory_mb:.1f}MB (接近512MB硬限制，可能被系统终止)")
                # 尝试主动释放一些内存
                import gc
                gc.collect()
                logger.warning("已尝试垃圾回收释放内存")
                log_memory_usage.last_warning_time = current_time
                log_memory_usage.last_warning_level = 3
        elif memory_mb > 240:  # 接近256MB软限制时警告
            if current_time - log_memory_usage.last_warning_time > warning_cooldown or log_memory_usage.last_warning_level != 2:
                logger.warning(f"⚠️ 内存使用过高: {memory_mb:.1f}MB (接近256MB软限制)")
                log_memory_usage.last_warning_time = current_time
                log_memory_usage.last_warning_level = 2
        elif memory_mb > 200:  # 超过200MB时提醒
            if current_time - log_memory_usage.last_warning_time > warning_cooldown or log_memory_usage.last_warning_level != 1:
                logger.warning(f"⚠️ 内存使用较高: {memory_mb:.1f}MB")
                log_memory_usage.last_warning_time = current_time
                log_memory_usage.last_warning_level = 1
        else:
            # 正常时只记录一次，避免刷屏
            if current_time - log_memory_usage.last_normal_log > 3600:  # 1小时记录一次正常状态
                logger.info(f"内存使用正常: {memory_mb:.1f}MB")
                log_memory_usage.last_normal_log = current_time
                log_memory_usage.last_warning_level = 0
            
    except Exception as e:
        logger.warning(f"获取内存使用情况失败: {e}")

def main():
    """主程序入口"""
    try:
        # 配置日志（确保早期日志也使用统一格式）
        _configure_logging()

        # 设置内存限制
        set_memory_limit()
        
        # 初始化配置
        config = Config()
        
        logger.info("Rule-Bot 正在启动...")
        
        # 初始化数据管理器（在新的事件循环中）
        async def init_data():
            data_manager = DataManager(config)
            await data_manager.initialize()
            return data_manager
        
        data_manager = asyncio.run(init_data())
        
        # 记录数据加载后的内存使用
        log_memory_usage()
        
        # 初始化机器人
        bot = RuleBot(config, data_manager)
        
        # 启动机器人
        logger.info("启动Telegram机器人...")
        
        # 启动定期内存检查（每10分钟检查一次）
        import threading
        
        def memory_monitor():
            while True:
                try:
                    time.sleep(600)  # 10分钟
                    log_memory_usage()
                except Exception as e:
                    logger.warning(f"内存监控出错: {e}")
                    time.sleep(60)  # 出错后等待1分钟再继续
        
        monitor_thread = threading.Thread(target=memory_monitor, daemon=True)
        monitor_thread.start()
        
        bot.start()
        
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
    except Exception as e:
        logger.error(f"程序启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 
