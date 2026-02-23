import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import logging
from database import init_db

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('discord')

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN or TOKEN == "your_discord_bot_token_here":
    logger.error("Please set a valid DISCORD_TOKEN in the .env file.")
    exit(1)

# 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class LegendGaldCupBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # 데이터베이스 초기화
        await init_db()
        
        # Cogs 로드
        cogs = [
            'cogs.general',
            'cogs.admin',
            'cogs.survey',
            'cogs.events',
            'cogs.master',
            'cogs.botadmin'
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")
        
        # 슬래시 명령어 동기화
        await self.tree.sync()
        logger.info("Slash commands synced successfully.")

bot = LegendGaldCupBot()

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="갈드컵 진행 중"))

if __name__ == "__main__":
    bot.run(TOKEN)
