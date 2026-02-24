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
                "• **간편 참여**: 봇이 띄운 메시지 하단의 버튼을 눌러 바로 투표하거나 `/투표` 명령어로 참여할 수 있습니다.\n"
                "• **주기적 갱신**: 3일 단위로 새 주제가 갱신되며, 최신 주제는 채널 상단에 항상 **고정(Pin)**됩니다.\n"
                "• **AI 마스터 (Gemini)**: 제출된 주제를 심사하고, 적절한 주제가 없으면 직접 주제를 만듭니다.\n"
                "• **익명 의견 열람**: 다양한 유저들의 생생하고 날것인 반응들을 페이지를 넘겨가며 모두 모아볼 수 있는 재미가 있습니다."
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
        
        embed.add_field(
            name="🎮 일반 명령어",
            value=(
                "`/소개`: 봇에 대한 간단한 소개를 봅니다.\n"
                "`/도움말`: 현재 보고 계신 도움말을 출력합니다.\n"
                "`/투표`: 현재 진행 중인 주제에 투표하고 익명 의견(300자 이내)을 남깁니다. (다시 입력 시 수정)\n"
                "`/현재상황`: 현재 진행 중인 주제와 다른 사람들의 익명 의견을 열람합니다.\n"
                "`/주제제시`: 다음 3일 간 진행할 재미있는 갈드컵 주제와 옵션들을 모집합니다.\n"
                "`/통계 (준비중)`: 과거 설문조사들의 전체 결과 및 통계를 조회합니다."
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ 서버 관리자 명령어",
            value=(
                "`/공지채널설정`: 3일 주기로 설문 결과 및 새 주제가 공지될 채널을 지정합니다.\n"
                "`/알림설정 [True/False]`: 지정된 채널로 향하는 갈드컵 자동 공지를 켜고 끌 수 있습니다."
            ),
            inline=False
        )
        
        # 봇 관리자 확인 로직
        is_bot_admin = await database.is_bot_admin(interaction.user.id, MASTER_ADMIN_ID)
        is_master = (interaction.user.id == MASTER_ADMIN_ID)

        if is_bot_admin or is_master:
            embed.add_field(
                name="🛡️ 봇 관리자 전용 명령어 (슬래시 `/` 대신 느낌표 `!` 사용)",
                value=(
                    "`!주제관리`: 유저 건의 주제 열람, 승인, 편집 및 AI 다듬기\n"
                    "`!대기열관리`: 다음 송출 큐(Queue) 확인, 순서 편집, 즉시 강제 송출\n"
                    "`!AI주제충전 <개수>`: AI 자체 생성 주제를 대기열 버퍼에 다이렉트 예약\n"
                    "`!주제강제종료`: 현재 진행 중인 투표를 즉시 마감하고 다음 주제 송출\n"
                    "`!관리자목록`: 권한을 부여받은 총/부관리자 현황 열람\n"
                    "`!관리자설명서`: 봇의 주제 큐(Queue) 송출 작동 원리 안내"
                ),
                inline=False
            )
            
            if is_master:
                embed.add_field(
                    name="👑 최고 관리자 전용 명령어",
                    value=(
                        "`!부관리자추가 [@유저] / !부관리자제거 [@유저]`: 봇 제어 권한 부여 및 박탈\n"
                        "`!업데이트`: Github 최신 코드 호출 및 **단절 없는 백그라운드 재부팅 적용 (종속성 자동 설치)**\n"
                        "*(봇에 심각한 오류 발생 시 해당 명령어를 서버 내에 전송하면 자가 복구합니다.)*"
                    ),
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
