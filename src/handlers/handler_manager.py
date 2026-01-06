"""
处理器管理器
统一管理所有Telegram消息处理逻辑
"""

import asyncio
import time
from typing import Dict, Any, Optional
from collections import defaultdict
from loguru import logger

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..config import Config
from ..data_manager import DataManager
from ..services.dns_service import DNSService
from ..services.geoip_service import GeoIPService
from ..services.github_service import GitHubService
from ..services.domain_checker import DomainChecker
from ..services.group_service import GroupService
from ..utils.domain_utils import normalize_domain, extract_second_level_domain, extract_second_level_domain_for_rules, is_cn_domain


class HandlerManager:
    """处理器管理器"""
    
    def __init__(self, config: Config, data_manager: DataManager, application=None):
        self.config = config
        self.data_manager = data_manager
        
        # 初始化服务
        self.dns_service = DNSService(config.DOH_SERVERS, config.NS_DOH_SERVERS)
        self.geoip_service = GeoIPService(str(data_manager.geoip_file))
        self.github_service = GitHubService(config)
        self.domain_checker = DomainChecker(self.dns_service, self.geoip_service)
        
        # 群组服务（需要bot实例）
        self.group_service = None
        if application:
            self.group_service = GroupService(config, application.bot)

    async def start(self):
        """启动服务"""
        if self.dns_service:
            await self.dns_service.start()
        
        # 用户状态管理
        self.user_states: Dict[int, Dict[str, Any]] = {}
        
        # 用户限制管理
        self.user_add_history: Dict[int, list] = defaultdict(list)  # 用户添加历史 {user_id: [timestamp1, timestamp2, ...]}
        self.MAX_DESCRIPTION_LENGTH = 20  # 域名说明最大字符数
        self.MAX_ADDS_PER_HOUR = 50  # 每小时最多添加域名数
        self.MAX_DETAIL_LINES = 6  # 检查详情最大行数
        self.MAX_DETAIL_LINE_LENGTH = 120  # 单行详情最大长度

    async def stop(self):
        """停止服务"""
        if self.dns_service:
            await self.dns_service.close()

    async def check_and_add_domain_auto(
        self, 
        domain: str, 
        username: str, 
        description: str = ""
    ) -> dict:
        """自动检查并添加域名（无需用户确认）
        
        供群组处理器调用，实现一步完成的域名检查和添加流程
        
        Args:
            domain: 待添加的域名（应为二级域名格式）
            username: 用户名（用于 commit 记录）
            description: 域名说明（可选）
            
        Returns:
            {
                "success": bool,
                "action": "added" | "exists" | "rejected" | "error",
                "message": str,
                "commit_url": str  # 仅添加成功时有值
            }
        """
        try:
            # 1. 检查是否已存在于 GitHub 规则中
            github_result = await self.github_service.check_domain_in_rules(domain)
            if github_result.get("exists"):
                matches = github_result.get("matches", [])
                match_info = f"第{matches[0]['line']}行" if matches else ""
                return {
                    "success": True,
                    "action": "exists",
                    "message": f"域名已存在于 GitHub 规则中（{match_info}）"
                }
            
            # 2. 检查是否在 GeoSite 中
            in_geosite = await self.data_manager.is_domain_in_geosite(domain)
            if in_geosite:
                return {
                    "success": True,
                    "action": "exists",
                    "message": "域名已存在于 GEOSITE:CN 中，无需重复添加"
                }
            
            # 3. 进行域名综合检查
            check_result = await self.domain_checker.check_domain_comprehensive(domain)
            
            if "error" in check_result:
                return {
                    "success": False,
                    "action": "error",
                    "message": f"域名检查失败：{check_result['error']}"
                }
            
            # 4. 判断是否符合添加条件
            if self.domain_checker.should_reject(check_result):
                return {
                    "success": True,
                    "action": "rejected",
                    "message": "域名 IP 和 NS 均不在中国大陆，不符合直连规则添加条件"
                }
            
            # 5. 获取目标域名并添加到 GitHub
            target_domain = self.domain_checker.get_target_domain_to_add(check_result)
            if not target_domain:
                target_domain = domain
            
            add_result = await self.github_service.add_domain_to_rules(
                target_domain, username, description
            )
            
            if add_result.get("success"):
                return {
                    "success": True,
                    "action": "added",
                    "message": "域名已成功添加到直连规则",
                    "commit_url": add_result.get("commit_url", ""),
                    "commit_sha": add_result.get("commit_sha", ""),
                    "target_domain": target_domain
                }
            else:
                return {
                    "success": False,
                    "action": "error",
                    "message": add_result.get("error", "添加失败，未知错误")
                }
                
        except Exception as e:
            logger.error(f"自动检查并添加域名失败: {e}")
            return {
                "success": False,
                "action": "error",
                "message": f"处理异常：{str(e)}"
            }

    
    def get_user_state(self, user_id: int) -> Dict[str, Any]:
        """获取用户状态"""
        if user_id not in self.user_states:
            self.user_states[user_id] = {"state": "idle", "data": {}}
        return self.user_states[user_id]
    
    def set_user_state(self, user_id: int, state: str, data: Dict[str, Any] = None):
        """设置用户状态"""
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
        self.user_states[user_id]["state"] = state
        self.user_states[user_id]["data"] = data or {}
    
    def check_user_add_limit(self, user_id: int) -> tuple[bool, int]:
        """检查用户添加频率限制
        
        Returns:
            tuple: (是否可以添加, 剩余次数)
        """
        current_time = time.time()
        one_hour_ago = current_time - 3600  # 1小时前的时间戳
        
        # 清理1小时前的记录
        self.user_add_history[user_id] = [
            timestamp for timestamp in self.user_add_history[user_id]
            if timestamp > one_hour_ago
        ]
        
        # 检查当前小时内的添加次数
        current_count = len(self.user_add_history[user_id])
        remaining = self.MAX_ADDS_PER_HOUR - current_count
        
        return current_count < self.MAX_ADDS_PER_HOUR, remaining
    
    def record_user_add(self, user_id: int):
        """记录用户添加操作"""
        current_time = time.time()
        self.user_add_history[user_id].append(current_time)
    
    def validate_description(self, description: str) -> tuple[bool, str]:
        """验证域名说明
        
        Returns:
            tuple: (是否有效, 处理后的说明)
        """
        if not description:
            return True, ""
        
        # 去除前后空格
        description = description.strip()
        
        # 检查长度
        if len(description) > self.MAX_DESCRIPTION_LENGTH:
            return False, description[:self.MAX_DESCRIPTION_LENGTH]
        
        return True, description
    
    def escape_markdown(self, text: str) -> str:
        """转义Markdown特殊字符"""
        if not text:
            return text
        
        # 转义特殊字符（不包含点号，因为域名和文件路径中需要保留）
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        
        return text

    def _build_main_menu_text(self, username: str) -> str:
        """构建主菜单文案"""
        return f"""
?? 欢迎使用 Rule-Bot，{username}！

?? 我是一个专门管理 Clash 规则的机器人，可以帮助您：

?? *目标仓库：* `{self.config.GITHUB_REPO}`

?? *主要功能：*
? ?? 查询域名规则状态
? ? 添加直连规则
? ? 删除规则（暂不可用）

?? *支持的操作：*
? 检查域名是否已在规则中
? 检查域名是否在 GEOSITE:CN 中
? DNS 解析和 IP 归属地检查
? 自动判断添加建议

请选择您要执行的操作：
"""

    def _build_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """构建主菜单键盘"""
        keyboard = [
            [InlineKeyboardButton("?? 查询域名", callback_data="query_domain")],
            [InlineKeyboardButton("? 添加直连规则", callback_data="add_direct_rule")],
            [InlineKeyboardButton("? 添加代理规则", callback_data="add_proxy_rule")],
            [InlineKeyboardButton("? 删除规则", callback_data="delete_rule")],
            [InlineKeyboardButton("?? 帮助信息", callback_data="help")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def _build_help_text(self) -> str:
        """构建帮助文案"""
        return f"""
?? *Rule-Bot 使用说明*

?? *目标仓库：* `{self.config.GITHUB_REPO}`
?? *直连规则文件：* `{self.config.DIRECT_RULE_FILE}`
?? *代理规则文件：* `{self.config.PROXY_RULE_FILE}`

?? *查询域名功能：*
? 检查域名是否在直连规则中
? 检查域名是否在 GEOSITE:CN 中
? 显示域名的 IP 归属地信息

? *添加直连规则功能：*
? 自动检查域名 IP 归属地
? 检查 NS 服务器归属地
? 根据检查结果自动判断是否适合添加
? 支持添加说明信息

?? *操作流程：*
1. 选择功能按钮
2. 输入域名（支持多种格式）
3. 查看检查结果
4. 根据提示进行操作

?? *注意事项：*
? 代理规则添加功能暂不支持
? 删除规则功能暂不支持
? 域名检查基于 DoH 和 GeoIP 数据

?? *技术特性：*
? 使用中国境内 EDNS 查询
? 支持阿里云和腾讯云 DoH
? 自动更新 GeoIP 和 GeoSite 数据
"""

    def _build_help_keyboard(self) -> InlineKeyboardMarkup:
        """构建帮助键盘"""
        keyboard = [[InlineKeyboardButton("?? 返回主菜单", callback_data="main_menu")]]
        return InlineKeyboardMarkup(keyboard)

    async def _build_stats_text(self, user_id: Optional[int] = None, include_limit: bool = False) -> str:
        """构建统计信息文案"""
        try:
            github_stats = await self.github_service.get_file_stats()
            direct_rule_count = github_stats.get("rule_count", 0) if "error" not in github_stats else 0
            geosite_count = len(self.data_manager.geosite_domains)
            stats_text = f"?? *当前统计：*\n? 直连规则数量：{direct_rule_count}\n? GEOSITE:CN 域名数量：{geosite_count:,}\n\n"

            if include_limit and user_id is not None:
                can_add, remaining = self.check_user_add_limit(user_id)
                if can_add:
                    stats_text += f"?? *添加限制：* 本小时内还可添加 {remaining} 个域名\n\n"
                else:
                    stats_text += f"?? *添加限制：* 本小时内已达到添加上限，请稍后再试\n\n"

            return stats_text
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return "?? *统计信息加载中...*\n\n"

    def _format_detail_lines(self, details: list) -> str:
        """格式化检查详情"""
        if not details:
            return ""

        lines = []
        for detail in details[:self.MAX_DETAIL_LINES]:
            detail = str(detail)
            if len(detail) > self.MAX_DETAIL_LINE_LENGTH:
                detail = detail[:self.MAX_DETAIL_LINE_LENGTH - 3] + "..."
            lines.append(f"   ? {detail}")

        remaining = len(details) - self.MAX_DETAIL_LINES
        if remaining > 0:
            lines.append(f"   ? 还有 {remaining} 条")

        return "\n".join(lines)

    def _build_query_prompt(self, stats_text: str) -> str:
        """构建查询提示文案"""
        return (
            "?? *域名查询*\n\n"
            f"?? *目标仓库：* `{self.config.GITHUB_REPO}`\n"
            f"?? *规则文件：* `{self.config.DIRECT_RULE_FILE}`\n\n"
            f"{stats_text}"
            "请输入要查询的域名：\n\n"
            "?? 支持格式：\n"
            "? example.com\n"
            "? www.example.com\n"
            "? https://example.com\n"
            "? https://www.example.com/path\n"
            "? sub.example.com\n"
            "? ftp://example.com\n"
            "? example.com:8080\n\n"
            "?? *注意：添加规则时统一使用二级域名*"
        )

    def _build_add_prompt(self, stats_text: str) -> str:
        """构建添加提示文案"""
        return (
            "? *添加直连规则*\n\n"
            f"?? *目标仓库：* `{self.config.GITHUB_REPO}`\n"
            f"?? *规则文件：* `{self.config.DIRECT_RULE_FILE}`\n\n"
            f"{stats_text}"
            "请输入要添加的域名：\n\n"
            "?? 支持格式：\n"
            "? example.com\n"
            "? www.example.com\n"
            "? https://example.com\n"
            "? https://www.example.com/path\n"
            "? sub.example.com\n"
            "? ftp://example.com\n"
            "? example.com:8080\n\n"
            "?? *注意：系统将自动提取二级域名进行添加*"
        )
    
    async def check_group_membership(self, update: Update) -> bool:
        """检查用户群组成员身份"""
        if not self.group_service or not self.group_service.is_group_check_enabled():
            return True
        
        user_id = update.effective_user.id
        check_result = await self.group_service.check_user_in_group(user_id)
        
        if check_result is True:
            return True

        if check_result is False:
            join_message = self.group_service.get_join_group_message()
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(join_message, parse_mode='Markdown')
            else:
                await update.message.reply_text(join_message, parse_mode='Markdown')
            return False

        error_message = "?? 群组验证失败，请稍后重试。"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(error_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(error_message, parse_mode='Markdown')
        
        return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令"""
        try:
            # 检查群组成员身份
            if not await self.check_group_membership(update):
                return
            
            user = update.effective_user
            username = user.first_name or user.username or "用户"
            
            welcome_text = f"""
👋 你好，{username}！

我是 **Rule-Bot**，可以帮你管理 Clash 规则。

📂 **当前管理仓库**
`{self.config.GITHUB_REPO}`

✨ **我能做什么**
• 🔍 查询域名是否已在规则中
• 🌍 检查域名 IP 归属地（支持 DNS 解析）
• 🤖 智能判断域名是否适合直连
• 📝 一键添加域名到规则文件
• 🗑️ 删除已添加的域名规则（暂未开放）

💡 **使用提示**
直接在聊天框输入域名即可查询，或点击下方按钮操作。
"""
            
            keyboard = [
                [InlineKeyboardButton("🔍 查询域名", callback_data="query_domain")],
                [InlineKeyboardButton("➕ 添加直连规则", callback_data="add_direct_rule")],
                [InlineKeyboardButton("➕ 添加代理规则", callback_data="add_proxy_rule")],
                [InlineKeyboardButton("➖ 删除规则", callback_data="delete_rule")],
                [InlineKeyboardButton("ℹ️ 帮助信息", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
            
            # 重置用户状态
            self.set_user_state(user.id, "idle")
            
        except Exception as e:
            logger.error(f"处理start命令失败: {e}")
            await update.message.reply_text("服务暂时不可用，请稍后再试。")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help 命令"""
        await update.message.reply_text(
            self._build_help_text(),
            reply_markup=self._build_help_keyboard(),
            parse_mode='Markdown'
        )

    async def query_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /query 命令"""
        user_id = update.effective_user.id
        self.set_user_state(user_id, "waiting_query_domain")

        stats_text = await self._build_stats_text()
        keyboard = [[InlineKeyboardButton("?? 返回主菜单", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            self._build_query_prompt(stats_text),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /add 命令"""
        keyboard = [
            [InlineKeyboardButton("➕ 添加直连规则", callback_data="add_direct_rule")],
            [InlineKeyboardButton("➕ 添加代理规则", callback_data="add_proxy_rule")],
            [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "➕ **添加规则**\n\n请选择要添加的规则类型：",
            reply_markup=reply_markup
        )
    
    async def delete_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /delete 命令"""
        await update.message.reply_text(
            "➖ **删除规则功能暂不可用**\n\n该功能正在开发中，敬请期待。"
        )
    
    async def skip_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /skip 命令"""
        try:
            if not await self.check_group_membership(update):
                return

            user_id = update.effective_user.id
            user_state = self.get_user_state(user_id)
            if user_state.get("state") != "waiting_description":
                await update.message.reply_text("当前没有需要跳过的说明。")
                return

            await self._add_domain_to_github_message(update.message, user_id, "")
        except Exception as e:
            logger.error(f"处理skip命令失败: {e}")
            await update.message.reply_text("处理失败，请重试。")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理回调查询"""
        try:
            # 检查群组成员身份
            if not await self.check_group_membership(update):
                return
            
            query = update.callback_query
            await query.answer()
            
            user_id = update.effective_user.id
            data = query.data
            
            if data == "main_menu":
                await self._show_main_menu(query)
            elif data == "query_domain":
                await self._start_domain_query(query, user_id)
            elif data == "add_direct_rule":
                await self._start_add_direct_rule(query, user_id)
            elif data == "add_proxy_rule":
                await self._show_proxy_rule_not_supported(query)
            elif data == "delete_rule":
                await self._show_delete_not_supported(query)
            elif data == "help":
                await self._show_help(query)
            elif data.startswith("add_domain_"):
                await self._handle_add_domain_callback(query, user_id, data)
            elif data.startswith("confirm_add_"):
                await self._handle_confirm_add_callback(query, user_id, data)
            elif data == "skip_description":
                await self._handle_skip_description(query, user_id)
            else:
                await query.edit_message_text("未知操作")
                
        except Exception as e:
            logger.error(f"处理回调失败: {e}")
            await query.edit_message_text("操作失败，请重试。")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本消息"""
        try:
            # 检查群组成员身份
            if not await self.check_group_membership(update):
                return
            
            user_id = update.effective_user.id
            text = update.message.text.strip()
            user_state = self.get_user_state(user_id)
            
            state = user_state.get("state", "idle")
            
            if state == "waiting_query_domain":
                await self._handle_domain_query(update, text, user_id)
            elif state == "waiting_add_domain":
                await self._handle_add_domain_input(update, text, user_id)
            elif state == "waiting_description":
                await self._handle_description_input(update, text, user_id)
            else:
                # 默认处理：显示主菜单
                await self._show_main_menu_message(update.message)
                
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            await update.message.reply_text("处理失败，请重试。")
    
    async def _show_main_menu(self, query):
        """显示主菜单"""
        username = query.from_user.first_name or query.from_user.username or "用户"
        welcome_text = self._build_main_menu_text(username)
        reply_markup = self._build_main_menu_keyboard()
        await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _show_main_menu_message(self, message):
        """通过消息显示主菜单"""
        username = message.from_user.first_name or message.from_user.username or "用户"
        welcome_text = self._build_main_menu_text(username)
        reply_markup = self._build_main_menu_keyboard()
        await message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _start_domain_query(self, query, user_id: int):
        """开始域名查询"""
        self.set_user_state(user_id, "waiting_query_domain")

        stats_text = await self._build_stats_text()
        keyboard = [[InlineKeyboardButton("?? 返回主菜单", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            self._build_query_prompt(stats_text),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def _start_add_direct_rule(self, query, user_id: int):
        """开始添加直连规则"""
        self.set_user_state(user_id, "waiting_add_domain")

        stats_text = await self._build_stats_text(user_id=user_id, include_limit=True)
        keyboard = [[InlineKeyboardButton("?? 返回主菜单", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            self._build_add_prompt(stats_text),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def _show_proxy_rule_not_supported(self, query):
        """显示代理规则不支持"""
        keyboard = [[InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"➕ *添加代理规则*\n\n📂 *目标仓库：* `{self.config.GITHUB_REPO}`\n📄 *规则文件：* `{self.config.PROXY_RULE_FILE}`\n\n⚠️ *代理规则功能暂不支持*\n\n该功能正在开发中，敬请期待。",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_delete_not_supported(self, query):
        """显示删除功能不支持"""
        keyboard = [[InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"➖ *删除规则*\n\n📂 *目标仓库：* `{self.config.GITHUB_REPO}`\n📄 *直连规则文件：* `{self.config.DIRECT_RULE_FILE}`\n📄 *代理规则文件：* `{self.config.PROXY_RULE_FILE}`\n\n⚠️ *删除规则功能暂不可用*\n\n该功能正在开发中，敬请期待。",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_help(self, query):
        """显示帮助信息"""
        await query.edit_message_text(
            self._build_help_text(),
            reply_markup=self._build_help_keyboard(),
            parse_mode='Markdown'
        )

    async def _handle_domain_query(self, update: Update, domain_input: str, user_id: int):
        """处理域名查询"""
        try:
            # 发送处理中消息
            processing_msg = await update.message.reply_text("🔍 正在查询域名信息，请稍候...")
            
            # 标准化域名（查询时使用用户输入的域名）
            domain = normalize_domain(domain_input)
            if not domain:
                await processing_msg.edit_text("❌ 无效的域名格式，请重新输入。")
                return
            
            # 同时获取二级域名用于规则检查
            second_level_for_check = extract_second_level_domain_for_rules(domain_input)
            
            # 检查是否为.cn域名，如果是则直接返回提示
            is_cn = is_cn_domain(domain)
            if is_cn:
                # .cn域名直接显示提示，不进行任何查询操作
                result_text = f"🔍 *域名查询结果*\n\n📍 *查询域名：* `{domain}`\n\n"
                result_text += "📋 *.cn域名说明：* 所有.cn域名默认直连，无需手动添加到规则中\n\n"
                result_text += "💡 *.cn域名包括：*\n"
                result_text += "   • .cn 顶级域名\n"
                result_text += "   • .com.cn 二级域名\n"
                result_text += "   • .net.cn 二级域名\n"
                result_text += "   • .org.cn 二级域名\n"
                result_text += "   • 其他所有.cn结尾的域名\n\n"
                result_text += "✅ *状态：* 域名已默认直连，无需任何操作"
                
                # 显示操作按钮（不包含添加按钮）
                keyboard = [
                    [InlineKeyboardButton("🔍 重新查询", callback_data="query_domain")],
                    [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
                
                # 重置用户状态
                self.set_user_state(user_id, "idle")
                return
            
            # 非.cn域名继续正常查询流程
            # 查询结果文本
            result_text = f"🔍 *域名查询结果*\n\n📍 *查询域名：* `{domain}`\n\n"
            
            # 1. 检查是否在GitHub规则中
            github_result = await self.github_service.check_domain_in_rules(domain)
            if github_result.get("exists"):
                result_text += "✅ *GitHub 规则状态：* 已存在\n"
                for match in github_result.get("matches", []):
                    result_text += f"   • 第{match['line']}行: {match['rule']}\n"
            else:
                result_text += "❌ *GitHub 规则状态：* 不存在\n"
            
            # 2. 检查是否在GeoSite中
            in_geosite = await self.data_manager.is_domain_in_geosite(domain)
            if in_geosite:
                result_text += "✅ *GEOSITE:CN 状态：* 已存在\n"
            else:
                result_text += "❌ *GEOSITE:CN 状态：* 不存在\n"
            
            # 3. 进行综合域名检查
            await processing_msg.edit_text("🔍 正在检查域名 IP 和 NS 信息...")
            check_result = await self.domain_checker.check_domain_comprehensive(domain)
            
            if "error" in check_result:
                result_text += f"\n❌ *域名检查失败：* {check_result['error']}\n"
            else:
                result_text += "\n📊 *DNS 解析信息：*\n"
                
                # 显示IP信息
                if check_result["domain_ips"]:
                    result_text += f"   • 域名 IP: {', '.join(check_result['domain_ips'])}\n"
                if check_result["second_level_ips"]:
                    result_text += f"   • 二级域名 IP: {', '.join(check_result['second_level_ips'])}\n"
                
                # 显示详细信息
                detail_lines = self._format_detail_lines(check_result.get("details", []))
                if detail_lines:
                    result_text += "\n🌍 *IP 归属地信息：*\n"
                    result_text += f"{detail_lines}\n"
                
                # 根据条件显示建议和状态
                if github_result.get("exists") or in_geosite:
                    result_text += f"\n✅ *状态：* 域名已在规则中，无需添加\n"
                elif (not github_result.get("exists") and not in_geosite and 
                    (check_result.get("domain_china_status") or check_result.get("second_level_china_status") or check_result.get("ns_china_status"))):
                    result_text += f"\n💡 *建议：* {check_result['recommendation']}\n"
                else:
                    result_text += f"\n ℹ️ *说明：* 域名 IP 和 NS 均不在中国大陆，不建议添加\n"
            
            # 显示操作按钮
            keyboard = []
            
            # 只有当域名不在GitHub规则和GeoSite中，且有中国IP或NS时才推荐添加
            # (.cn域名已经在上面提前处理了，这里不会遇到)
            if (not github_result.get("exists") and not in_geosite and 
                "error" not in check_result and 
                (check_result.get("domain_china_status") or check_result.get("second_level_china_status") or check_result.get("ns_china_status"))):
                keyboard.append([InlineKeyboardButton("➕ 添加到直连规则", callback_data=f"add_domain_{domain}")])
            
            keyboard.append([InlineKeyboardButton("🔍 重新查询", callback_data="query_domain")])
            keyboard.append([InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await processing_msg.edit_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
            
            # 重置用户状态
            self.set_user_state(user_id, "idle")
            
        except Exception as e:
            logger.error(f"域名查询失败: {e}")
            await update.message.reply_text("查询失败，请重试。")
    
    async def _handle_add_domain_input(self, update: Update, domain_input: str, user_id: int):
        """处理添加域名输入"""
        try:
            # 发送处理中消息
            processing_msg = await update.message.reply_text("🔍 正在检查域名，请稍候...")
            
            # 检查用户添加频率限制
            can_add, remaining = self.check_user_add_limit(user_id)
            if not can_add:
                keyboard = [
                    [InlineKeyboardButton("🔍 查询域名", callback_data="query_domain")],
                    [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(
                    "⚠️ **添加频率限制**\n\n"
                    f"您在当前小时内已达到添加上限（{self.MAX_ADDS_PER_HOUR}个域名）。\n\n"
                    "🕐 请等待一小时后再尝试添加新域名。\n\n"
                    "💡 此限制是为了防止系统滥用，感谢您的理解。",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                # 重置用户状态
                self.set_user_state(user_id, "idle")
                return
            
            # 检查是否为.cn域名
            normalized_input = normalize_domain(domain_input)
            if normalized_input and is_cn_domain(normalized_input):
                keyboard = [
                    [InlineKeyboardButton("🔍 查询其他域名", callback_data="query_domain")],
                    [InlineKeyboardButton("➕ 添加其他域名", callback_data="add_direct_rule")],
                    [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(
                    "❌ **.cn域名不可添加**\n\n"
                    "📋 **.cn域名默认直连**：所有.cn结尾的域名都已默认走直连路线，无需手动添加到规则中。\n\n"
                    "💡 如需添加其他域名，请选择下方操作：",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                # 重置用户状态
                self.set_user_state(user_id, "idle")
                return
            
            # 提取二级域名用于添加规则
            domain = extract_second_level_domain_for_rules(domain_input)
            if not domain:
                if normalized_input and is_cn_domain(normalized_input):
                    keyboard = [
                        [InlineKeyboardButton("🔍 查询其他域名", callback_data="query_domain")],
                        [InlineKeyboardButton("➕ 添加其他域名", callback_data="add_direct_rule")],
                        [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await processing_msg.edit_text(
                        "❌ **.cn域名不可添加**\n\n"
                        "📋 **.cn域名默认直连**：所有.cn结尾的域名都已默认走直连路线，无需手动添加到规则中。",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    await processing_msg.edit_text("❌ 无效的域名格式，请重新输入。")
                # 重置用户状态
                self.set_user_state(user_id, "idle")
                return
            
            # 显示提取的二级域名信息
            if domain != normalize_domain(domain_input):
                await processing_msg.edit_text(f"🔍 已提取二级域名：`{domain}`\n\n正在检查域名状态...")
                await asyncio.sleep(1)  # 给用户时间看到提取结果
            
            # 1. 防重复检查
            await processing_msg.edit_text("🔍 正在检查域名是否已存在...")
            
            # 检查 GitHub 规则
            github_result = await self.github_service.check_domain_in_rules(domain)
            second_level = extract_second_level_domain(domain)
            
            if github_result.get("exists"):
                result_text = f"❌ **域名已存在于规则中**\n\n"
                result_text += f"📍 **域名：** `{domain}`\n\n"
                result_text += "📋 **找到的规则：**\n"
                for match in github_result.get("matches", []):
                    result_text += f"   • 第{match['line']}行: {match['rule']}\n"
                
                keyboard = [
                    [InlineKeyboardButton("➕ 添加其他域名", callback_data="add_direct_rule")],
                    [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
                self.set_user_state(user_id, "idle")
                return
            
            # 检查二级域名规则
            if second_level and second_level != domain:
                second_level_result = await self.github_service.check_domain_in_rules(second_level)
                if second_level_result.get("exists"):
                    result_text = f"❌ **二级域名已存在于规则中**\n\n"
                    result_text += f"📍 **输入域名：** `{domain}`\n"
                    result_text += f"📍 **二级域名：** `{second_level}`\n\n"
                    result_text += "📋 **找到的规则：**\n"
                    for match in second_level_result.get("matches", []):
                        result_text += f"   • 第{match['line']}行: {match['rule']}\n"
                    
                    keyboard = [
                        [InlineKeyboardButton("➕ 添加其他域名", callback_data="add_direct_rule")],
                        [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await processing_msg.edit_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
                    self.set_user_state(user_id, "idle")
                    return
            
            # 检查GeoSite
            in_geosite = await self.data_manager.is_domain_in_geosite(domain)
            if in_geosite:
                result_text = f"❌ **域名已存在于 GEOSITE:CN 中**\n\n"
                result_text += f"📍 **域名：** `{domain}`\n\n"
                result_text += "该域名已在 GEOSITE:CN 规则中，不需要重复添加。"
                
                keyboard = [
                    [InlineKeyboardButton("➕ 添加其他域名", callback_data="add_direct_rule")],
                    [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
                self.set_user_state(user_id, "idle")
                return
            
            # 2. 进行域名检查
            await processing_msg.edit_text("🔍 正在检查域名 IP 和 NS 信息...")
            check_result = await self.domain_checker.check_domain_comprehensive(domain)
            
            if "error" in check_result:
                await processing_msg.edit_text(f"❌ 域名检查失败：{check_result['error']}")
                return
            
            # 保存检查结果到用户状态
            self.set_user_state(user_id, "domain_checked", {
                "domain": domain,
                "check_result": check_result
            })
            
            # 生成检查结果文本
            result_text = f"📊 **域名检查结果**\n\n"
            result_text += f"📍 **域名：** `{domain}`\n\n"
            
            # 显示详细信息
            detail_lines = self._format_detail_lines(check_result.get("details", []))
            if detail_lines:
                result_text += "?? **检查详情：**\n"
                result_text += f"{detail_lines}\n"

            result_text += f"\n💡 **建议：** {check_result['recommendation']}\n"
            
            # 根据检查结果决定下一步
            keyboard = []
            
            if self.domain_checker.should_add_directly(check_result):
                # 符合条件，提供添加选项
                keyboard.append([InlineKeyboardButton("✅ 确认添加", callback_data="confirm_add_yes")])
                keyboard.append([InlineKeyboardButton("❌ 取消添加", callback_data="confirm_add_no")])
            elif self.domain_checker.should_reject(check_result):
                # 不符合条件，拒绝添加
                result_text += "\n❌ **不符合添加条件，无法添加到直连规则。**"
                keyboard.append([InlineKeyboardButton("➕ 添加其他域名", callback_data="add_direct_rule")])
            else:
                # 默认情况（理论上不会到这里）
                keyboard.append([InlineKeyboardButton("✅ 确认添加", callback_data="confirm_add_yes")])
                keyboard.append([InlineKeyboardButton("❌ 取消添加", callback_data="confirm_add_no")])
            
            keyboard.append([InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await processing_msg.edit_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"添加域名输入处理失败: {e}")
            await update.message.reply_text("处理失败，请重试。")
    
    async def _handle_add_domain_callback(self, query, user_id: int, data: str):
        """处理添加域名回调"""
        try:
            domain = data.replace("add_domain_", "")
            
            # 进行域名检查
            check_result = await self.domain_checker.check_domain_comprehensive(domain)
            
            if "error" in check_result:
                await query.edit_message_text(f"❌ 域名检查失败：{check_result['error']}")
                return
            
            # 保存检查结果
            self.set_user_state(user_id, "domain_checked", {
                "domain": domain,
                "check_result": check_result
            })
            
            # 生成检查结果文本
            result_text = f"📊 **域名检查结果**\n\n"
            result_text += f"📍 **域名：** `{domain}`\n\n"
            
            detail_lines = self._format_detail_lines(check_result.get("details", []))
            if detail_lines:
                result_text += "?? **检查详情：**\n"
                result_text += f"{detail_lines}\n"

            result_text += f"\n💡 **建议：** {check_result['recommendation']}\n"
            
            # 根据检查结果决定下一步
            keyboard = []
            
            if not self.domain_checker.should_reject(check_result):
                keyboard.append([InlineKeyboardButton("✅ 确认添加", callback_data="confirm_add_yes")])
                keyboard.append([InlineKeyboardButton("❌ 取消添加", callback_data="confirm_add_no")])
            else:
                result_text += "\n❌ **不符合添加条件，无法添加到直连规则。**"
            
            keyboard.append([InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"处理添加域名回调失败: {e}")
            await query.edit_message_text("操作失败，请重试。")
    
    async def _handle_confirm_add_callback(self, query, user_id: int, data: str):
        """处理确认添加回调"""
        try:
            if data == "confirm_add_no":
                # 取消添加
                keyboard = [
                    [InlineKeyboardButton("➕ 添加其他域名", callback_data="add_direct_rule")],
                    [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "❌ **已取消添加**\n\n您可以重新选择要添加的域名。",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                self.set_user_state(user_id, "idle")
                return
            
            # 确认添加
            user_state = self.get_user_state(user_id)
            domain_data = user_state.get("data", {})
            
            if not domain_data:
                await query.edit_message_text("❌ 数据丢失，请重新开始。")
                return
            
            domain = domain_data.get("domain")
            if not domain:
                await query.edit_message_text("❌ 域名数据丢失，请重新开始。")
                return
            
            # 询问说明
            self.set_user_state(user_id, "waiting_description", domain_data)
            
            keyboard = [[InlineKeyboardButton("⏭️ 跳过说明", callback_data="skip_description")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📝 **请输入域名说明**\n\n"
                f"📍 **域名：** `{domain}`\n\n"
                f"请输入该域名的用途说明（限制20个汉字以内）：\n\n"
                f"例如：游戏官网、视频网站、新闻门户等",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"处理确认添加回调失败: {e}")
            await query.edit_message_text("操作失败，请重试。")
    
    async def _handle_skip_description(self, query, user_id: int):
        """处理跳过说明"""
        await self._add_domain_to_github(query, user_id, "")
    
    async def _handle_description_input(self, update: Update, description: str, user_id: int):
        """处理说明输入"""
        try:
            # 验证说明内容
            is_valid, processed_description = self.validate_description(description)
            
            if not is_valid:
                keyboard = [
                    [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"❌ **说明内容超出限制**\n\n"
                    f"📏 **限制：** 最多 {self.MAX_DESCRIPTION_LENGTH} 个字符\n"
                    f"📝 **您的输入：** {len(description)} 个字符\n\n"
                    f"✂️ **截取后内容：** `{processed_description}`\n\n"
                    "💡 请重新输入简短的说明，或发送 `/skip` 跳过说明。",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            
            await self._add_domain_to_github_message(update.message, user_id, processed_description)
            
        except Exception as e:
            logger.error(f"处理说明输入失败: {e}")
            await update.message.reply_text("处理失败，请重试。")
    
    async def _add_domain_to_github(self, query, user_id: int, description: str):
        """添加域名到GitHub"""
        try:
            user_state = self.get_user_state(user_id)
            domain_data = user_state.get("data", {})
            
            domain = domain_data.get("domain")
            check_result = domain_data.get("check_result")
            
            if not domain or not check_result:
                await query.edit_message_text("❌ 数据丢失，请重新开始。")
                return
            
            # 获取要添加的目标域名
            logger.debug(f"准备获取目标域名，check_result: {check_result}")
            target_domain = self.domain_checker.get_target_domain_to_add(check_result)
            if not target_domain:
                target_domain = domain
                logger.warning(f"无法获取目标域名，使用原始域名: {domain}")
            
            # 获取用户名
            username = query.from_user.first_name or query.from_user.username or str(query.from_user.id)
            
            logger.debug(f"最终目标域名: {target_domain}, 用户名: {username}, 描述: {description}")
            
            # 显示添加中消息
            await query.edit_message_text("⏳ 正在添加域名到 GitHub 规则...")
            
            # 添加到GitHub
            add_result = await self.github_service.add_domain_to_rules(
                target_domain, username, description
            )
            
            if add_result.get("success"):
                # 记录用户添加历史
                self.record_user_add(user_id)
                
                # 获取剩余添加次数
                _, remaining = self.check_user_add_limit(user_id)
                
                result_text = f"✅ **域名添加成功！**\n\n"
                result_text += f"📍 **域名：** `{self.escape_markdown(target_domain)}`\n"
                result_text += f"👤 **提交者：** @{self.escape_markdown(username)}\n"
                if description:
                    result_text += f"📝 **说明：** {self.escape_markdown(description)}\n"
                result_text += f"📂 **文件路径：** `{self.escape_markdown(add_result['file_path'])}`\n"
                if add_result.get('commit_url'):
                    result_text += f"🔗 **查看提交：** [点击查看]({add_result['commit_url']})\n"
                    result_text += f"📝 **Commit ID：** `{add_result.get('commit_sha', '')[:8]}`\n"
                result_text += f"💬 **提交信息：** `{self.escape_markdown(add_result['commit_message'])}`\n"
                result_text += f"\n💡 本小时内还可添加 {remaining} 个域名"
            else:
                result_text = f"❌ **域名添加失败**\n\n"
                result_text += f"📍 **域名：** `{self.escape_markdown(target_domain)}`\n"
                result_text += f"❌ **错误：** {self.escape_markdown(add_result.get('error', '未知错误'))}"
            
            keyboard = [
                [InlineKeyboardButton("➕ 继续添加", callback_data="add_direct_rule")],
                [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
            
            # 重置用户状态
            self.set_user_state(user_id, "idle")
            
        except Exception as e:
            logger.error(f"添加域名到GitHub失败: {e}")
            await query.edit_message_text("添加失败，请重试。")
    
    async def _add_domain_to_github_message(self, message, user_id: int, description: str):
        """通过消息添加域名到GitHub"""
        try:
            user_state = self.get_user_state(user_id)
            domain_data = user_state.get("data", {})
            
            domain = domain_data.get("domain")
            check_result = domain_data.get("check_result")
            
            if not domain or not check_result:
                await message.reply_text("❌ 数据丢失，请重新开始。")
                return
            
            # 获取要添加的目标域名
            target_domain = self.domain_checker.get_target_domain_to_add(check_result)
            if not target_domain:
                target_domain = domain
            
            # 显示添加中消息
            processing_msg = await message.reply_text("⏳ 正在添加域名到 GitHub 规则...")
            
            # 添加到GitHub
            username = message.from_user.first_name or message.from_user.username or str(message.from_user.id)
            add_result = await self.github_service.add_domain_to_rules(
                target_domain, username, description
            )
            
            if add_result.get("success"):
                # 记录用户添加历史
                self.record_user_add(user_id)
                
                # 获取剩余添加次数
                _, remaining = self.check_user_add_limit(user_id)
                
                result_text = f"✅ **域名添加成功！**\n\n"
                result_text += f"📍 **域名：** `{self.escape_markdown(target_domain)}`\n"
                result_text += f"👤 **提交者：** @{self.escape_markdown(username)}\n"
                if description:
                    result_text += f"📝 **说明：** {self.escape_markdown(description)}\n"
                result_text += f"📂 **文件路径：** `{self.escape_markdown(add_result['file_path'])}`\n"
                if add_result.get('commit_url'):
                    result_text += f"🔗 **查看提交：** [点击查看]({add_result['commit_url']})\n"
                    result_text += f"📝 **Commit ID：** `{add_result.get('commit_sha', '')[:8]}`\n"
                result_text += f"💬 **提交信息：** `{self.escape_markdown(add_result['commit_message'])}`\n"
                result_text += f"\n💡 本小时内还可添加 {remaining} 个域名"
            else:
                result_text = f"❌ **域名添加失败**\n\n"
                result_text += f"📍 **域名：** `{self.escape_markdown(target_domain)}`\n"
                result_text += f"❌ **错误：** {self.escape_markdown(add_result.get('error', '未知错误'))}"
            
            keyboard = [
                [InlineKeyboardButton("➕ 继续添加", callback_data="add_direct_rule")],
                [InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await processing_msg.edit_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
            
            # 重置用户状态
            self.set_user_state(user_id, "idle")
            
        except Exception as e:
            logger.error(f"添加域名到GitHub失败: {e}")
            await message.reply_text("添加失败，请重试。")

 
