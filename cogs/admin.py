import discord
from discord.ext import commands
from discord import app_commands
import logging
from database import set_announcement_channel, get_active_survey

logger = logging.getLogger('discord')

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="공지채널설정", description="[관리자 전용] 주기적으로 설문조사 결과 및 새 주제가 공지될 채널을 지정합니다.")
    @app_commands.default_permissions(administrator=True)
    async def set_announce_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await set_announcement_channel(interaction.guild_id, channel.id)
        logger.info(f"Guild {interaction.guild_id} set announcement channel to {channel.id}")
        
        await interaction.response.send_message(
            f"✅ 알림 공지 채널이 {channel.mention} (으)로 설정되었습니다.", 
            ephemeral=True
        )

        intro_text = (
            "🎉 **레전드 갈드컵 봇이 이 채널에 연결되었습니다!** 🎉\n"
            "이곳에서 주기적으로 새롭고 흥미진진한 갈드컵 매치가 배달됩니다.\n\n"
            "💡 **[봇과 함께 노는 방법]**\n"
            "1️⃣ 채팅창에 `/투표` 를 입력해 현재 진행 중인 주제에 익명으로 투표하고 이유를 남겨주세요!\n"
            "   *(새 주제 알림 메시지 하단의 버튼을 눌러 바로 참여할 수도 있습니다)*\n"
            "2️⃣ 기발한 아이디어가 떠올랐다면 `/주제제시` 로 갈드컵 주제를 직접 건의하세요.\n"
            "3️⃣ 사람들의 익명 반응이 궁금하다면 언제든 `/현재상황` 을 쳐보세요!\n\n"
            "*(봇 관리자에 의해 채택된 신규 주제와 투표 마감 결과가 이 채널에 자동으로 송출되며, 최신 주제는 항상 채널 상단에 **고정(Pin)**됩니다.)*\n"
            "⚠️ **주의**: 설정된 공지 채널을 임의로 삭제하거나 봇의 접근(메시지 쓰기/고정) 권한을 뺏으면 봇 알림이 영구 정지될 수 있습니다. 채널 변경 시 반드시 다시 설정해주세요."
        )

        # 등록되는 즉시 안내 메세지 전송
        try:
            await channel.send(intro_text)
        except discord.Forbidden:
            logger.warning(f"Failed to send intro message to {channel.id} due to permission issue.")
            return

        survey = await get_active_survey()
        if survey:
            embed = discord.Embed(
                title=f"📢 현재 진행 중인 갈드컵 주제",
                description=f"**{survey['topic']}**",
                color=discord.Color.gold()
            )
            embed.add_field(name="선택지", value="\n".join([f"- {opt}" for opt in survey['options']]), inline=False)
            embed.set_footer(text="설문조사 참가 방법: 채팅창에 `/투표` 를 입력해주세요!")
            
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

    @app_commands.command(name="알림설정", description="[관리자 전용] 갈드컵 새 주제 및 결과 공지를 켜거나 끕니다.")
    @app_commands.describe(enable="알림 송출 여부 (True=켜기, False=끄기)")
    @app_commands.default_permissions(administrator=True)
    async def toggle_announcement(self, interaction: discord.Interaction, enable: bool):
        from database import set_announcement_enabled
        await set_announcement_enabled(interaction.guild_id, 1 if enable else 0)
        status = "✅ 켜짐(ON)" if enable else "🔇 꺼짐(OFF)"
        await interaction.response.send_message(f"현재 서버의 갈드컵 공지 알림이 **{status}** 상태로 변경되었습니다.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
