from os import path

import nonebot
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter


def main():
    # Initialize NoneBot2 with env-based configuration
    nonebot.init()

    driver = nonebot.get_driver()
    driver.register_adapter(OneBotV11Adapter)

    # Load scheduler plugin for cron/interval jobs
    nonebot.load_plugin("nonebot_plugin_apscheduler")

    # Load all local plugins under the plugins directory
    nonebot.load_plugins(path.join(path.dirname(__file__), "plugins"), "plugins")

    logger.info("starting NoneBot2 bot")
    nonebot.run()


if __name__ == "__main__":
    main()