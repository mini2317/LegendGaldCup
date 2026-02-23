import discord
from discord.ext import commands
from discord import app_commands
import logging
import database
import csv
import io
import asyncio

logger = logging.getLogger('discord')

class SuggestTopicModal(discord.ui.Modal, title='새로운 갈드컵 주제 제시하기'):
    topic = discord.ui.TextInput(
        label='1. 갈드컵 주제',
        style=discord.TextStyle.short,
        placeholder='예: 평생 탕수육 소스는?',
        required=True,
        max_length=100
    )
    
    options = discord.ui.TextInput(
        label='2. 선택 옵션 (쉼표로 구분)',
        style=discord.TextStyle.short,
        placeholder='예: 부먹, 찍먹',
        required=True,
        max_length=200
    )

    allow_multiple = discord.ui.TextInput(
        label='3. 중복투표 가능여부 (O/X)',
        style=discord.TextStyle.short,
        placeholder='O 또는 X',
        required=True,
        max_length=1
    )

    allow_short = discord.ui.TextInput(
        label='4. 기타 단답형 허용여부 (O/X)',
        style=discord.TextStyle.short,
        placeholder='O 또는 X',
        required=True,
        max_length=1
    )

    image_url = discord.ui.TextInput(
        label='5. 대표 이미지 URL (선택사항)',
        style=discord.TextStyle.short,
        placeholder='http://... (비워둬도 됨)',
        required=False,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        topic_text = self.topic.value
        
        f = io.StringIO(self.options.value)
        try:
            reader = csv.reader(f, skipinitialspace=True)
            options_list = next(reader)
            options_list = [opt.strip() for opt in options_list if opt.strip()]
        except Exception:
            options_list = [opt.strip() for opt in self.options.value.split(',') if opt.strip()]
        
        if len(options_list) < 2:
            await interaction.response.send_message("옵션은 쉼표(,)로 구분하여 최소 2개 이상 입력해야 합니다.", ephemeral=True)
            return

        parsed_options = []
        for opt in options_list:
            if ":" in opt:
                name, desc = opt.split(":", 1)
                parsed_options.append({"name": name.strip(), "desc": desc.strip()})
            else:
                parsed_options.append({"name": opt.strip(), "desc": ""})

        is_multiple = self.allow_multiple.value.upper() == 'O'
        is_short = self.allow_short.value.upper() == 'O'
        img_val = self.image_url.value.strip() if self.image_url.value else None

        await database.suggest_topic(topic_text, parsed_options, is_multiple, is_short, interaction.user.id, img_val)
        
        await interaction.response.send_message(
            "✅ 성공적으로 주제 의견을 제출했습니다! 3일 뒤 로테이션 때 추첨 및 평가에 반영됩니다.",
            ephemeral=True
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"SuggestTopicModal error: {error}")
        await interaction.response.send_message("❌ 주제 제출 중 오류가 발생했습니다.", ephemeral=True)


class VoteOpinionModal(discord.ui.Modal):
    def __init__(self, survey_id: int, selected_option: str):
        super().__init__(title="투표에 대한 의견 작성")
        self.survey_id = survey_id
        self.selected_option = selected_option

        self.opinion = discord.ui.TextInput(
            label=f'[{selected_option}] 선택에 대한 의견 (익명)',
            style=discord.TextStyle.long,
            placeholder='300자 이내로 왜 이 옵션을 선택했는지 남겨주세요.',
            required=False,
            max_length=300
        )
        self.add_item(self.opinion)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        server_id = interaction.guild_id or 0
        opinion_text = self.opinion.value.strip()

        # Save or update vote in database
        await database.save_vote(self.survey_id, user_id, server_id, self.selected_option, opinion_text)

        await interaction.response.send_message(
            f"✅ **[{self.selected_option}]** (으)로 투표와 익명 의견이 기록되었습니다!\n(현재상황을 보려면 `/현재상황`을 입력하세요.)",
            ephemeral=True
        )


class VoteShortAnswerModal(discord.ui.Modal):
    def __init__(self, survey_id: int, other_choices: list):
        super().__init__(title="기타 옵션 직접 입력 및 의견")
        self.survey_id = survey_id
        self.other_choices = other_choices

        self.custom_option = discord.ui.TextInput(
            label='새로 추가할 선택지 (단답형)',
            style=discord.TextStyle.short,
            placeholder='여기에 원하는 옵션을 짧게 적어주세요 (최대 30자)',
            required=True,
            max_length=30
        )
        self.add_item(self.custom_option)

        self.opinion = discord.ui.TextInput(
            label='이 선택지에 대한 의견 (익명)',
            style=discord.TextStyle.long,
            placeholder='300자 이내로 왜 이 옵션을 선택했는지 남겨주세요.',
            required=False,
            max_length=300
        )
        self.add_item(self.opinion)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        server_id = interaction.guild_id or 0
        opinion_text = self.opinion.value.strip()
        custom_opt = self.custom_option.value.strip()

        # Combine short answer with other choices if multiple
        final_choices = self.other_choices + [custom_opt]
        joined_selections = ", ".join(final_choices)

        # Save or update vote in database
        await database.save_vote(self.survey_id, user_id, server_id, joined_selections, opinion_text)

        await interaction.response.send_message(
            f"✅ **[{joined_selections}]** (으)로 투표와 익명 의견이 기록되었습니다!\n(현재상황을 보려면 `/현재상황`을 입력하세요.)",
            ephemeral=True
        )


class VoteSelectView(discord.ui.View):
    def __init__(self, survey_id: int, options: list, allow_short: bool, allow_multiple: bool):
        super().__init__(timeout=None)
        self.survey_id = survey_id
        self.options = options
        self.allow_short = allow_short
        self.allow_multiple = allow_multiple
        
        select_options = []
        for opt in options:
            if isinstance(opt, dict):
                label = opt.get('name', '옵션')[:100]
                desc = opt.get('desc', '')[:100]
                select_options.append(discord.SelectOption(label=label, description=desc if desc else None, value=label))
            else:
                label = str(opt)[:100]
                select_options.append(discord.SelectOption(label=label, value=label))
                
        if self.allow_short:
            select_options.append(discord.SelectOption(label="기타 (직접입력)", value="##SHORT_ANSWER##"))
            
        select = discord.ui.Select(
            placeholder="투표할 옵션을 선택하세요 (다중선택 가능)" if allow_multiple else "투표할 옵션을 선택하세요",
            min_values=1,
            max_values=len(select_options) if allow_multiple else 1,
            options=select_options[:25]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_values = interaction.data['values']
        
        # Determine if SHORT_ANSWER was selected
        has_short = "##SHORT_ANSWER##" in selected_values
        
        # Check if user already voted.
        existing_vote = await database.get_user_vote(self.survey_id, interaction.user.id)
        
        if has_short:
            # Drop the placeholder from the list to pass the rest of the choices to the modal
            other_choices = [v for v in selected_values if v != "##SHORT_ANSWER##"]
            await interaction.response.send_modal(VoteShortAnswerModal(self.survey_id, other_choices))
        else:
            # Join multiple selections with a comma
            joined_selections = ", ".join(selected_values)
            await interaction.response.send_modal(VoteOpinionModal(self.survey_id, joined_selections))
        
        # Send DM in background
        if existing_vote:
            async def send_warning_dm():
                try:
                    await interaction.user.send(
                        f"⚠️ **이미 현 갈드컵에 투표하셨습니다!**\n"
                        f"방금 띄워드린 팝업창을 통해 새로운 의견을 제출하시면 기존 투표 내역이 덮어씌워집니다."
                    )
                except discord.Forbidden:
                    logger.debug(f"Could not send DM to {interaction.user.name} regarding existing vote.")
            
            asyncio.create_task(send_warning_dm())


class Survey(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="주제제시", description="재미있는 갈드컵 다음 주제를 제시합니다.")
    async def suggest_topic(self, interaction: discord.Interaction):
        has_pending = await database.has_pending_suggestion(interaction.user.id)
        if has_pending:
            await interaction.response.send_message("❌ 이미 제출하여 대기 중인 갈드컵 주제가 있습니다. 한 번에 하나의 주제만 제안할 수 있습니다.\n(제출하신 주제가 봇 관리자에 의해 채택되거나 기각된 이후에 새 주제를 제안할 수 있습니다.)", ephemeral=True)
            return
            
        await interaction.response.send_modal(SuggestTopicModal())

    @app_commands.command(name="투표", description="현재 진행 중인 갈드컵에 익명으로 투표와 의견을 남깁니다.")
    async def vote(self, interaction: discord.Interaction):
        survey = await database.get_active_survey()
        if not survey:
            await interaction.response.send_message("❌ 현재 진행 중인 갈드컵 주제가 없습니다.", ephemeral=True)
            return

        view = VoteSelectView(survey['id'], survey['options'], survey['allow_short_answer'], survey['allow_multiple'])
        
        embed = discord.Embed(
            title="🤔 [투표 진행 중]",
            description=f"**{survey['topic']}**\n\n아래 선택바를 눌러 원하는 옵션을 고르고 의견을 작성해주세요.",
            color=discord.Color.blue()
        )
        
        # /투표를 쳤을 때 대화 기록을 남기지 않도록 ephemeral 설정
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="현재상황", description="현재 진행 중인 갈드컵의 내용과 타 유저들의 익명 반응을 열람합니다.")
    async def current_status(self, interaction: discord.Interaction):
        survey = await database.get_active_survey()
        if not survey:
            await interaction.response.send_message("❌ 현재 진행 중인 갈드컵 주제가 없습니다.", ephemeral=True)
            return

        votes = await database.get_votes_for_survey(survey['id'])
        
        total_votes = len(votes)
        
        embed = discord.Embed(
            title=f"📊 갈드컵 현황: {survey['topic']}",
            description=f"현재 총 {total_votes}명이 투표에 참여했습니다.",
            color=discord.Color.gold()
        )
        
        # 옵션별 통계 표시 (다중선택의 경우 각각을 카운트)
        option_names = [opt.get('name', str(opt)) if isinstance(opt, dict) else str(opt) for opt in survey['options']]
        option_counts = {name: 0 for name in option_names}
        for v in votes:
            chosen = [c.strip() for c in v['selected_option'].split(',')]
            for c in chosen:
                if c in option_counts:
                    option_counts[c] += 1
                else:
                    option_counts[c] = 1 # unexpected option fallback

        # 다중투표의 특성상 총 투표수(인원)보다 득표수 합계가 클 수 있음
        stat_text = "\n".join([f"**{opt}**: {cnt}표" for opt, cnt in sorted(option_counts.items(), key=lambda item: item[1], reverse=True)])
        embed.add_field(name="투표 분포", value=stat_text if stat_text else "아직 투표가 없습니다.", inline=False)
        
        # 의견 나열 (최근 10개 정도 익명으로)
        recent_opinions = [v for v in list(votes) if v['opinion']]
        
        if recent_opinions:
            opinions_text = ""
            for v in recent_opinions[:10]: # 10개로 제한
                opinions_text += f"\n- [{v['selected_option']}] \"{v['opinion']}\""
            embed.add_field(name="👀 최근 익명 의견들", value=opinions_text, inline=False)
        else:
            embed.add_field(name="👀 의견", value="아직 작성된 의견이 없습니다.", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="통계", description="최근 종료된 5개의 갈드컵 결과 요약을 보여줍니다.")
    async def statistics(self, interaction: discord.Interaction):
        past_surveys = await database.get_past_surveys(5)
        if not past_surveys:
            await interaction.response.send_message("❌ 아직 종료된 갈드컵이 없습니다.", ephemeral=True)
            return

        import json
        embed = discord.Embed(
            title="📊 최근 갈드컵 통계 (최대 5개)",
            color=discord.Color.purple()
        )

        for s in past_surveys:
            votes = await database.get_votes_for_survey(s['id'])
            total_votes = len(votes)
            raw_options = json.loads(s['options'])
            
            option_names = [opt.get('name', str(opt)) if isinstance(opt, dict) else str(opt) for opt in raw_options]
            options_counts = {name: 0 for name in option_names}
            for v in votes:
                chosen = [c.strip() for c in v['selected_option'].split(',')]
                for c in chosen:
                    if c in options_counts:
                        options_counts[c] += 1
                    else:
                        options_counts[c] = 1
            
            stats_str = f"총 투표수: {total_votes}명 참여\n"
            if total_votes > 0:
                best_opt = max(options_counts, key=options_counts.get)
                stats_str += f"**🏆 우승: {best_opt}** ({options_counts[best_opt]}표)"
            else:
                stats_str += "투표 없음"

            time_str = s['end_time'] if s['end_time'] else "알 수 없음"
            embed.add_field(name=f"Q. {s['topic']} ({time_str[:10]})", value=stats_str, inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(Survey(bot))
