"""
群组消息处理器
处理群组内 @机器人 的消息，自动提取域名并查询/添加
"""

from typing import Optional
from loguru import logger

from telegram import Update, Message
from telegram.ext import ContextTypes

from ..config import Config
from ..data_manager import DataManager
from ..utils.text_extractor import extract_domain_for_rules, remove_bot_mention
from ..utils.domain_utils import is_cn_domain


class GroupHandler:
    """群组消息处理器"""
    
    def __init__(self, config: Config, data_manager: DataManager, handler_manager):
        """初始化群组处理器
        
        Args:
            config: 配置对象
            data_manager: 数据管理器
            handler_manager: 主处理器管理器（用于复用服务和核心逻辑）
        """
        self.config = config
        self.data_manager = data_manager
        self.handler_manager = handler_manager
        
        # 缓存机器人用户名（在第一次处理消息时获取）
        self._bot_username: Optional[str] = None
    
    def is_group_allowed(self, chat_id: int) -> bool:
        """检查群组是否在白名单中
        
        Args:
            chat_id: 群组 ID
            
        Returns:
            是否允许在该群组工作
        """
        return chat_id in self.config.ALLOWED_GROUP_IDS
    
    def is_bot_mentioned(self, message: Message, bot_username: str) -> bool:
        """检查消息是否 @了机器人
        
        Args:
            message: 消息对象
            bot_username: 机器人用户名
            
        Returns:
            是否提及了机器人
        """
        if not message.text:
            return False
        
        # 检查 entities 中是否有 mention 类型指向机器人
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    mention_text = message.text[entity.offset:entity.offset + entity.length]
                    if mention_text.lower() == f"@{bot_username.lower()}":
                        return True
        
        # 备用检查：直接在文本中查找
        return f"@{bot_username}".lower() in message.text.lower()
    
    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理群组消息主入口
        
        Args:
            update: Telegram 更新对象
            context: 上下文对象
        """
        try:
            message = update.effective_message
            chat = update.effective_chat
            user = update.effective_user
            
            # 添加入口日志，确认消息被接收
            logger.info(f"[群组处理器] 收到消息 - 群组: {chat.id if chat else 'None'}, "
                       f"用户: {user.id if user else 'None'}, "
                       f"消息: {message.text[:50] if message and message.text else 'None'}...")
            
            # 基本检查
            if not message or not chat or not user:
                logger.warning("[群组处理器] 消息/群组/用户对象为空")
                return
            
            # 只处理群组消息
            if chat.type not in ["group", "supergroup"]:
                logger.debug(f"[群组处理器] 非群组消息，类型: {chat.type}")
                return
            
            # 检查群组是否在白名单
            logger.debug(f"[群组处理器] 检查白名单 - 群组ID: {chat.id}, 白名单: {self.config.ALLOWED_GROUP_IDS}")
            if not self.is_group_allowed(chat.id):
                logger.debug(f"[群组处理器] 群组 {chat.id} 不在白名单中，忽略消息")
                return
            
            logger.info(f"[群组处理器] 群组 {chat.id} 在白名单中，继续处理")
            
            # 获取机器人用户名（首次获取后缓存）
            if not self._bot_username:
                bot = await context.bot.get_me()
                self._bot_username = bot.username
                logger.info(f"[群组处理器] 获取机器人用户名: @{self._bot_username}")
            
            # 检查是否 @了机器人
            is_mentioned = self.is_bot_mentioned(message, self._bot_username)
            logger.debug(f"[群组处理器] 是否提及机器人: {is_mentioned}, 消息内容: {message.text}")
            
            if not is_mentioned:
                logger.debug(f"[群组处理器] 消息未提及机器人，忽略")
                return
            
            logger.info(f"[群组处理器] 群组 {chat.id} 用户 {user.id}(@{user.username}) 提及了机器人")
            
            # 提取域名
            domain = await self._extract_domain_from_message(message)
            
            if not domain:
                # 未找到有效域名
                await message.reply_text(
                    "❌ **未找到有效域名**\n\n"
                    "💡 请在消息中包含域名，或回复包含域名的消息后 @我\n\n"
                    "📝 支持格式：\n"
                    "• `example.com`\n"
                    "• `https://example.com/path`\n"
                    "• `www.example.com`",
                    parse_mode='Markdown'
                )
                return
            
            # 检查是否为 .cn 域名
            if is_cn_domain(domain):
                await message.reply_text(
                    f"ℹ️ **域名 `{domain}` 为 .cn 域名**\n\n"
                    "📋 所有 .cn 域名默认直连，无需手动添加。",
                    parse_mode='Markdown'
                )
                return
            
            # 获取用户名用于 commit
            username = user.username or user.first_name or str(user.id)
            
            # 执行域名处理
            await self._process_domain_request(message, domain, username, user.id)
            
        except Exception as e:
            logger.error(f"处理群组消息失败: {e}")
            try:
                await update.effective_message.reply_text("❌ 处理失败，请稍后重试。")
            except Exception:
                pass
    
    async def _extract_domain_from_message(self, message: Message) -> Optional[str]:
        """从消息中提取域名（支持回复消息）
        
        优先从当前消息提取，如果当前消息无域名且是回复消息，则从被回复消息提取
        
        Args:
            message: 消息对象
            
        Returns:
            提取到的域名（二级域名格式），或 None
        """
        # 移除 @机器人 提及后提取域名
        text = message.text or ""
        clean_text = remove_bot_mention(text, self._bot_username) if self._bot_username else text
        
        # 1. 先从当前消息提取
        domain = extract_domain_for_rules(clean_text)
        if domain:
            logger.debug(f"从当前消息提取到域名: {domain}")
            return domain
        
        # 2. 如果当前消息无域名，检查是否是回复消息
        if message.reply_to_message:
            reply_text = message.reply_to_message.text or ""
            domain = extract_domain_for_rules(reply_text)
            if domain:
                logger.debug(f"从回复消息提取到域名: {domain}")
                return domain
        
        return None
    
    async def _process_domain_request(
        self, 
        message: Message, 
        domain: str, 
        username: str,
        user_id: int
    ):
        """处理域名请求：查询 + 自动添加
        
        Args:
            message: 消息对象（用于回复）
            domain: 待处理的域名
            username: 用户名（用于 commit）
            user_id: 用户 ID（用于频率限制）
        """
        try:
            # 发送处理中消息
            processing_msg = await message.reply_text(f"🔍 正在检查域名 `{domain}`...", parse_mode='Markdown')
            
            # 检查用户添加频率限制
            can_add, remaining = self.handler_manager.check_user_add_limit(user_id)
            if not can_add:
                await processing_msg.edit_text(
                    f"⚠️ **添加频率限制**\n\n"
                    f"您在当前小时内已达到添加上限（{self.handler_manager.MAX_ADDS_PER_HOUR}个域名）。\n\n"
                    "🕐 请等待一小时后再尝试。",
                    parse_mode='Markdown'
                )
                return
            
            # 调用核心逻辑进行检查和添加
            result = await self.handler_manager.check_and_add_domain_auto(domain, username)
            
            # 根据结果回复
            if result["action"] == "added":
                # 记录用户添加历史
                self.handler_manager.record_user_add(user_id)
                _, remaining = self.handler_manager.check_user_add_limit(user_id)
                
                result_text = f"✅ **域名添加成功！**\n\n"
                result_text += f"📍 **域名：** `{domain}`\n"
                result_text += f"👤 **提交者：** @{username}\n"
                if result.get("commit_url"):
                    result_text += f"🔗 **查看提交：** [点击查看]({result['commit_url']})\n"
                result_text += f"\n💡 本小时内还可添加 {remaining} 个域名"
                
            elif result["action"] == "exists":
                result_text = f"ℹ️ **域名已存在**\n\n"
                result_text += f"📍 **域名：** `{domain}`\n"
                result_text += f"📋 {result['message']}"
                
            elif result["action"] == "rejected":
                result_text = f"❌ **无法添加域名**\n\n"
                result_text += f"📍 **域名：** `{domain}`\n"
                result_text += f"📋 {result['message']}"
                
            else:  # error
                result_text = f"❌ **处理失败**\n\n"
                result_text += f"📍 **域名：** `{domain}`\n"
                result_text += f"❌ {result['message']}"
            
            await processing_msg.edit_text(result_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"处理域名请求失败: {e}")
            await message.reply_text(f"❌ 处理域名 `{domain}` 时出错，请稍后重试。", parse_mode='Markdown')
