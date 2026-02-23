import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger('discord')

class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        
        owner = guild.owner
        if not owner:
            try:
                owner = await guild.fetch_member(guild.owner_id)
            except Exception:
                pass

        message_content = (
            f"안녕하세요! '{guild.name}' 서버에 '레전드 갈드컵' 봇을 초대해주셔서 감사합니다.\n\n"
            "이 봇은 3일마다 자동으로 새로운 논쟁/투표 주제를 던져주고 익명으로 의견을 받습니다.\n"
            "원활한 동작을 위해 **서버 관리자**님께서 디스코드 채팅창에 `/공지채널설정` 명령어를 입력하여 "
            "설문조사 결과 및 알림을 받을 채널을 지정해 주셔야 합니다.\n\n"
            "명령어를 통해 등록이 완료되면 즉시 현재 진행 중인 주제가 채널에 띄워집니다!"
            "주제가 선정될 때마다 공지를 받고싶지 않으시다면 `/알림설정` 명령어를 통해 알림을 끌 수 있습니다."
        )

        sent_dm = False
        if owner:
            try:
                await owner.send(message_content)
                sent_dm = True
                logger.info(f"Sent DM to owner of {guild.name}")
            except discord.Forbidden:
                logger.warning(f"Failed to send DM to owner of {guild.name}")
            except Exception as e:
                logger.error(f"Error sending DM to owner of {guild.name}: {e}")

        if not sent_dm:
            # DM이 막혀있다면 메시지를 보낼 수 있는 채널을 찾아서 핑합니다.
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    try:
                        mention = owner.mention if owner else "서버 관리자"
                        await channel.send(f"{mention}님! DM 전송이 막혀있어 이 채널에 메시지를 남깁니다.\n{message_content}")
                        logger.info(f"Sent ping message in channel {channel.name} of {guild.name}")
                        break
                    except Exception as e:
                        logger.error(f"Failed to send message in channel {channel.name}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
