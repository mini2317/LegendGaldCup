import discord
from discord.ext import commands
from discord import app_commands
import os
import database

MASTER_ADMIN_ID = int(os.getenv("MASTER_ADMIN_ID", "0"))

class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="소개", description="레전드 갈드컵 봇을 소개합니다.")
    async def introduce(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎯 레전드 갈드컵 (Legend GaldCup)",
            description=(
                "디스코드를 통해 익명으로 2가지(또는 그 이상)의 선택지 중 하나를 고르고, "
                "300자 이내의 의견을 남기며 즐기는 익명 토론/투표 봇입니다!\n\n"
                "**기능 특징**\n"
                "• **익명 투표**: 누가 투표했는지는 저장되지 않고 익명으로 기록됩니다.\n"
                "• **주기적 갱신**: 3일 단위로 새로운 주제가 선정되고 이전 결과가 공유됩니다.\n"
                "• **AI 마스터 (Gemini)**: 제출된 주제를 심사하고, 적절한 주제가 없으면 직접 주제를 만듭니다.\n"
                "• **서버 간 통신**: 우리 서버의 의견과 다른 무작위 서버의 익명 반응을 교환해 보는 신선한 재미가 있습니다."
            ),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="도움말", description="명령어 목록과 사용법을 확인합니다.")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📜 레전드 갈드컵 명령어 도움말",
            color=discord.Color.green()
        )
        
        embed.add_field(name="/소개", value="봇에 대한 간단한 소개를 봅니다.", inline=False)
        embed.add_field(name="/도움말", value="현재 보고 계신 도움말을 출력합니다.", inline=False)
        embed.add_field(name="/투표", value="현재 진행 중인 주제에 투표하고 익명 의견(300자 이내)을 남깁니다. (다시 입력 시 수정됩니다)", inline=False)
        embed.add_field(name="/현재상황", value="현재 진행 중인 주제와 다른 사람들의 익명 의견을 열람합니다.", inline=False)
        embed.add_field(name="/주제제시", value="다음 3일 간 진행할 재미있는 갈드컵 주제와 옵션들을 모집합니다. (제한 없이 언제든 여러 개 제출 가능)", inline=False)
        embed.add_field(name="/통계 (준비중)", value="과거 설문조사들의 전체 결과 및 통계를 조회합니다.", inline=False)
        embed.add_field(name="/공지채널설정", value="[서버 관리자 전용] 3일 주기로 설문 결과 및 새 주제가 공지될 채널을 지정합니다.", inline=False)
        embed.add_field(name="/알림설정", value="[서버 관리자 전용] 지정된 채널로 향하는 갈드컵 자동 공지를 켜고(True) 끌(False) 수 있습니다.", inline=False)
        
        # 봇 관리자 확인 로직
        is_bot_admin = await database.is_bot_admin(interaction.user.id, MASTER_ADMIN_ID)
        is_master = (interaction.user.id == MASTER_ADMIN_ID)

        if is_bot_admin or is_master:
            embed.add_field(name="\u200b", value="**🛡️ 봇 관리자 전용 명령어 (슬래시 `/` 대신 느낌표 `!` 사용)**", inline=False)
            embed.add_field(name="!관리자설명서", value="레전드 갈드컵 봇의 관리 시스템 및 흐름(Queue 시스템 등)을 안내합니다.", inline=False)
            embed.add_field(name="!관리자목록", value="현재 봇 기능 권한을 부여받은 관리자 리스트를 열람합니다.", inline=False)
            embed.add_field(name="!주제관리", value="DM으로 대중이 건의한 아이디어 주제들을 열람하고, 검토를 통해 진행 `대기열(Queue)`로 승격시킵니다.", inline=False)
            embed.add_field(name="!대기열관리", value="DM으로 실제 송출 예정인 `대기열(Queue)` 안의 주제 현황 및 순서를 관리합니다.", inline=False)
            embed.add_field(name="!AI주제충전 <개수>", value="[1~5] AI가 창작한 주제를 지정한 개수만큼 `대기열(Queue)`에 다이렉트로 장전합니다.", inline=False)
            embed.add_field(name="!주제강제종료", value="현재 진행 중인 투표를 즉시 마감하고 다음 주제로 순서를 넘깁니다.", inline=False)
            
            if is_master:
                embed.add_field(name="\u200b", value="**👑 최고 관리자 전용 명령어**", inline=False)
                embed.add_field(name="!부관리자추가 [@유저]", value="봇을 관리할 부관리자를 새로 임명합니다.", inline=False)
                embed.add_field(name="!부관리자제거 [@유저]", value="기존 부관리자의 권한을 박탈합니다.", inline=False)
                embed.add_field(name="!업데이트", value="Github에서 최신 코드를 pull 받고 봇을 무중단 리로드합니다.", inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
