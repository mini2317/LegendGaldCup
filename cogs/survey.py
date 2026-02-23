import discord
from discord.ext import commands
from discord import app_commands
import logging
import database
import csv
import io
import asyncio

logger = logging.getLogger('discord')

# ====================================================
# [추가] 고급 주제 제시 빌더 (Advanced Suggestion Builder)
# ====================================================

class SuggestTopicTitleModal(discord.ui.Modal, title='새로운 갈드컵 주제 제시하기'):
    def __init__(self, master_cog):
        super().__init__()
        self.master_cog = master_cog

    topic = discord.ui.TextInput(
        label='갈드컵 주제 (질문 / 최대 100자)',
        style=discord.TextStyle.short,
        placeholder='예: 평생 탕수육 소스는?',
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        topic_text = self.topic.value
        view = SuggestionBuilderView(topic_text, self.master_cog, interaction.user.id)
        embed = view.get_embed()
        # 이 유저에게만 보이는 임시 메뉴로 빌더 띄우기
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class AddOptionModal(discord.ui.Modal, title='선택지 추가하기'):
    def __init__(self, view: 'SuggestionBuilderView'):
        super().__init__()
        self.view = view

    opt_name = discord.ui.TextInput(
        label='선택지 이름 (최대 50자)',
        style=discord.TextStyle.short,
        placeholder='예: 부먹',
        required=True,
        max_length=50
    )
    opt_desc = discord.ui.TextInput(
        label='설명 (선택사항 / 최대 250자)',
        style=discord.TextStyle.long,
        placeholder='예: 소스를 부어 축축하게 먹는다',
        required=False,
        max_length=250
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.opt_name.value.strip()
        desc = self.opt_desc.value.strip()
        self.view.options.append({"name": name, "desc": desc})
        await interaction.response.edit_message(embed=self.view.get_embed(), view=self.view)

class RemoveOptionModal(discord.ui.Modal, title='선택지 지우기'):
    def __init__(self, view: 'SuggestionBuilderView'):
        super().__init__()
        self.view = view

    opt_index = discord.ui.TextInput(
        label='지울 선택지 번호',
        style=discord.TextStyle.short,
        placeholder='숫자만 입력 (예: 1)',
        required=True,
        max_length=2
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            idx = int(self.opt_index.value.strip()) - 1
            if 0 <= idx < len(self.view.options):
                popped = self.view.options.pop(idx)
                await interaction.response.edit_message(embed=self.view.get_embed(), view=self.view)
            else:
                await interaction.response.send_message("❌ 존재하는 번호가 아닙니다.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ 숫자만 입력해주세요.", ephemeral=True)

class AddLinkModal(discord.ui.Modal, title='콘텐츠 링크 첨부 (URL)'):
    def __init__(self, view: 'SuggestionBuilderView'):
        super().__init__()
        self.view = view

    link_url = discord.ui.TextInput(
        label='이미지 또는 참고 웹페이지 링크',
        style=discord.TextStyle.short,
        placeholder='http://... (이미지는 본문, 그 외는 텍스트 링크)',
        required=False,
        max_length=4000
    )

    async def on_submit(self, interaction: discord.Interaction):
        self.view.image_url = self.link_url.value.strip() if self.link_url.value.strip() else None
        await interaction.response.edit_message(embed=self.view.get_embed(), view=self.view)

class EditTopicTitleModal(discord.ui.Modal, title='주제 제목 수정'):
    def __init__(self, view: 'SuggestionBuilderView'):
        super().__init__()
        self.view = view

    topic_title = discord.ui.TextInput(
        label='새로운 주제 (질문 / 최대 100자)',
        style=discord.TextStyle.short,
        placeholder='수정할 주제를 입력하세요',
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        self.view.topic = self.topic_title.value.strip()
        await interaction.response.edit_message(embed=self.view.get_embed(), view=self.view)

class SuggestionBuilderView(discord.ui.View):
    def __init__(self, topic: str, master_cog, user_id: int):
        super().__init__(timeout=900) # 15분 타임아웃
        self.topic = topic
        self.master_cog = master_cog
        self.user_id = user_id
        self.options = []
        self.allow_multiple = False
        self.allow_short = False
        self.image_url = None

    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🛠️ 주제 제시 빌더",
            description=f"**주제: {self.topic}**\n\n아래 버튼들을 이용해 옵션을 추가하고 세부 설정을 관리하세요.",
            color=discord.Color.blurple()
        )
        
        if self.options:
            desc = ""
            for idx, opt in enumerate(self.options):
                if opt.get('desc'):
                    desc += f"**{idx+1}. {opt['name']}**\n- {opt['desc']}\n\n"
                else:
                    desc += f"**{idx+1}. {opt['name']}**\n"
            embed.add_field(name="현재 추가된 선택지", value=desc.strip(), inline=False)
        else:
            embed.add_field(name="현재 추가된 선택지", value="아직 선택지가 없습니다. `➕ 옵션 추가` 버튼을 눌러주세요.", inline=False)

        embed.add_field(name="🔄 중복 투표", value="[O] 허용" if self.allow_multiple else "[X] 불가", inline=True)
        embed.add_field(name="📝 단답형 허용", value="[O] 허용" if self.allow_short else "[X] 불가", inline=True)
        
        if self.image_url:
            import urllib.parse
            parsed = urllib.parse.urlparse(self.image_url)
            is_image = parsed.path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')) or 'pollinations.ai' in self.image_url
            
            if is_image:
                embed.set_thumbnail(url=self.image_url)
                embed.add_field(name="🖼️ 첨부 이미지", value="설정됨 (우측 썸네일 참조)", inline=False)
            else:
                embed.add_field(name="🔗 참고 링크", value=self.image_url, inline=False)
            
        return embed

    @discord.ui.button(label="옵션 추가", style=discord.ButtonStyle.secondary, emoji="➕", row=0)
    async def add_opt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddOptionModal(self))

    @discord.ui.button(label="옵션 제거", style=discord.ButtonStyle.secondary, emoji="➖", row=0)
    async def rem_opt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.options:
            await interaction.response.send_message("❌ 제거할 옵션이 없습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(RemoveOptionModal(self))

    @discord.ui.button(label="콘텐츠 첨부", style=discord.ButtonStyle.secondary, emoji="📎", row=0)
    async def link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddLinkModal(self)
        if self.image_url:
            modal.link_url.default = self.image_url
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="제목 수정", style=discord.ButtonStyle.secondary, emoji="✏️", row=0)
    async def edit_topic_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditTopicTitleModal(self)
        modal.topic_title.default = self.topic
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="중복 투표", style=discord.ButtonStyle.primary, emoji="🔄", row=1)
    async def toggle_multiple_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.allow_multiple = not self.allow_multiple
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="단답형 허용", style=discord.ButtonStyle.primary, emoji="📝", row=1)
    async def toggle_short_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.allow_short = not self.allow_short
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="AI 가공 (다듬기)", style=discord.ButtonStyle.blurple, emoji="🤖", row=1)
    async def ai_refine_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.options) < 2:
            await interaction.response.send_message("❌ AI 다듬기를 사용하려면 옵션을 최소 2개 이상 입력해야 합니다.", ephemeral=True)
            return
            
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        import cogs.master
        refined_data = await self.master_cog.refine_topic(self.topic, self.options) 
        
        if not refined_data:
            await interaction.followup.send("❌ AI 가공 처리에 실패했습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="🤖 AI가 가공한 추천 주제 구성",
            description=f"**원문:** {self.topic}\n**가공 후:** {refined_data['topic']}",
            color=discord.Color.purple()
        )
        
        desc = ""
        for idx, opt in enumerate(refined_data['options']):
            desc += f"**{idx+1}. {opt.get('name', '옵션')}**\n- {opt.get('desc', '')}\n\n"
            
        embed.add_field(name="가공된 선택지", value=desc.strip(), inline=False)
        
        if 'image_prompt' in refined_data:
            import urllib.parse
            prompt_encoded = urllib.parse.quote(refined_data['image_prompt'])
            image_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=800&height=400&nologo=true"
            refined_data['image_url'] = image_url
            embed.set_thumbnail(url=image_url)
            
        view = RefinedTopicView(self, refined_data)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="최종 제출", style=discord.ButtonStyle.success, emoji="✅", row=2)
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.options) < 2:
            await interaction.response.send_message("❌ 서버에 제출하려면 옵션을 최소 2개 이상 입력해야 합니다.", ephemeral=True)
            return

        # Disable all buttons
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(content="⏳ 대기열 서버 스토리지에 데이터를 쓰는 중...", embed=self.get_embed(), view=self)
        
        await database.suggest_topic(
            self.topic, 
            self.options, 
            self.allow_multiple, 
            self.allow_short, 
            self.user_id, 
            self.image_url
        )
        
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            content="🎉 **성공적으로 갈드컵 주제 의견을 제출했습니다!** 3일 뒤 로테이션 때 추첨 및 평가에 반영될 수 있습니다.",
            view=None
        )


