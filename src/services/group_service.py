"""
群组验证服务
检查用户是否加入指定群组
"""

from typing import Optional
from loguru import logger
from telegram import Bot
from telegram.error import TelegramError

from ..config import Config


class GroupService:
    """群组验证服务"""
    
    def __init__(self, config: Config, bot: Bot):
        self.config = config
        self.bot = bot
        self._group_check_enabled = bool(getattr(config, "GROUP_CHECK_ENABLED", False))
    
    def is_group_check_enabled(self) -> bool:
        """检查是否启用群组验证"""
        return self._group_check_enabled
    
    async def check_user_in_group(self, user_id: int) -> Optional[bool]:
        """检查用户是否在指定群组中"""
        if not self._group_check_enabled:
            return True  # 功能关闭时默认通过
        
        try:
            chat_member = await self.bot.get_chat_member(
                chat_id=self.config.REQUIRED_GROUP_ID,
                user_id=user_id
            )
            
            # 检查用户状态
            valid_statuses = ['member', 'administrator', 'creator']
            is_member = chat_member.status in valid_statuses
            
            logger.debug(f"用户 {user_id} 群组状态: {chat_member.status}, 是否为成员: {is_member}")
            return is_member

        except TelegramError as e:
            logger.warning(f"检查用户 {user_id} 群组成员身份失败: {e}")
            return None
        except Exception as e:
            logger.warning(f"检查用户 {user_id} 群组成员身份失败: {e}")
            return None
    
    def get_join_group_message(self) -> str:
        """获取加入群组的提示消息"""
        if not self._group_check_enabled:
            return ""
        
        message = f"🔒 **使用限制**\n\n"
        message += f"为了使用本机器人，请先加入我们的群组：\n\n"
        message += f"📢 **群组名称：** {self.config.REQUIRED_GROUP_NAME}\n"
        message += f"🔗 **加入链接：** {self.config.REQUIRED_GROUP_LINK}\n\n"
        message += f"加入后请重新尝试使用机器人功能。"
        
        return message 
