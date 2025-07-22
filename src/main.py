#!/usr/bin/env python3
"""
Rule-Bot Main Entry Point
Telegram机器人用于管理GitHub规则文件
"""

import asyncio
import os
import sys
from loguru import logger

from .bot import RuleBot
from .config import Config
from .data_manager import DataManager


def main():
    """主程序入口"""
    try:
        # 初始化配置
        config = Config()
        
        # 配置日志
        logger.remove()
        logger.add(
            sys.stderr,
            level=config.LOG_LEVEL,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
        # 日志只输出到stderr，不需要文件持久化
        
        logger.info("Rule-Bot 正在启动...")
        
        # 初始化数据管理器（在新的事件循环中）
        async def init_data():
            data_manager = DataManager(config)
            await data_manager.initialize()
            return data_manager
        
        data_manager = asyncio.run(init_data())
        
        # 初始化机器人
        bot = RuleBot(config, data_manager)
        
        # 启动机器人
        logger.info("启动Telegram机器人...")
        bot.start()
        
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
    except Exception as e:
        logger.error(f"程序启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 