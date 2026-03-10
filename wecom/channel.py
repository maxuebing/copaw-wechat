# -*- coding: utf-8 -*-
# pylint: disable=too-many-statements,too-many-branches,too-many-lines,unused-argument
"""企业微信频道 - WebSocket 长连接模式

实现企业微信智能机器人的消息收发功能，使用 WebSocket 长连接方式。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import logging
import os
import threading
import uuid
from pathlib import Path
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

        # 媒体目录
        self._media_dir = Path(os.path.expanduser("~/.copaw/media/wecom"))
        self._media_dir.mkdir(parents=True, exist_ok=True)

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
        # 显示版本号
        try:
            from . import __version__
            print(f"[WeCom Channel] v{__version__} 启动中...")
            logger.info(f"企业微信频道 v{__version__} 启动中（长连接模式）...")
        except ImportError:
            print("[WeCom Channel] 启动中...")
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

        # 直接发送订阅请求，不通过 _send_json（因为我们需要等待特定的订阅响应）
        async with self._ws_lock:
            await self._ws.send_json(subscribe_msg)
            logger.info(f"发送订阅请求: bot_id={self.bot_id}")

            # 等待订阅响应
            response = await self._ws.receive()

            # 解析响应
            if response.type == aiohttp.WSMsgType.TEXT:
                response_data = json.loads(response.data)
            elif response.type == aiohttp.WSMsgType.BINARY:
                if isinstance(response.data, (str, bytes, bytearray)):
                    response_data = json.loads(response.data)
                else:
                    raise ConnectionError(f"收到非法的二进制数据: {type(response.data)}")
            elif response.type == aiohttp.WSMsgType.CLOSED:
                raise ConnectionError("WebSocket 连接已关闭")
            elif response.type == aiohttp.WSMsgType.ERROR:
                raise ConnectionError(f"WebSocket 错误: {response.data}")
            else:
                raise ValueError(f"未知的消息类型: {response.type}")

            errcode = response_data.get("errcode", -1)
            errmsg = response_data.get("errmsg", "")

            if errcode != 0:
                raise Exception(f"订阅失败: errcode={errcode}, errmsg={errmsg}")

            logger.info(f"订阅成功: bot_id={self.bot_id}")

    async def _receive_loop(self) -> None:
        """消息接收循环

        接收并分发所有消息：
        - aibot_msg_callback: 消息回调
        - aibot_event_callback: 事件回调
        - errcode/errmsg 响应: 命令执行结果
        - ping: 心跳响应
        """
        logger.info("开始接收消息...")

        while not self._stop_event.is_set():
            try:
                if self._ws is None or self._ws.closed:
                    logger.warning("WebSocket 连接已关闭")
                    break

                msg = await self._ws.receive()

                # 解析消息
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    if isinstance(msg.data, (str, bytes, bytearray)):
                        data = json.loads(msg.data)
                    else:
                        logger.error(f"收到非法的二进制数据: {type(msg.data)}")
                        continue
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket 错误: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning("WebSocket 连接已关闭")
                    break
                else:
                    logger.debug(f"收到非消息类型: {msg.type}")
                    continue

                # 分发消息
                await self._dispatch_message(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"接收消息异常: {e}")
                import traceback
                traceback.print_exc()
                if not self._is_connected:
                    break

    async def _dispatch_message(self, data: dict) -> None:
        """分发收到的消息

        Args:
            data: 消息数据
        """
        cmd = data.get("cmd", "")

        # 检查是否是响应（有 errcode 字段表示是命令执行结果）
        if "errcode" in data:
            errcode = data.get("errcode", -1)
            errmsg = data.get("errmsg", "")
            if errcode == 0:
                logger.debug(f"命令执行成功")
            else:
                logger.warning(f"命令执行失败: errcode={errcode}, errmsg={errmsg}")
            return

        # 处理推送类型的消息
        if cmd == "aibot_msg_callback":
            await self._process_message_callback(data)
        elif cmd == "aibot_event_callback":
            await self._process_event_callback(data)
        elif cmd == "ping":
            logger.debug("收到心跳响应")
        else:
            logger.debug(f"未知命令类型: {cmd}, data={data}")


    async def _process_message_callback(self, msg_data: dict) -> None:
        """处理接收到的消息"""
        print(f"[DEBUG WeCom] _process_message_callback START: {msg_data.get('msgid')}", flush=True)

        try:
            # 兼容两层结构或扁平结构
            # 真实数据通常在 body 字段中，但也可能直接是扁平的
            headers = msg_data.get("headers", {})
            body = msg_data.get("body", {})
            req_id = headers.get("req_id", "")
            
            if not body:
                 # 尝试直接解析 msg_data
                 body = msg_data
                 req_id = body.get("headers", {}).get("req_id", "")

            if body:
                msg_id = body.get("msgid")
                from_user = body.get("from", {})
                sender_id = from_user.get("userid", "")

                # 优先使用 alias
                alias = from_user.get("alias")
                if alias:
                    sender_id = alias

                # 临时修复：为了避开历史记录中的坏数据，我们在 user_id 后添加后缀
                # 这样系统会认为这是一个新用户，从而创建一个干净的会话
                sender_id = f"{sender_id}_v2"

                msg_type = body.get("msgtype", "")
                print(f"[DEBUG WeCom] _process_message_callback: msg_type={msg_type}, body={json.dumps(body, ensure_ascii=False)[:200]}...", flush=True)
                
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

                # 验证机器人 ID (略，假设已校验或非必须)
                # aibot_id = body.get("aibotid", "")
                # if aibot_id != self.bot_id: ...

                # 检查访问权限
                chat_type = body.get("chattype", WECOM_CHATTYPE_SINGLE)
                chat_id = body.get("chatid", "")
                
                # 修正 chat_id 为 sender_id (单聊场景)
                if chat_type == WECOM_CHATTYPE_SINGLE:
                     chat_id = sender_id
                
                is_group = chat_type == WECOM_CHATTYPE_GROUP
                allowed, deny_msg = self._check_allowlist(sender_id, is_group)

                if not allowed and deny_msg:
                    # 发送拒绝消息
                    if req_id:
                        await self._send_response(req_id, build_markdown_message(deny_msg))
                    return

                # 保存 req_id 用于后续发送
                # 注意：保存时要用加了后缀的 sender_id (作为 to_handle)
                print(f"[DEBUG WeCom] 即将保存 req_id: req_id={req_id}, sender_id={sender_id}, chat_type={chat_type}", flush=True)
                await self._save_req_id(req_id, sender_id, chat_type, chat_id)

                native_payload = await self._build_native_payload(
                    body, sender_id, chat_type, chat_id, req_id
                )
                
                if not native_payload:
                    print("[DEBUG WeCom] _build_native_payload returns empty", flush=True)
                    return

                # 获取最终的 sender_id (可能包含后缀)
                final_sender_id = native_payload.get("sender_id", sender_id)
                
                # 显式构造 session_id，确保使用修改后的 sender_id
                if chat_type == WECOM_CHATTYPE_GROUP:
                    session_id = f"{self.channel}:group:{chat_id}"
                else:
                    session_id = f"{self.channel}:{final_sender_id}"
                native_payload["session_id"] = session_id
                
                # 覆盖 native_payload 里的 user_id，确保它也是带后缀的
                native_payload["user_id"] = final_sender_id

                print(f"[DEBUG WeCom] _build_native_payload 成功: content_parts_count={len(native_payload.get('content_parts', []))}, session_id={session_id}", flush=True)

                # 入队处理
                if self._enqueue:
                    print(f"[DEBUG WeCom] 即将入队: {final_sender_id}", flush=True)
                    self._enqueue(native_payload)
                else:
                    print("[DEBUG WeCom] _enqueue callback is None", flush=True)

        except Exception as e:
            print(f"[DEBUG WeCom] _process_message_callback error: {e}", flush=True)
            import traceback
            traceback.print_exc()

    async def _process_event_callback(self, data: dict) -> None:
        """处理事件回调

        Args:
            data: 事件数据
        """
        try:
            headers = data.get("headers", {})
            body = data.get("body", {})
            event = body.get("event", {})
            event_type = event.get("eventtype", "")

            if event_type == "enter_chat":
                # 进入会话事件 - 可以发送欢迎语
                logger.info(f"用户进入会话: {data.get('body', {}).get('from', {})}")
                # TODO: 实现欢迎语

            elif event_type == "disconnected_event":
                # 连接断开事件
                logger.warning("收到连接断开事件，准备重连...")
                self._is_connected = False

            else:
                logger.debug(f"未处理的事件类型: {event_type}")

            # 发送空响应确认事件已处理（企业微信要求所有回调都需要确认）
            # 事件回调通常不需要响应，但为了协议完整性，我们记录一下
            logger.debug(f"事件回调已处理: event_type={event_type}")

        except Exception as e:
            logger.error(f"处理事件回调异常: {e}")
            import traceback
            traceback.print_exc()

    async def _download_and_cache_media(self, url: str, ext: str = ".jpg") -> str:
        """下载媒体文件并缓存到本地，确保有扩展名

        Args:
            url: 媒体 URL
            ext: 期望的扩展名

        Returns:
            本地文件路径
        """
        if not url:
            return ""

        # 生成缓存文件名 (使用 URL 的 MD5)
        url_hash = hashlib.md5(url.encode()).hexdigest()
        local_path = self._media_dir / f"{url_hash}{ext}"

        if local_path.exists():
            return str(local_path)

        try:
            print(f"[DEBUG WeCom] 开始下载媒体: {url[:100]}...", flush=True)
            # 使用 self._ws_session 或新建 session
            # 注意：此处可能在非 WS 线程运行，如果 _ws_session 为空则新建
            async with aiohttp.ClientSession() as session:
                async with session.get(url, proxy=self._http_proxy) as resp:
                    print(f"[DEBUG WeCom] HTTP 响应状态: {resp.status}", flush=True)
                    print(f"[DEBUG WeCom] HTTP 响应头: {dict(resp.headers)}", flush=True)

                    if resp.status == 200:
                        content_type = resp.headers.get('Content-Type', '')
                        content_length = resp.headers.get('Content-Length', 'unknown')
                        print(f"[DEBUG WeCom] Content-Type: {content_type}, Content-Length: {content_length}", flush=True)

                        content = await resp.read()

                        # 打印前 16 字节用于调试
                        print(f"[DEBUG WeCom] 文件头 (hex): {content[:16].hex()}", flush=True)

                        # 如果文件太小，可能不是有效图片
                        if len(content) < 100:
                            print(f"[DEBUG WeCom] 警告: 文件过小 ({len(content)} 字节)，可能不是有效图片", flush=True)

                        local_path.write_bytes(content)
                        print(f"[DEBUG WeCom] 媒体下载成功: {local_path}, 大小: {len(content)} 字节", flush=True)
                        return str(local_path)
                    else:
                        print(f"[DEBUG WeCom] 媒体下载失败: HTTP {resp.status}", flush=True)
                        # 打印响应体用于调试
                        error_body = await resp.text()
                        print(f"[DEBUG WeCom] 错误响应体: {error_body[:500]}", flush=True)
        except Exception as e:
            print(f"[DEBUG WeCom] 媒体下载异常: {e}", flush=True)
            import traceback
            traceback.print_exc()

        return url

    def _detect_image_mime_type(self, file_path: str) -> str:
        """基于文件头检测图片的实际 MIME 类型

        Args:
            file_path: 图片文件路径

        Returns:
            MIME 类型字符串
        """
        try:
            p = Path(file_path)
            if not p.exists():
                return "image/jpeg"

            # 读取文件头（前 12 字节）
            with open(p, "rb") as f:
                header = f.read(12)

            if not header:
                return "image/jpeg"

            # 检测各种图片格式的文件头
            # JPEG: FF D8 FF
            if header[:3] == b'\xFF\xD8\xFF':
                return "image/jpeg"
            # PNG: 89 50 4E 47 0D 0A 1A 0A
            if header[:8] == b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A':
                return "image/png"
            # GIF: 47 49 46 38 (GIF8)
            if header[:4] == b'\x47\x49\x46\x38':
                # GIF87a 或 GIF89a
                return "image/gif"
            # WebP: 52 49 46 46 ... 57 45 42 50 (RIFF...WEBP)
            if header[:4] == b'\x52\x49\x46\x46' and header[8:12] == b'\x57\x45\x42\x50':
                return "image/webp"
            # BMP: 42 4D (BM)
            if header[:2] == b'\x42\x4D':
                return "image/bmp"

            # 无法识别，默认返回 JPEG
            print(f"[DEBUG WeCom] 无法识别图片格式，使用默认 image/jpeg. 文件头: {header[:8].hex()}", flush=True)
            return "image/jpeg"
        except Exception as e:
            print(f"[DEBUG WeCom] 检测图片格式失败: {e}", flush=True)
            return "image/jpeg"

    def _file_to_base64_data_url(self, file_path: str, mime_type: str = None) -> str:
        """将本地文件转换为 Base64 Data URL

        Args:
            file_path: 图片文件路径
            mime_type: MIME 类型，如果为 None 则自动检测
        """
        try:
            p = Path(file_path)
            if not p.exists():
                return file_path

            # 自动检测 MIME 类型
            if mime_type is None:
                mime_type = self._detect_image_mime_type(file_path)

            data = p.read_bytes()
            encoded = base64.b64encode(data).decode("utf-8")
            return f"data:{mime_type};base64,{encoded}"
        except Exception as e:
            print(f"[DEBUG WeCom] Base64 转换失败: {e}", flush=True)
            return file_path

    async def _process_image_url(self, image_url: str) -> str:
        """处理图片 URL：下载、缓存、转 Base64，并确保格式符合要求"""
        if not image_url:
            return ""

        # 下载并本地缓存（不强制使用 .jpg 后缀）
        local_image_path = await self._download_and_cache_media(image_url, ".jpg")

        # 自动检测 MIME 类型并转换为 Base64
        detected_mime = self._detect_image_mime_type(local_image_path)
        print(f"[DEBUG WeCom] 检测到图片格式: {detected_mime}", flush=True)
        data_url = self._file_to_base64_data_url(local_image_path, detected_mime)

        # 检查 data_url 是否有效 (agentscope 要求必须有后缀或为 data: 开头)
        if not data_url.startswith("data:") and not any(data_url.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            print(f"[DEBUG WeCom] data_url 缺少后缀，尝试修复: {data_url}", flush=True)
            # 如果转换 Base64 失败导致返回了本地路径，再次尝试强制转换
            # 如果再次失败，则返回占位符，绝对不要返回本地路径
            try:
                import mimetypes
                import base64

                p_old = Path(data_url)
                if p_old.exists():
                    mime_type, _ = mimetypes.guess_type(str(p_old))
                    if not mime_type:
                        mime_type = "image/jpeg"

                    with open(p_old, "rb") as f:
                        encoded = base64.b64encode(f.read()).decode("utf-8")
                        data_url = f"data:{mime_type};base64,{encoded}"
                        print(f"[DEBUG WeCom] 强制修复: 已转换为 Base64", flush=True)
                else:
                    raise FileNotFoundError(f"File not found: {data_url}")
            except Exception as e:
                print(f"[DEBUG WeCom] 强制修复失败: {e}，使用占位符", flush=True)
                # 降级处理：使用 1x1 透明 GIF，防止 API 报错
                data_url = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"

        return data_url

    async def _build_native_payload(
        self,
        msg_data: dict,
        sender_id: str,
        chat_type: str,
        chat_id: str,
        req_id: str = None
    ) -> dict:
        """构建内部使用的 payload 格式

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

        # 临时修复：为了避开历史记录中的坏数据，我们在 user_id 后添加后缀
        # 这样系统会认为这是一个新用户，从而创建一个干净的会话
        # sender_id = f"{sender_id}_v2"
        # 已经在 _process_message_callback 中处理
        print(f"[DEBUG WeCom] _build_native_payload: type={msg_type}, sender={sender_id}", flush=True)

        content_parts = []
        if msg_type == WECOM_MSGTYPE_TEXT:
            text = msg_data.get("text", {}).get("content", "")
            if text:
                content_parts.append(TextContent(type=ContentType.TEXT, text=text))
        elif msg_type == WECOM_MSGTYPE_IMAGE:
            image_url = msg_data.get("image", {}).get("url", "")
            if image_url:
                # 使用 _process_image_url 处理图片，确保格式正确
                data_url = await self._process_image_url(image_url)
                print(f"[DEBUG WeCom] _build_native_payload: 图片转换为 Base64 完成 (长度={len(data_url)})", flush=True)
                try:
                    # 尝试兼容不同的 ImageContent 参数
                    content_parts.append(
                        ImageContent(type=ContentType.IMAGE, image_url=data_url)
                    )
                except TypeError:
                    content_parts.append(
                        ImageContent(type=ContentType.IMAGE, url=data_url)
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
                        data_url = await self._process_image_url(image_url)
                        print(f"[DEBUG WeCom] _build_native_payload (mixed): 图片转换为 Base64 完成", flush=True)
                        try:
                            content_parts.append(
                                ImageContent(type=ContentType.IMAGE, image_url=data_url)
                            )
                        except TypeError:
                            content_parts.append(
                                ImageContent(type=ContentType.IMAGE, url=data_url)
                            )
        elif msg_type == WECOM_MSGTYPE_FILE:
            file_url = msg_data.get("file", {}).get("url", "")
            if file_url:
                # 获取原始文件名后缀
                filename = msg_data.get("file", {}).get("name", "file")
                ext = Path(filename).suffix or ".bin"
                local_file_path = await self._download_and_cache_media(file_url, ext)
                print(f"[DEBUG WeCom] _build_native_payload: 文件路径={local_file_path}", flush=True)
                try:
                    content_parts.append(
                        FileContent(type=ContentType.FILE, file_url=local_file_path)
                    )
                except TypeError:
                    content_parts.append(
                        FileContent(type=ContentType.FILE, url=local_file_path)
                    )
        elif msg_type == WECOM_MSGTYPE_VOICE:
            # 语音消息
            content = msg_data.get("voice", {}).get("content", "")
            if content:
                content_parts.append(TextContent(type=ContentType.TEXT, text=content))

        # 如果没有内容，添加空文本
        if not content_parts:
            print(f"[DEBUG WeCom] _build_native_payload: 无内容, 添加空文本", flush=True)
            content_parts.append(TextContent(type=ContentType.TEXT, text=""))

        # 如果只有图片，补充一段说明文字（防止某些模型忽略无文字的请求）
        if msg_type == WECOM_MSGTYPE_IMAGE and len(content_parts) == 1:
            content_parts.insert(0, TextContent(type=ContentType.TEXT, text="[图片]"))

        # 构建 native payload
        native_payload = {
            "channel_id": self.channel,  # 使用 channel_id 保持一致
            "sender_id": sender_id,
            "chat_type": chat_type,
            "chat_id": chat_id,
            "req_id": req_id,
            "content_parts": content_parts,
            "meta": {
                "msg_id": msg_data.get("msgid"),
                "aibot_id": msg_data.get("aibotid"),
                "response_url": msg_data.get("response_url"),
            },
        }
        
        # 打印调试信息，显示 content_parts 的具体内容
        parts_info = []
        for p in content_parts:
            p_type = getattr(p, "type", "unknown")
            if p_type == ContentType.TEXT:
                parts_info.append(f"Text(text='{getattr(p, 'text', '')[:20]}')")
            elif p_type == ContentType.IMAGE:
                url = getattr(p, "image_url", None) or getattr(p, "url", None)
                parts_info.append(f"Image(url='{url[:50] if url else 'None'}')")
            else:
                parts_info.append(f"Part(type={p_type})")
        
        print(f"[DEBUG WeCom] _build_native_payload 完成: channel_id={self.channel}, sender_id={sender_id}, parts=[{', '.join(parts_info)}]", flush=True)
        return native_payload

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

        print(f"[DEBUG WeCom] get_to_handle_from_request: chat_type={chat_type}, user_id={user_id}, chat_id={chat_id}")

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
        # 临时处理：如果 to_handle 带 _v2 后缀，查找时要尝试去掉它
        # 或者存储时已经存了带 _v2 的 key
        
        # 总是从存储中获取最新的 req_id
        req_id = self._get_req_id_sync(to_handle)
        
        # 如果找不到，尝试查找原始 ID (去掉 _v2)
        if not req_id and to_handle.endswith("_v2"):
             original_handle = to_handle[:-3]
             print(f"[DEBUG WeCom] 尝试查找原始 ID: {original_handle}", flush=True)
             req_id = self._get_req_id_sync(original_handle)

        print(f"[DEBUG WeCom] send 被调用: to_handle={to_handle}, text={text[:50] if text else ''}, req_id from storage={req_id}")

        if not req_id:
            print(f"[DEBUG WeCom] 没有找到 req_id，无法发送: to_handle={to_handle}")
            logger.warning(f"[WeCom] 没有找到 req_id，无法发送: to_handle={to_handle}")
            return

        # 添加机器人前缀
        if self.bot_prefix:
            text = self.bot_prefix + text

        # 发送文本消息 (注意：aibot_respond_msg 优先支持 markdown 类型)
        msg = build_markdown_message(text)
        await self._send_response(req_id, msg)

    async def send_content_parts(
        self,
        to_handle: str,
        parts: List[OutgoingContentPart],
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """发送多部分内容"""
        import sys

        try:
            msg = f"[DEBUG WeCom] send_content_parts START: to_handle={to_handle}, parts_count={len(parts)}"
            print(msg, flush=True)

            # 总是从存储中获取最新的 req_id，不使用 meta 中的
            # 因为 meta 中的 req_id 可能是旧消息的
            req_id = self._get_req_id_sync(to_handle)
            
            # 如果找不到，尝试查找原始 ID (去掉 _v2)
            if not req_id and to_handle.endswith("_v2"):
                 original_handle = to_handle[:-3]
                 print(f"[DEBUG WeCom] send_content_parts 尝试查找原始 ID: {original_handle}", flush=True)
                 req_id = self._get_req_id_sync(original_handle)

            msg = f"[DEBUG WeCom] send_content_parts: req_id from storage={req_id}"
            print(msg, flush=True)

            if not req_id:
                msg = f"[DEBUG WeCom] send_content_parts 没有找到 req_id: to_handle={to_handle}"
                print(msg, flush=True)
                logger.warning(f"没有找到 req_id，无法发送: to_handle={to_handle}")
                return

            # 提取文本和图片
            text_parts = []
            image_parts = []
            for part in parts:
                if part.type == ContentType.TEXT:
                    text_parts.append(part.text)
                elif part.type == ContentType.IMAGE:
                    # 尝试兼容不同的 ImageContent 参数
                    url = getattr(part, "image_url", None) or getattr(part, "url", None)
                    if url:
                        image_parts.append(url)
                elif part.type == ContentType.FILE:
                    # 文件暂时转为文本链接
                    url = getattr(part, "file_url", None) or getattr(part, "url", None)
                    if url:
                        text_parts.append(f"\n[文件]({url})")

            print(f"[DEBUG WeCom] send_content_parts: text_parts={len(text_parts)}, image_parts={len(image_parts)}", flush=True)

            # 如果只有文本
            if text_parts and not image_parts:
                text = "".join(text_parts)
                if self.bot_prefix:
                    text = self.bot_prefix + text
                # aibot_respond_msg 优先支持 markdown 类型
                msg_dict = build_markdown_message(text)
                msg = f"[DEBUG WeCom] send_content_parts: 即将发送 Markdown 消息, text={text[:50]}"
                print(msg, flush=True)
                await self._send_response(req_id, msg_dict)
                return

            # 如果有图片，使用 Markdown 格式发送 (aibot_respond_msg 不一定支持 mixed)
            md_content = []
            if text_parts:
                text = "".join(text_parts)
                if self.bot_prefix:
                    text = self.bot_prefix + text
                md_content.append(text)

            for image_url in image_parts:
                md_content.append(f"\n\n![图片]({image_url})")

            if md_content:
                text = "\n".join(md_content)
                msg_dict = build_markdown_message(text)
                msg = f"[DEBUG WeCom] send_content_parts: 即将发送 Markdown (含图片) 消息, content={text[:100]}..."
                print(msg, flush=True)
                await self._send_response(req_id, msg_dict)
            else:
                print(f"[DEBUG WeCom] send_content_parts: 无有效内容发送", flush=True)
        except Exception as e:
            print(f"[DEBUG WeCom] send_content_parts 异常: {e}", flush=True)
            logger.error(f"发送多部分内容异常: {e}")
            import traceback
            traceback.print_exc()

    async def _send_response(self, req_id: str, msg: dict) -> None:
        """发送响应消息

        Args:
            req_id: 关联的请求 ID
            msg: 消息体
        """
        import sys
        try:
            # 构造回复消息
            response_msg = {
                "cmd": "aibot_respond_msg",
                "headers": {"req_id": req_id},
                "body": msg,
            }

            print(f"[DEBUG WeCom] _send_response: 即将发送 {json.dumps(response_msg, ensure_ascii=False)[:200]}...", flush=True)

            # 检查是否在正确的事件循环中
            current_loop = asyncio.get_event_loop()
            print(f"[DEBUG WeCom] _send_response: current_loop={current_loop}, ws_loop={self._loop}, same={current_loop == self._loop}", flush=True)

            if current_loop != self._loop:
                print(f"[DEBUG WeCom] _send_response: 跨线程调用，使用 run_coroutine_threadsafe", flush=True)
                
                # 检查事件循环是否运行
                if not self._loop or not self._loop.is_running():
                    print(f"[DEBUG WeCom] _send_response ERROR: WebSocket 事件循环未运行!", flush=True)
                    logger.error("WebSocket 事件循环未运行，无法跨线程发送消息")
                    return

                # 跨线程调用，使用 run_coroutine_threadsafe
                future = asyncio.run_coroutine_threadsafe(
                    self._send_json(response_msg), self._loop
                )
                
                # 添加完成后的回调，用于记录错误
                def _on_sent(fut: asyncio.Future):
                    try:
                        fut.result()
                        print(f"[DEBUG WeCom] _send_response: 跨线程发送成功", flush=True)
                    except Exception as e:
                        print(f"[DEBUG WeCom] _send_response: 跨线程发送失败: {e}", flush=True)
                        logger.error(f"跨线程发送消息失败: {e}")
                
                future.add_done_callback(_on_sent)
                print(f"[DEBUG WeCom] _send_response: 跨线程调用已提交", flush=True)
            else:
                print(f"[DEBUG WeCom] _send_response: 同一线程，直接发送", flush=True)
                await self._send_json(response_msg)
                print(f"[DEBUG WeCom] _send_response: 同一线程发送完成", flush=True)

            logger.info(f"[WeCom] 发送消息成功: msgtype={msg.get('msgtype')}")

        except Exception as e:
            print(f"[DEBUG WeCom] _send_response 异常: {e}", flush=True)
            logger.error(f"[WeCom] 发送消息异常: {e}")
            import traceback
            traceback.print_exc()

    async def _send_json(self, data: dict) -> None:
        """发送 JSON 数据（不等待响应）

        Args:
            data: 要发送的数据
        """
        import sys
        try:
            print(f"[DEBUG WeCom] _send_json: 准备发送, cmd={data.get('cmd')}", flush=True)

            async with self._ws_lock:
                print(f"[DEBUG WeCom] _send_json: 获取锁成功", flush=True)

                if self._ws is None:
                    print(f"[DEBUG WeCom] _send_json: WebSocket 是 None!", flush=True)
                    raise ConnectionError("WebSocket 连接已关闭")

                if self._ws.closed:
                    print(f"[DEBUG WeCom] _send_json: WebSocket 已关闭!", flush=True)
                    raise ConnectionError("WebSocket 连接已关闭")

                print(f"[DEBUG WeCom] _send_json: 即将发送 JSON", flush=True)
                await self._ws.send_json(data)
                print(f"[DEBUG WeCom] _send_json: JSON 发送成功", flush=True)

        except Exception as e:
            print(f"[DEBUG WeCom] _send_json 异常: {e}", flush=True)
            import traceback
            traceback.print_exc()
            raise

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
            print(f"[DEBUG WeCom] _save_req_id 完成: key={key}, req_id={req_id}")
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