class RefinedTopicView(discord.ui.View):
    def __init__(self, builder_view: SuggestionBuilderView, refined_data: dict):
        super().__init__(timeout=None)
        self.builder_view = builder_view
        self.refined_data = refined_data

    @discord.ui.button(label="승인 및 덮어쓰기", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.builder_view.topic = self.refined_data['topic']
        self.builder_view.options = self.refined_data['options']
        
        if 'image_url' in self.refined_data:
            self.builder_view.image_url = self.refined_data['image_url']
            
        await interaction.response.edit_message(content="✅ **가공된 내용으로 빌더가 업데이트되었습니다.** (본창을 확인해주세요)", embed=None, view=None)
        # Update the original builder message
        try:
            msg = await interaction.channel.fetch_message(interaction.message.reference.message_id) if interaction.message.reference else None
            # Fetching the interaction message might not easily give us the ephemeral reference, 
            # but we can edit standard logic if we had the message object. 
            # Actually, because it's ephemeral, standard edit_message works for the view itself if triggered there,
            # but from another ephemeral message, we might just ask them to click "Refresh" or just update it if they interact with the original builder.
            # To fix an issue where ephemeral views can't easily cross-reference edits without the Webhook, we'll just rely on the user seeing the original UI updating when they click any button on it, OR we just let this followup serve as a notification.
            # Wait, better yet, we can't edit the parent ephemeral message directly from this interaction without its ID. 
            pass
        except:
            pass
            
    @discord.ui.button(label="거절 (원본 유지)", style=discord.ButtonStyle.danger, emoji="✖️")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✖️ **AI 가공 제안을 거절했습니다.** (빌더의 내용은 그대로 유지됩니다)", embed=None, view=None)

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
        
        if existing_vote:
            # send_modal 이후에는 followup으로 메세지를 전송합니다 (ephemeral 속성)
            await interaction.followup.send(
                "⚠️ **이미 현 갈드컵에 투표하셨습니다!** 방금 띄워드린 팝업창을 통해 새로운 의견을 제출하시면 기존 투표 내역이 수정 반영됩니다.",
                ephemeral=True
            )


class Survey(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="주제제시", description="재미있는 갈드컵 다음 주제를 제시합니다.")
    async def suggest_topic(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SuggestTopicTitleModal(self.bot.get_cog('Master')))

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
