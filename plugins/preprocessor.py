import time
from typing import Dict

from nonebot import on_message, get_driver
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, GroupMessageEvent
from nonebot.message import event_preprocessor

from kusa_base import config
import dbConnection.db as db
from nb2_compat import scheduled_job

lastSpellRecord: Dict[int, float] = dict()
repeatWarning: Dict[int, int] = dict()


@event_preprocessor
async def preprocessor(bot: Bot, event: Event):
    """
    NoneBot2-compatible message preprocessor that replicates the
    original anti-spam and blacklist logic for commands starting with '!'.
    """
    global lastSpellRecord, repeatWarning

    if not isinstance(event, MessageEvent):
        return

    raw_message = event.get_plaintext()
    if not raw_message.startswith("!"):
        return

    user_id = event.user_id
    await db.createUser(user_id)

    if user_id in config["qq"]["ban"]:
        from nonebot.exception import IgnoredException
        raise IgnoredException("此人处于除草器指令黑名单，跳过指令响应")

    if isinstance(event, GroupMessageEvent):
        if event.group_id not in config["group"]["allow"]:
            from nonebot.exception import IgnoredException
            raise IgnoredException("非可用群，跳过指令响应")

    # 记录触发指令时间，屏蔽刷指令
    warningCount = repeatWarning.get(user_id)
    if warningCount and warningCount >= 5:
        from nonebot.exception import IgnoredException
        raise IgnoredException("刷指令人员，暂时屏蔽所有服务")

    now_ts = time.time()
    recordTimeStamp = lastSpellRecord.get(user_id)
    if recordTimeStamp and now_ts - recordTimeStamp <= 0.5:
        warningCount = (warningCount or 0) + 1
        repeatWarning[user_id] = warningCount
        if warningCount >= 8:
            msg = "识别到恶意刷指令。除草器所有服务对你停止1小时。"
            if isinstance(event, GroupMessageEvent):
                await bot.send_group_msg(group_id=event.group_id, message=msg)
            else:
                await bot.send_private_msg(user_id=user_id, message=msg)

    lastSpellRecord[user_id] = now_ts


@scheduled_job("interval", minutes=67, misfire_grace_time=None)
async def cleanWarningRunner():
    global repeatWarning
    for key in list(repeatWarning.keys()):
        repeatWarning[key] = 0

