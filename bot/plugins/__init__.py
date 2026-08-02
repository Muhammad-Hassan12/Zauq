import os
import importlib
import logging
from discord.ext import commands

logger = logging.getLogger("zauq.plugins")

async def load_plugins(bot: commands.Bot):
    """
    Scans the bot/plugins directory and dynamically loads any community plugin cogs.
    Each plugin file must contain an `async def setup(bot: commands.Bot)` entrypoint.
    """
    plugins_dir = os.path.dirname(__file__)
    if not os.path.exists(plugins_dir):
        return

    loaded_count = 0
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            plugin_name = f"bot.plugins.{filename[:-3]}"
            try:
                await bot.load_extension(plugin_name)
                logger.info(f"Loaded community plugin extension: {plugin_name}")
                loaded_count += 1
            except Exception as e:
                logger.warning(f"Failed to load plugin {plugin_name}: {e}")

    if loaded_count > 0:
        logger.info(f"Successfully loaded {loaded_count} plugin(s).")
