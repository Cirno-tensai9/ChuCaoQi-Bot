from typing import Awaitable, Callable

from nonebot import on_command as nb2_on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageEvent,
    GroupMessageEvent,
)


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

        ctx = {"user_id": event.user_id}
        if isinstance(event, GroupMessageEvent):
            ctx["group_id"] = event.group_id
            ctx["sender"] = {"nickname": event.sender.nickname}
        self.ctx = ctx

    async def send(self, message: str):
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

