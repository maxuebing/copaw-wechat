# -*- coding: utf-8 -*-
# pylint: disable=too-many-statements,too-many-branches,too-many-lines,unused-argument
"""企业微信频道 - WebSocket 长连接模式

实现企业微信智能机器人的消息收发功能，使用 WebSocket 长连接方式。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import threading
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import aiohttp

# 导入 CoPaw 相关模块
try:
    from copaw.app.channels.base import (
        BaseChannel,
        OnReplySent,
        OutgoingContentPart,
        ProcessHandler,
    )
    from agentscope_runtime.engine.schemas.agent_schemas import (
        ContentType,
        ImageContent,
        TextContent,
        FileContent,
    )
    _COPAW_AVAILABLE = True
except ImportError:
    BaseChannel = object  # type: ignore
    OnReplySent = None  # type: ignore
    OutgoingContentPart = None  # type: ignore
    ProcessHandler = None  # type: ignore
    ContentType = None  # type: ignore
    ImageContent = None  # type: ignore
    TextContent = None  # type: ignore
    FileContent = None  # type: ignore
    _COPAW_AVAILABLE = False

from .constants import (
    WECOM_CHATTYPE_GROUP,
    WECOM_CHATTYPE_SINGLE,
    WECOM_MSGTYPE_FILE,
    WECOM_MSGTYPE_IMAGE,
    WECOM_MSGTYPE_MARKDOWN,
    WECOM_MSGTYPE_MIXED,
    WECOM_MSGTYPE_TEXT,
    WECOM_MSGTYPE_VOICE,
)

if TYPE_CHECKING:
    from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest

logger = logging.getLogger(__name__)

# WebSocket 常量
WSS_URL = "wss://openws.work.weixin.qq.com"
HEARTBEAT_INTERVAL = 30  # 心跳间隔（秒）
RECONNECT_DELAY = 5  # 重连延迟（秒）
MAX_RECONNECT_DELAY = 60  # 最大重连延迟（秒）


class WeComChannel(BaseChannel):
    """企业微信频道 - WebSocket 长连接模式

    通过 WebSocket 长连接接收企业微信智能机器人的消息，
    并通过同一连接发送回复。

    配置方式：
    1. 在企业微信管理后台开启「长连接 API 模式」
    2. 获取 BotID 和 Secret（长连接专用）
    3. 无需配置回调 URL 和加解密密钥
    """

    channel = "wecom"

    def __init__(
        self,
        process: ProcessHandler,
        enabled: bool,
        bot_id: str,
        secret: str,
        bot_prefix: str = "[BOT] ",
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
        dm_policy: str = "open",
        group_policy: str = "open",
        allow_from: Optional[List[str]] = None,
        deny_message: str = "",
        http_proxy: str = "",
        http_proxy_auth: str = "",
    ):
        # 检测 BaseChannel 是否支持访问控制参数
        base_sig = inspect.signature(BaseChannel.__init__)
        base_params = set(base_sig.parameters.keys())

        # 构建基础参数（所有版本都支持）
        base_kwargs = {
            "process": process,
            "on_reply_sent": on_reply_sent,
            "show_tool_details": show_tool_details,
            "filter_tool_messages": filter_tool_messages,
            "filter_thinking": filter_thinking,
        }

        # 检查是否支持访问控制参数（新版本 CoPaw）
        self._has_base_access_control = "dm_policy" in base_params

        if self._has_base_access_control:
            # 新版本：传递访问控制参数给 BaseChannel
            base_kwargs.update({
                "dm_policy": dm_policy,
                "group_policy": group_policy,
                "allow_from": allow_from,
                "deny_message": deny_message,
            })
        else:
            # 旧版本：自己存储访问控制配置
            self._dm_policy = dm_policy
            self._group_policy = group_policy
            self._allow_from = set(allow_from or [])
            self._deny_message = deny_message

        super().__init__(**base_kwargs)

        self.enabled = enabled
        self.bot_id = bot_id
        self.secret = secret
        self.bot_prefix = bot_prefix

        # 代理配置
        self._http_proxy = http_proxy
        self._http_proxy_auth = http_proxy_auth

        # WebSocket 连接
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._ws_session: Optional[aiohttp.ClientSession] = None
        self._ws_lock = asyncio.Lock()

        # 事件循环和线程
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 心跳任务
        self._heartbeat_task: Optional[asyncio.Task] = None

        # 消息去重缓存
        self._processed_message_ids: set = set()
        self._processed_lock = threading.Lock()

        # req_id 存储（用于回复消息关联）
        self._req_id_store: Dict[str, Dict] = {}
        self._req_id_lock = asyncio.Lock()

        # 时间去抖动
        self._debounce_seconds = 0.0

        # 连接状态
        self._is_connected = False
        self._is_connecting = False

        # 重连相关
        self._reconnect_delay = RECONNECT_DELAY
        self._should_reconnect = True

    @classmethod
    def from_env(
        cls,
        process: ProcessHandler,
        on_reply_sent: OnReplySent = None,
    ) -> "WeComChannel":
        """从环境变量创建实例

        环境变量：
        - WECOM_CHANNEL_ENABLED: 是否启用
        - WECOM_BOT_ID: 智能机器人 BotID
        - WECOM_SECRET: 长连接专用密钥
        - WECOM_BOT_PREFIX: 机器人前缀
        """
        allow_from_env = os.getenv("WECOM_ALLOW_FROM", "")
        allow_from = (
            [s.strip() for s in allow_from_env.split(",") if s.strip()]
            if allow_from_env
            else []
        )

        return cls(
            process=process,
            enabled=os.getenv("WECOM_CHANNEL_ENABLED", "1") == "1",
            bot_id=os.getenv("WECOM_BOT_ID", ""),
            secret=os.getenv("WECOM_SECRET", ""),
            bot_prefix=os.getenv("WECOM_BOT_PREFIX", "[BOT] "),
            on_reply_sent=on_reply_sent,
            dm_policy=os.getenv("WECOM_DM_POLICY", "open"),
            group_policy=os.getenv("WECOM_GROUP_POLICY", "open"),
            allow_from=allow_from,
            deny_message=os.getenv("WECOM_DENY_MESSAGE", ""),
            http_proxy=os.getenv("WECOM_HTTP_PROXY", ""),
            http_proxy_auth=os.getenv("WECOM_HTTP_PROXY_AUTH", ""),
        )

    @classmethod
    def from_config(
        cls,
        process: ProcessHandler,
        config: Any,
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
    ) -> "WeComChannel":
        """从配置创建实例

        Args:
            process: 处理函数
            config: 配置对象（可能是 Pydantic 模型、SimpleNamespace 或 dict）
            on_reply_sent: 回调函数
            show_tool_details: 是否显示工具详情
            filter_tool_messages: 是否过滤工具消息
            filter_thinking: 是否过滤思考内容

        Returns:
            WeComChannel 实例
        """
        # 处理不同类型的配置对象
        if isinstance(config, dict):
            enabled = config.get("enabled", False)
            bot_id = config.get("bot_id", "")
            secret = config.get("secret", "")
            bot_prefix = config.get("bot_prefix", "[BOT] ")
            dm_policy = config.get("dm_policy", "open")
            group_policy = config.get("group_policy", "open")
            allow_from = config.get("allow_from")
            deny_message = config.get("deny_message", "")
            http_proxy = config.get("http_proxy", "")
            http_proxy_auth = config.get("http_proxy_auth", "")
        else:
            # SimpleNamespace 或 Pydantic 模型
            enabled = getattr(config, "enabled", False)
            bot_id = getattr(config, "bot_id", "")
            secret = getattr(config, "secret", "")
            bot_prefix = getattr(config, "bot_prefix", "[BOT] ")
            dm_policy = getattr(config, "dm_policy", "open")
            group_policy = getattr(config, "group_policy", "open")
            allow_from = getattr(config, "allow_from", None)
            deny_message = getattr(config, "deny_message", "")
            http_proxy = getattr(config, "http_proxy", "")
            http_proxy_auth = getattr(config, "http_proxy_auth", "")

        return cls(
            process=process,
            enabled=enabled,
            bot_id=bot_id,
            secret=secret,
            bot_prefix=bot_prefix,
            on_reply_sent=on_reply_sent,
            show_tool_details=show_tool_details,
            filter_tool_messages=filter_tool_messages,
            filter_thinking=filter_thinking,
            dm_policy=dm_policy,
            group_policy=group_policy,
            allow_from=allow_from,
            deny_message=deny_message,
            http_proxy=http_proxy,
            http_proxy_auth=http_proxy_auth,
        )

    # ---------------------------
    # 生命周期管理
    # ---------------------------

    async def start(self) -> None:
        """启动频道

        1. 创建事件循环
        2. 建立 WebSocket 连接
        3. 发送订阅请求
        4. 启动心跳任务
        5. 启动消息接收循环
        """
        logger.info("启动企业微信频道（长连接模式）...")

        self._stop_event.clear()
        self._should_reconnect = True

        # 创建新的事件循环
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # 在新线程中运行 WebSocket
        self._ws_thread = threading.Thread(
            target=self._run_ws_loop, daemon=True, name="WeComWebSocket"
        )
        self._ws_thread.start()

        logger.info("企业微信频道已启动（长连接模式）")

    async def stop(self) -> None:
        """停止频道

        1. 停止重连
        2. 关闭 WebSocket 连接
        3. 取消心跳任务
        4. 关闭事件循环
        """
        logger.info("停止企业微信频道...")

        self._should_reconnect = False
        self._stop_event.set()

        # 在事件循环中执行关闭
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._close_ws(), self._loop)

        # 等待线程结束
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5)

        logger.info("企业微信频道已停止")

    def _run_ws_loop(self) -> None:
        """在新线程中运行 WebSocket 事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._ws_main())

    async def _ws_main(self) -> None:
        """WebSocket 主循环"""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_subscribe()
                await self._receive_loop()
            except Exception as e:
                logger.error(f"WebSocket 连接异常: {e}")
                if self._stop_event.is_set():
                    break

                # 指数退避重连
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, MAX_RECONNECT_DELAY
                )

    async def _connect_and_subscribe(self) -> None:
        """建立 WebSocket 连接并发送订阅请求"""
        async with self._ws_lock:
            if self._is_connecting:
                return

            self._is_connecting = True
            self._is_connected = False

        try:
            # 配置代理
            connector = aiohttp.TCPConnector(limit=100)
            timeout = aiohttp.ClientTimeout(total=30)

            headers = {}
            proxy = None
            if self._http_proxy:
                proxy = self._http_proxy
                if self._http_proxy_auth:
                    headers["Proxy-Authorization"] = self._http_proxy_auth

            # 创建 HTTP Session
            self._ws_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=headers,
            )

            # 建立 WebSocket 连接
            logger.info(f"正在连接企业微信 WebSocket: {WSS_URL}")
            self._ws = await self._ws_session.ws_connect(
                WSS_URL, proxy=proxy, heartbeat=HEARTBEAT_INTERVAL
            )
            self._is_connected = True
            self._reconnect_delay = RECONNECT_DELAY  # 重置重连延迟

            logger.info("WebSocket 连接成功，正在订阅机器人...")

            # 发送订阅请求
            await self._subscribe()

            # 启动心跳任务
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            logger.info(f"企业微信机器人订阅成功: bot_id={self.bot_id}")

        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            self._is_connected = False
            if self._ws_session:
                await self._ws_session.close()
                self._ws_session = None
            raise
        finally:
            self._is_connecting = False

    async def _subscribe(self) -> None:
        """发送订阅请求"""
        req_id = str(uuid.uuid4())

        subscribe_msg = {
            "cmd": "aibot_subscribe",
            "headers": {"req_id": req_id},
            "body": {"bot_id": self.bot_id, "secret": self.secret},
        }

        await self._send_json(subscribe_msg)

        # 等待订阅响应
        response = await self._ws.receive()
        response_data = response.json()

        if response_data.get("errcode") != 0:
            raise Exception(f"订阅失败: {response_data}")

    async def _receive_loop(self) -> None:
        """消息接收循环"""
        logger.info("开始接收消息...")

        while not self._stop_event.is_set():
            try:
                if self._ws is None or self._ws.closed:
                    logger.warning("WebSocket 连接已关闭")
                    break

                msg = await self._ws.receive()

                # msg.json 是方法，需要调用
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    data = json.loads(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket 错误: {msg}")
                    break
                else:
                    logger.debug(f"收到非消息类型: {msg.type}")
                    continue

                await self._handle_ws_message(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"接收消息异常: {e}")
                if not self._is_connected:
                    break

    async def _handle_ws_message(self, data: dict) -> None:
        """处理 WebSocket 消息

        Args:
            data: 消息数据
        """
        cmd = data.get("cmd", "")
        headers = data.get("headers", {})
        body = data.get("body", {})
        req_id = headers.get("req_id", "")

        # 处理不同类型的消息
        if cmd == "aibot_msg_callback":
            # 消息回调
            await self._process_message_callback(data)

        elif cmd == "aibot_event_callback":
            # 事件回调
            await self._process_event_callback(data)

        elif cmd == "ping":
            # 心跳响应
            logger.debug("收到心跳响应")

        else:
            logger.debug(f"未知命令类型: {cmd}")

    async def _process_message_callback(self, data: dict) -> None:
        """处理消息回调

        Args:
            data: 消息数据
        """
        headers = data.get("headers", {})
        body = data.get("body", {})
        req_id = headers.get("req_id", "")

        # 提取消息字段
        msg_id = body.get("msgid", "")
        aibot_id = body.get("aibotid", "")
        chat_id = body.get("chatid", "")
        chat_type = body.get("chattype", WECOM_CHATTYPE_SINGLE)
        from_user = body.get("from", {})
        sender_id = from_user.get("userid", "")
        msg_type = body.get("msgtype", "")

        # 去重
        with self._processed_lock:
            if msg_id in self._processed_message_ids:
                logger.debug(f"重复消息，跳过: msg_id={msg_id[:24]}...")
                return

            self._processed_message_ids.add(msg_id)

            # 限制缓存大小
            if len(self._processed_message_ids) > 10000:
                old_ids = list(self._processed_message_ids)[:5000]
                self._processed_message_ids.difference_update(old_ids)

        # 验证机器人 ID
        if aibot_id != self.bot_id:
            logger.debug(
                f"机器人 ID 不匹配，跳过: expected={self.bot_id}, got={aibot_id}"
            )
            return

        # 检查访问权限
        is_group = chat_type == WECOM_CHATTYPE_GROUP
        allowed, deny_msg = self._check_allowlist(sender_id, is_group)

        if not allowed and deny_msg:
            # 发送拒绝消息
            await self._send_response(req_id, build_text_message(deny_msg))
            return

        # 保存 req_id 用于后续发送
        await self._save_req_id(req_id, sender_id, chat_type, chat_id)

        # 构建原生 payload
        native_payload = await self._build_native_payload(
            body, sender_id, chat_type, chat_id, req_id
        )

        # 入队处理
        if self._enqueue:
            self._enqueue(native_payload)
        else:
            logger.warning("enqueue callback not set")

    async def _process_event_callback(self, data: dict) -> None:
        """处理事件回调

        Args:
            data: 事件数据
        """
        headers = data.get("headers", {})
        body = data.get("body", {})
        event = body.get("event", {})
        event_type = event.get("eventtype", "")

        if event_type == "enter_chat":
            # 进入会话事件 - 可以发送欢迎语
            logger.info("用户进入会话")
            # TODO: 实现欢迎语

        elif event_type == "disconnected_event":
            # 连接断开事件
            logger.warning("收到连接断开事件，准备重连...")
            self._is_connected = False

        else:
            logger.debug(f"未处理的事件类型: {event_type}")

    async def _build_native_payload(
        self,
        msg_data: dict,
        sender_id: str,
        chat_type: str,
        chat_id: str,
        req_id: str,
    ) -> dict:
        """构建原生 payload

        Args:
            msg_data: 消息数据
            sender_id: 发送者 ID
            chat_type: 会话类型
            chat_id: 会话 ID
            req_id: 请求 ID

        Returns:
            原生 payload
        """
        msg_type = msg_data.get("msgtype", "")
        content_parts = []

        # 解析消息内容
        if msg_type == WECOM_MSGTYPE_TEXT:
            text = msg_data.get("text", {}).get("content", "")
            content_parts.append(TextContent(type=ContentType.TEXT, text=text))

        elif msg_type == WECOM_MSGTYPE_IMAGE:
            image_url = msg_data.get("image", {}).get("url", "")
            if image_url:
                content_parts.append(
                    ImageContent(type=ContentType.IMAGE, image_url=image_url)
                )

        elif msg_type == "mixed":
            mixed = msg_data.get("mixed", {})
            text = extract_text_from_mixed(mixed)

            if text:
                content_parts.append(TextContent(type=ContentType.TEXT, text=text))

            # 提取图片
            for item in mixed.get("msg_item", []):
                if item.get("msgtype") == "image":
                    image_url = item.get("image", {}).get("url", "")
                    if image_url:
                        content_parts.append(
                            ImageContent(type=ContentType.IMAGE, image_url=image_url)
                        )

        elif msg_type == WECOM_MSGTYPE_VOICE:
            voice_content = msg_data.get("voice", {}).get("content", "")
            if voice_content:
                content_parts.append(TextContent(type=ContentType.TEXT, text=voice_content))

        elif msg_type == WECOM_MSGTYPE_FILE:
            file_url = msg_data.get("file", {}).get("url", "")
            if file_url:
                content_parts.append(
                    FileContent(type=ContentType.FILE, file_url=file_url)
                )

        # 如果没有内容，添加空文本
        if not content_parts:
            content_parts.append(TextContent(type=ContentType.TEXT, text=""))

        # 构建元数据
        meta = {
            "chat_type": chat_type,
            "chat_id": chat_id,
            "req_id": req_id,
            "msgid": msg_data.get("msgid", ""),
            "aibot_id": msg_data.get("aibotid", ""),
        }

        return {
            "channel_id": self.channel,
            "sender_id": sender_id,
            "content_parts": content_parts,
            "meta": meta,
        }

    # ---------------------------
    # 访问控制
    # ---------------------------

    def _check_allowlist(self, sender_id: str, is_group: bool) -> tuple[bool, str]:
        """检查发送者是否在白名单中"""
        if self._has_base_access_control:
            # 新版本：使用 BaseChannel 的方法
            if hasattr(super(), "_check_allowlist"):
                return super()._check_allowlist(sender_id, is_group)
            # 如果没有方法，使用属性检查
            policy = self.group_policy if is_group else self.dm_policy
            allow_list = set(self.allow_from or [])
            deny_msg = self.deny_message or ""
        else:
            # 旧版本：使用自己存储的配置
            policy = self._group_policy if is_group else self._dm_policy
            allow_list = self._allow_from
            deny_msg = self._deny_message

        # open 模式：允许所有人
        if policy == "open":
            return True, ""

        # whitelist 模式：检查白名单
        if policy == "whitelist":
            if not allow_list:
                return True, ""
            if sender_id in allow_list:
                return True, ""
            return False, deny_msg

        return True, ""

    # ---------------------------
    # 消息构建（BaseChannel 接口）
    # ---------------------------

    def build_agent_request_from_native(
        self, native_payload: Any
    ) -> "AgentRequest":
        """将渠道原生消息转为 AgentRequest"""
        payload = native_payload if isinstance(native_payload, dict) else {}
        channel_id = payload.get("channel_id") or self.channel
        sender_id = payload.get("sender_id") or ""
        content_parts = payload.get("content_parts") or []
        meta = dict(payload.get("meta") or {})

        session_id = self.resolve_session_id(sender_id, meta)

        request = self.build_agent_request_from_user_content(
            channel_id=channel_id,
            sender_id=sender_id,
            session_id=session_id,
            content_parts=content_parts,
            channel_meta=meta,
        )

        if hasattr(request, "channel_meta"):
            request.channel_meta = meta

        return request

    def resolve_session_id(
        self, sender_id: str, channel_meta: Optional[Dict[str, Any]] = None
    ) -> str:
        """解析会话 ID"""
        meta = channel_meta or {}
        chat_type = meta.get("chat_type", WECOM_CHATTYPE_SINGLE)

        if chat_type == WECOM_CHATTYPE_GROUP:
            chat_id = meta.get("chat_id", "")
            return f"{self.channel}:group:{chat_id}"

        return f"{self.channel}:{sender_id}"

    def get_to_handle_from_request(self, request: "AgentRequest") -> str:
        """从 AgentRequest 解析发送目标"""
        meta = getattr(request, "channel_meta", None) or {}
        chat_type = meta.get("chat_type", WECOM_CHATTYPE_SINGLE)

        user_id = getattr(request, "user_id", "") or ""
        chat_id = meta.get("chat_id", "")

        logger.info(f"[WeCom] get_to_handle_from_request: chat_type={chat_type}, user_id={user_id}, chat_id={chat_id}")

        if chat_type == WECOM_CHATTYPE_GROUP:
            return chat_id

        return user_id

    # ---------------------------
    # 消息发送
    # ---------------------------

    async def send(
        self, to_handle: str, text: str, meta: Optional[Dict[str, Any]] = None
    ) -> None:
        """发送一条文本消息"""
        meta = meta or {}
        req_id = meta.get("req_id")

        logger.info(f"[WeCom] send 被调用: to_handle={to_handle}, meta={meta}, req_id from meta={req_id}")

        if not req_id:
            # 尝试从存储中获取
            req_id = self._get_req_id_sync(to_handle)
            logger.info(f"[WeCom] 从存储获取 req_id: to_handle={to_handle}, req_id={req_id}, stored_keys={list(self._req_id_store.keys())}")

        if not req_id:
            logger.warning(f"[WeCom] 没有找到 req_id，无法发送: to_handle={to_handle}")
            return

        # 添加机器人前缀
        if self.bot_prefix:
            text = self.bot_prefix + text

        # 发送文本消息
        msg = build_text_message(text)
        await self._send_response(req_id, msg)

    async def send_content_parts(
        self,
        to_handle: str,
        parts: List[OutgoingContentPart],
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """发送多部分内容"""
        meta = meta or {}
        req_id = meta.get("req_id")

        if not req_id:
            req_id = await self._get_req_id(to_handle)

        if not req_id:
            logger.warning(f"没有找到 req_id，无法发送: to_handle={to_handle}")
            return

        # 解析内容部分
        text_parts = []
        image_parts = []

        for part in parts:
            p_type = getattr(part, "type", None)

            if p_type == ContentType.TEXT:
                text_content = getattr(part, "text", "")
                if text_content:
                    text_parts.append(text_content)

            elif p_type == ContentType.IMAGE:
                image_url = getattr(part, "image_url", "")
                if image_url:
                    image_parts.append(image_url)

        # 如果只有文本
        if text_parts and not image_parts:
            text = "".join(text_parts)
            if self.bot_prefix:
                text = self.bot_prefix + text
            msg = build_text_message(text)
            await self._send_response(req_id, msg)
            return

        # 如果有图片，发送图文混排
        items = []

        if text_parts:
            text = "".join(text_parts)
            if self.bot_prefix:
                text = self.bot_prefix + text
            items.append({"msgtype": "text", "text": {"content": text}})

        for image_url in image_parts:
            items.append({"msgtype": "image", "image": {"url": image_url}})

        if items:
            msg = build_mixed_message(items)
            await self._send_response(req_id, msg)

    async def _send_response(self, req_id: str, msg: dict) -> None:
        """发送响应消息

        Args:
            req_id: 关联的请求 ID
            msg: 消息体
        """
        try:
            response_msg = {
                "cmd": "aibot_respond_msg",
                "headers": {"req_id": req_id},
                "body": msg,
            }

            # 检查是否在正确的事件循环中
            current_loop = asyncio.get_event_loop()
            if current_loop != self._loop:
                # 跨线程调用，使用 run_coroutine_threadsafe
                future = asyncio.run_coroutine_threadsafe(
                    self._send_json(response_msg), self._loop
                )
                future.result(timeout=5)  # 等待完成
            else:
                await self._send_json(response_msg)

            logger.info(f"[WeCom] 发送消息成功: msgtype={msg.get('msgtype')}")

        except Exception as e:
            logger.error(f"[WeCom] 发送消息异常: {e}")

    async def _send_json(self, data: dict) -> None:
        """发送 JSON 数据

        Args:
            data: 要发送的数据
        """
        async with self._ws_lock:
            if self._ws is None or self._ws.closed:
                raise ConnectionError("WebSocket 连接已关闭")

            await self._ws.send_json(data)

    async def _close_ws(self) -> None:
        """关闭 WebSocket 连接"""
        async with self._ws_lock:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                self._heartbeat_task = None

            if self._ws:
                await self._ws.close()
                self._ws = None

            if self._ws_session:
                await self._ws_session.close()
                self._ws_session = None

            self._is_connected = False

    # ---------------------------
    # req_id 存储
    # ---------------------------

    def _get_req_id_sync(self, to_handle: str) -> Optional[str]:
        """同步获取 req_id（用于跨线程调用）

        Args:
            to_handle: 发送目标

        Returns:
            req_id 或 None
        """
        # 使用普通锁
        with self._processed_lock:
            # 尝试直接匹配
            if to_handle in self._req_id_store:
                return self._req_id_store[to_handle]["req_id"]

            # 尝试群聊匹配
            group_key = f"group:{to_handle}"
            if group_key in self._req_id_store:
                return self._req_id_store[group_key]["req_id"]

            return None

    async def _save_req_id(
        self, req_id: str, sender_id: str, chat_type: str, chat_id: str
    ) -> None:
        """保存 req_id

        Args:
            req_id: 请求 ID
            sender_id: 发送者 ID
            chat_type: 会话类型
            chat_id: 会话 ID
        """
        # 使用普通锁，不是 asyncio.Lock
        with self._processed_lock:
            # 单聊使用 sender_id，群聊使用 chat_id
            key = f"group:{chat_id}" if chat_type == WECOM_CHATTYPE_GROUP else sender_id
            self._req_id_store[key] = {
                "req_id": req_id,
                "chat_type": chat_type,
                "chat_id": chat_id,
            }
            logger.info(f"[WeCom] 保存 req_id: key={key}, req_id={req_id}, sender_id={sender_id}, chat_type={chat_type}")

    async def _get_req_id(self, to_handle: str) -> Optional[str]:
        """获取 req_id

        Args:
            to_handle: 发送目标

        Returns:
            req_id 或 None
        """
        async with self._req_id_lock:
            # 尝试直接匹配
            if to_handle in self._req_id_store:
                return self._req_id_store[to_handle]["req_id"]

            # 尝试群聊匹配
            group_key = f"group:{to_handle}"
            if group_key in self._req_id_store:
                return self._req_id_store[group_key]["req_id"]

            return None

    # ---------------------------
    # 心跳
    # ---------------------------

    async def _heartbeat_loop(self) -> None:
        """心跳循环"""
        while not self._stop_event.is_set() and self._is_connected:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await self._send_ping()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                break

    async def _send_ping(self) -> None:
        """发送心跳"""
        ping_msg = {
            "cmd": "ping",
            "headers": {"req_id": str(uuid.uuid4())},
        }

        try:
            await self._send_json(ping_msg)
            logger.debug("发送心跳成功")
        except Exception as e:
            logger.error(f"发送心跳失败: {e}")
            raise


# ---------------------------
# 工具函数
# ---------------------------


def extract_text_from_mixed(mixed: dict) -> str:
    """从图文混排消息中提取文本"""
    items = mixed.get("msg_item", [])
    texts = []

    for item in items:
        if item.get("msgtype") == "text":
            content = item.get("text", {}).get("content", "")
            if content:
                texts.append(content)

    return "".join(texts)


def build_text_message(text: str) -> dict:
    """构建文本消息"""
    return {"msgtype": "text", "text": {"content": text}}


def build_mixed_message(items: list) -> dict:
    """构建图文混排消息"""
    return {"msgtype": "mixed", "mixed": {"msg_item": items}}


def build_markdown_message(content: str) -> dict:
    """构建 Markdown 消息"""
    return {"msgtype": "markdown", "markdown": {"content": content}}
