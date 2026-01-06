"""
Telegram机器人主控制器
"""

import asyncio
from typing import Optional
from loguru import logger

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

from .config import Config
from .data_manager import DataManager
from .handlers import HandlerManager, GroupHandler


class RuleBot:
    """Rule-Bot主控制器"""
    
    def __init__(self, config: Config, data_manager: DataManager):
        self.config = config
        self.data_manager = data_manager
        self.app: Optional[Application] = None
        self.handler_manager = None  # 延迟初始化
        self.group_handler = None  # 群组处理器
    
    async def stop(self):
        """停止机器人"""
        logger.info("正在停止机器人...")
        if self.handler_manager:
            await self.handler_manager.stop()
        if self.app:
            await self.app.stop()
            await self.app.shutdown()
        logger.info("机器人已停止")

    def start(self):
        """启动机器人"""
        try:
            # 创建应用
            self.app = Application.builder().token(self.config.TELEGRAM_BOT_TOKEN).build()
            
            # 初始化处理器管理器（需要app实例）
            self.handler_manager = HandlerManager(self.config, self.data_manager, self.app)
            
            # 初始化群组处理器
            self.group_handler = GroupHandler(self.config, self.data_manager, self.handler_manager)
            
            # 注册处理器
            self._register_handlers()
            
            # 启动轮询
            logger.info("机器人启动成功，开始轮询...")
            
            # 在新的事件循环中运行机器人
            import asyncio
            
            async def run_bot():
                try:
                    async with self.app:
                        await self.handler_manager.start()  # 显式启动服务（如DNS Session）
                        await self.app.start()
                        await self.app.updater.start_polling(
                            allowed_updates=Update.ALL_TYPES,
                            drop_pending_updates=True  # 丢弃待处理的更新，避免发送旧消息
                        )
                        # 保持运行
                        await asyncio.Event().wait()
                finally:
                    await self.stop()
            
            # 使用新的事件循环运行
            asyncio.run(run_bot())
            
        except Exception as e:
            logger.error(f"机器人启动失败: {e}")
            raise
    
    def _register_handlers(self):
        """注册所有处理器"""
        # 命令处理器
        self.app.add_handler(CommandHandler("start", self.handler_manager.start_command))
        self.app.add_handler(CommandHandler("help", self.handler_manager.help_command))
        self.app.add_handler(CommandHandler("query", self.handler_manager.query_command))
        self.app.add_handler(CommandHandler("add", self.handler_manager.add_command))
        self.app.add_handler(CommandHandler("delete", self.handler_manager.delete_command))
        self.app.add_handler(CommandHandler("skip", self.handler_manager.skip_command))
        
        # 回调查询处理器
        self.app.add_handler(CallbackQueryHandler(self.handler_manager.handle_callback))
        
        # 群组消息处理器（处理群组中 @机器人 的消息）
        # 注意：需要在私聊消息处理器之前注册，使用 group 参数设置优先级
        if self.config.ALLOWED_GROUP_IDS:
            self.app.add_handler(MessageHandler(
                filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND & filters.Entity("mention"),
                self.group_handler.handle_group_message
            ), group=0)
            logger.info(f"群组工作模式已启用，允许的群组: {self.config.ALLOWED_GROUP_IDS}")
        
        # 私聊消息处理器（用于处理用户输入）
        self.app.add_handler(MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, 
            self.handler_manager.handle_message
        ))
        
        logger.info("所有处理器注册完成") 
