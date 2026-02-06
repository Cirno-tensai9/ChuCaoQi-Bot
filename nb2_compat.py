from typing import Awaitable, Callable

import nonebot
from nonebot import on_command as nb2_on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageSegment,
    MessageEvent,
    GroupMessageEvent,
)

# Compat for NoneBot1 CQHttpError (NB2 uses adapter exceptions)
try:
    from nonebot.adapters.onebot.v11 import ActionFailed as CQHttpError
except Exception:
    CQHttpError = Exception

# Re-export for plugins that used "from nonebot import Message, MessageSegment"
__all__ = [
    "CommandSession",
    "CQHttpError",
    "Message",
    "MessageSegment",
    "NLPSession",
    "RequestSession",
    "get_bot",
    "on_command",
    "on_natural_language",
    "on_request",
    "on_startup",
    "on_websocket_connect",
    "scheduled_job",
]


def get_bot() -> Bot:
    """Return the first available OneBot v11 bot (replaces nonebot.get_bot())."""
    bots = list(nonebot.get_bots().values())
    if not bots:
        raise RuntimeError("No bot connected yet (get_bot called before any adapter connected).")
    return bots[0]


class CommandSession:
    """
    Minimal compatibility shim to run existing NoneBot1-style command
    handlers on top of NoneBot2.
    """

    def __init__(self, bot: Bot, event: MessageEvent, args: Message):
        self._bot = bot
        self._event = event

        # Plain text arguments after the command name
        self.current_arg_text = args.extract_plain_text()
        self.current_arg = self.current_arg_text  # decorator.py checks 'CQ:' in session.current_arg

        ctx = {"user_id": event.user_id, "message_id": event.message_id}
        if isinstance(event, GroupMessageEvent):
            ctx["group_id"] = event.group_id
            ctx["sender"] = {"nickname": event.sender.nickname or ""}
        self.ctx = ctx

    @property
    def event(self) -> MessageEvent:
        return self._event

    @property
    def bot(self) -> Bot:
        return self._bot

    async def send(self, message):
        await self._bot.send(event=self._event, message=message)


def on_command(*args, **kwargs):
    """
    Wrapper around NoneBot2's on_command that passes a CommandSession
    to legacy handlers instead of (bot, event, state, ...).
    """
    matcher = nb2_on_command(*args, **kwargs)

    def decorator(func: Callable[[CommandSession], Awaitable[None]]):
        @matcher.handle()
        async def _handler(
            bot: Bot,
            event: MessageEvent,
            args: Message = CommandArg(),
        ):
            session = CommandSession(bot, event, args)
            await func(session)

        return _handler

    return decorator


try:
    # Scheduler compatibility for jobs using nonebot.scheduler.scheduled_job
    from nonebot_plugin_apscheduler import scheduler

    def scheduled_job(*args, **kwargs):
        """
        Thin wrapper so legacy code can call scheduled_job with the same
        signature as apscheduler's add_job.
        """

        def decorator(func):
            scheduler.add_job(func, *args, **kwargs)
            return func

        return decorator

except Exception:  # pragma: no cover - scheduler plugin not available
    scheduler = None

    def scheduled_job(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


# ---- Request / lifecycle compat (OneBot v11) ----
from nonebot import on
from nonebot.adapters.onebot.v11 import (
    GroupRequestEvent,
    FriendRequestEvent,
)

_nlp_handlers = []


class RequestSession:
    """Shim for NoneBot1 RequestSession; wraps OneBot v11 request events and bot."""

    def __init__(self, bot: Bot, event):
        self.bot = bot
        self.event = event

    async def approve(self, **kwargs):
        await self.event.approve(self.bot, **kwargs)

    async def reject(self, reason: str = "", **kwargs):
        await self.event.reject(self.bot, reason=reason, **kwargs)


def _on_group_request():
    matcher = on(type=GroupRequestEvent)

    @matcher.handle()
    async def _handle(bot: Bot, event: GroupRequestEvent):
        session = RequestSession(bot, event)
        for handler in _request_handlers.get("group", []):
            await handler(session)

    return matcher


def _on_friend_request():
    matcher = on(type=FriendRequestEvent)

    @matcher.handle()
    async def _handle(bot: Bot, event: FriendRequestEvent):
        session = RequestSession(bot, event)
        for handler in _request_handlers.get("friend", []):
            await handler(session)

    return matcher


_request_handlers = {"group": [], "friend": []}


def on_request(request_type: str):
    """Register a handler for group or friend request (compat with NoneBot1 on_request)."""

    def decorator(func):
        if request_type not in _request_handlers:
            _request_handlers[request_type] = []
        _request_handlers[request_type].append(func)
        return func

    return decorator


# Register matchers once so request handlers are dispatched (only when running under NoneBot)
try:
    _on_group_request()
    _on_friend_request()
except Exception:
    pass


# ---- Bot connect: run friend list init when first bot is available ----
_bot_connect_handlers = []


def on_websocket_connect(func):
    """Register a handler to run when a bot connects (e.g. init friend list)."""
    _bot_connect_handlers.append(func)
    return func


def on_startup(func):
    """Register a handler to run on driver startup (compat with NoneBot1 @on_startup)."""
    try:
        nonebot.get_driver().on_startup(func)
    except Exception:
        pass  # e.g. running without NoneBot (e.g. discord_bot.py)
    return func


async def _run_bot_connect_handlers(bot: Bot):
    for f in _bot_connect_handlers:
        try:
            await f(bot)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"bot_connect handler error: {e}")


try:
    nonebot.get_driver().on_bot_connect(_run_bot_connect_handlers)
except Exception:
    pass  # e.g. running without NoneBot (e.g. discord_bot.py)


# ---- Natural language / NLP compat ----
class NLPSession:
    """Shim for NoneBot1 NLPSession; wraps Bot and MessageEvent for NLP handlers."""

    def __init__(self, bot: Bot, event: MessageEvent):
        self.bot = bot
        self.event = event
        self._ctx = {
            "user_id": event.user_id,
            "message": event.message,
            "message_id": event.message_id,
        }
        if isinstance(event, GroupMessageEvent):
            self._ctx["group_id"] = event.group_id

    @property
    def ctx(self):
        return self._ctx


def on_natural_language(keywords=None, only_to_me=False):
    """Register an NLP handler (runs on every message with low priority)."""

    def decorator(func):
        _nlp_handlers.append((func, only_to_me))
        return func

    return decorator


try:
    from nonebot import on_message
    _nlp_matcher = on_message(priority=99, block=False)

    @_nlp_matcher.handle()
    async def _nlp_dispatch(bot: Bot, event: MessageEvent):
        session = NLPSession(bot, event)
        for func, only_to_me in _nlp_handlers:
            if only_to_me and not event.to_me:
                continue
            try:
                await func(session)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"NLP handler error: {e}")
except Exception:
    pass  # e.g. running without NoneBot (discord_bot.py)

