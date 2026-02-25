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
    def __init__(self, topic: str, master_cog, user_id: int, edit_target_id: int = None, existing_options=None, allow_short=False, image_url=None):
        super().__init__(timeout=900) # 15분 타임아웃
        self.topic = topic
        self.master_cog = master_cog
        self.user_id = user_id
        self.edit_target_id = edit_target_id
        
        self.options = existing_options if existing_options else []
        self.allow_short = allow_short
        self.image_url = image_url

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
            
        await interaction.response.edit_message(content="⏳ 데이터베이스에 쓰는 중...", embed=self.get_embed(), view=self)
        
        if self.edit_target_id:
            await database.update_suggested_topic(
                self.edit_target_id,
                self.topic,
                self.options,
                self.allow_short,
                self.image_url
            )
            await interaction.edit_original_response(
                content="✅ **기존 주제가 성공적으로 수정 및 저장되었습니다!**\n(심사 메뉴에서 [새로고침]을 눌러 반영된 데이터를 확인하세요.)",
                embed=None,
                view=None
            )
        else:
            await database.suggest_topic(
                self.topic, 
                self.options, 
                self.allow_short, 
                self.user_id,
                self.image_url
            )
            await interaction.edit_original_response(
                content="✅ **성공적으로 제안이 서버로 전송되었습니다!**\n(관리자 심사를 거쳐 채택 시 실제 투표에 올라갑니다.)", 
                embed=None, 
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


class VoteOptionButton(discord.ui.Button):
    def __init__(self, label: str, value: str, is_short: bool, survey_id: int, index: int):
        style = discord.ButtonStyle.secondary if is_short else discord.ButtonStyle.primary
        super().__init__(style=style, label=label[:80], custom_id=f"vote_btn_{survey_id}_{index}")
        self.value_choice = value
        self.is_short = is_short
        self.survey_id = survey_id

    async def callback(self, interaction: discord.Interaction):
        existing_vote = await database.get_user_vote(self.survey_id, interaction.user.id)
        
        if self.is_short:
            await interaction.response.send_modal(VoteShortAnswerModal(self.survey_id, []))
        else:
            await interaction.response.send_modal(VoteOpinionModal(self.survey_id, self.value_choice))
            
        if existing_vote:
            await interaction.followup.send(
                "⚠️ **이미 현 갈드컵에 투표하셨습니다!** 방금 띄워드린 팝업창을 통해 새로운 의견을 제출하시면 기존 투표 내역이 수정 반영됩니다.",
                ephemeral=True
            )

class ViewStatsButton(discord.ui.Button):
    def __init__(self, survey_id: int):
        super().__init__(style=discord.ButtonStyle.success, label="👀 다른 의견 보기", custom_id=f"view_stats_{survey_id}")
        self.survey_id = survey_id

    async def callback(self, interaction: discord.Interaction):
        survey_cog = interaction.client.get_cog("Survey")
        if survey_cog:
            await survey_cog.current_status.callback(survey_cog, interaction)
        else:
            await interaction.response.send_message("❌ 시스템 오류: 통계를 불러올 수 없습니다.", ephemeral=True)

class VoteSelectView(discord.ui.View):
    def __init__(self, survey_id: int, options: list, allow_short: bool):
        super().__init__(timeout=None)
        self.survey_id = survey_id
        
        # Add dynamic buttons for options (Limit to 24 to save 1 slot for stats button)
        for idx, opt in enumerate(options[:24]):
            if isinstance(opt, dict):
                label = opt.get('name', '옵션')[:80]
            else:
                label = str(opt)[:80]
                
            self.add_item(VoteOptionButton(label, label, False, survey_id, idx))
            
        if allow_short:
            self.add_item(VoteOptionButton("기타 (직접입력)", "##SHORT_ANSWER##", True, survey_id, 99))
            
        self.add_item(ViewStatsButton(survey_id))


class OpinionPaginationView(discord.ui.View):
    def __init__(self, topic_name: str, opinions: list):
        super().__init__(timeout=600)
        self.topic_name = topic_name
        self.opinions = opinions
        self.current_page = 0
        self.per_page = 5
        self.max_pages = max(1, (len(opinions) + self.per_page - 1) // self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = (self.current_page == 0)
        self.next_btn.disabled = (self.current_page >= self.max_pages - 1)

    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"💬 의견 모아보기: {self.topic_name}",
            color=discord.Color.light_embed()
        )
        
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_ops = self.opinions[start_idx:end_idx]
        
        if not page_ops:
            embed.description = "아직 작성된 의견이 없습니다."
        else:
            opinions_text = "\n\n".join([f"- {opt}" for opt in page_ops])
            page_text = f" (페이지 {self.current_page + 1}/{self.max_pages})" if self.max_pages > 1 else ""
            embed.description = f"**👀 익명 유저들의 반응{page_text}**\n\n{opinions_text[:3500]}"
            
        embed.set_footer(text=f"총 {len(self.opinions)}개의 의견이 등록됨 | 좌우 화살표를 눌러 넘겨보세요")
        return embed

    @discord.ui.button(label="이전", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="다음", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

class Survey(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # 봇 재시작 후에도 버튼들이 정상 작동하도록, 현재 진행 중인 옵션의 Persistent View를 등록
        survey_dict = await database.get_active_survey()
        if survey_dict:
            import json
            options = survey_dict['options']
            if isinstance(options, str):
                options = json.loads(options)
            view = VoteSelectView(
                survey_dict['id'], 
                options, 
                bool(survey_dict.get('allow_short_answer', False))
            )
            self.bot.add_view(view)

    @app_commands.command(name="주제제시", description="재미있는 갈드컵 다음 주제를 제시합니다.")
    async def suggest_topic(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SuggestTopicTitleModal(self.bot.get_cog('Master')))

    @app_commands.command(name="투표", description="현재 진행 중인 갈드컵에 익명으로 투표와 의견을 남깁니다.")
    async def vote(self, interaction: discord.Interaction):
        survey = await database.get_active_survey()
        if not survey:
            await interaction.response.send_message("❌ 현재 진행 중인 갈드컵 주제가 없습니다.", ephemeral=True)
            return

        view = VoteSelectView(survey['id'], survey['options'], survey['allow_short_answer'])
        
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
        
        try:
            from datetime import datetime, timezone, timedelta
            start_time = datetime.strptime(survey['start_time'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            end_time = int((start_time + timedelta(hours=72)).timestamp())
            embed.description += f"\n⏳ **투표 마감 예정:** <t:{end_time}:R>"
        except Exception:
            pass
        
        # 옵션별 통계 표시 (다중선택의 경우 각각을 카운트)
        option_names = [opt.get('name', str(opt)) if isinstance(opt, dict) else str(opt) for opt in survey['options']]
        option_counts = {name: 0 for name in option_names}
        for v in votes:
            c = v['selected_option'].strip()
            if c in option_counts:
                option_counts[c] += 1
            else:
                option_counts[c] = 1 # unexpected option fallback

        # 통계 렌더링
        stat_text = "\n".join([f"**{opt}**: {cnt}표" for opt, cnt in sorted(option_counts.items(), key=lambda item: item[1], reverse=True)])
        embed.add_field(name="투표 분포", value=stat_text if stat_text else "아직 투표가 없습니다.", inline=False)
        
        # 의견 나열 (pagenation 적용)
        all_opinions = [f"[{v['selected_option']}] \"{v['opinion']}\"" for v in votes if v['opinion']]
        
        # 먼저 통계 엠베드를 전송
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # 의견이 있으면 별도의 메세지로 페이지네이션 뷰를 전송 (followup)
        if all_opinions:
            view = OpinionPaginationView(survey['topic'], all_opinions)
            await interaction.followup.send(embed=view.get_embed(), view=view, ephemeral=True)

    @app_commands.command(name="통계", description="과거에 종료된 모든 갈드컵 주제 목록과 결과를 열람합니다.")
    async def statistics(self, interaction: discord.Interaction):
        past_surveys = await database.get_past_surveys(100) # Get up to 100 recent
        if not past_surveys:
            await interaction.response.send_message("❌ 아직 종료된 갈드컵이 없습니다.", ephemeral=True)
            return

        view = SurveyHistoryPaginationView(past_surveys)
        await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

    @app_commands.command(name="조회", description="특정 갈드컵 ID를 입력하여 과거 결과를 상세 조회합니다.")
    @app_commands.describe(survey_id="조회할 갈드컵의 고유 ID 번호")
    async def lookup_survey(self, interaction: discord.Interaction, survey_id: int):
        await send_archived_survey_result(interaction, survey_id)

import os
import json
import io
import aiosqlite

async def send_archived_survey_result(interaction: discord.Interaction, survey_id: int):
    # Retrieve past survey basic metadata from DB to check existence
    async with aiosqlite.connect(database.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)) as cursor:
            survey_row = await cursor.fetchone()
            
    if not survey_row:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ ID {survey_id}인 설문을 찾을 수 없습니다.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ ID {survey_id}인 설문을 찾을 수 없습니다.", ephemeral=True)
        return

    survey_data = dict(survey_row)
    topic = survey_data['topic']

    json_path = os.path.join("data", "charts", f"survey_{survey_id}.json")
    png_path = os.path.join("data", "charts", f"survey_{survey_id}.png")

    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            archived = json.load(f)
        
        stats_str = archived.get('stats_str', "데이터 없음")
        clustered_data = archived.get('clustered_data', [])
        
        embed = discord.Embed(
            title=f"📜 과거 갈드컵 조회 [{survey_id}회차]: {topic}",
            description=stats_str,
            color=discord.Color.teal()
        )
        
        if clustered_data:
            cluster_text = ""
            valid_clusters = [c for c in clustered_data if c.get('count', 0) > 0]
            for idx, c in enumerate(valid_clusters):
                quote = c.get('quote', '')
                quote_str = f'\n> 💬 "{quote}"' if quote else ''
                cluster_text += f"**{idx+1}. {c.get('name', '그룹')}** ({c.get('count', 0)}명)\n*{c.get('summary', '')}*{quote_str}\n\n"
            if cluster_text:
                embed.add_field(name="🤖 AI 여론 분석 (당시 기록)", value=cluster_text[:1024], inline=False)
    else:
        # Fallback for old surveys before JSON archiving was added
        votes = await database.get_votes_for_survey(survey_id)
        total_votes = len(votes)
        raw_options = json.loads(survey_data['options'])
        option_names = [opt.get('name', str(opt)) if isinstance(opt, dict) else str(opt) for opt in raw_options]
        counts = {name: 0 for name in option_names}
        for v in votes:
            c = v['selected_option'].strip()
            if c in counts: counts[c] += 1
            else: counts[c] = 1
                
        stats_str = f"총 참여인원: {total_votes}명\n"
        for opt, cnt in sorted(counts.items(), key=lambda item: item[1], reverse=True):
            ratio = (cnt / total_votes * 100) if total_votes > 0 else 0
            stats_str += f"- **{opt}**: {ratio:.1f}% ({cnt}표)\n"
            
        embed = discord.Embed(
            title=f"📜 과거 갈드컵 조회 [{survey_id}회차]: {topic}",
            description=stats_str + "\n\n*(이 데이터는 구버전 기록으로 AI 텍스트 및 전용 차트가 없을 수 있습니다.)*",
            color=discord.Color.teal()
        )

    file = None
    if os.path.exists(png_path):
        file = discord.File(png_path, filename="chart.png")
        embed.set_image(url="attachment://chart.png")
        
    if not interaction.response.is_done():
        if file:
            await interaction.response.send_message(embed=embed, file=file, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        if file:
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

class SurveyHistoryPaginationView(discord.ui.View):
    def __init__(self, past_surveys: list):
        super().__init__(timeout=600)
        self.surveys = past_surveys
        self.current_page = 0
        self.per_page = 5
        self.max_pages = max(1, (len(past_surveys) + self.per_page - 1) // self.per_page)
        self.update_components()

    def update_components(self):
        self.clear_items()
        
        # Add Select Menu for the current page items
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_surveys = self.surveys[start_idx:end_idx]
        
        if page_surveys:
            options = []
            for s in page_surveys:
                topic = s['topic']
                title = topic[:90] + "..." if len(topic) > 90 else topic
                options.append(discord.SelectOption(
                    label=f"ID: {s['id']}회차",
                    description=title,
                    value=str(s['id']),
                    emoji="📊"
                ))
                
            select = discord.ui.Select(
                placeholder="상세 결과를 조회할 주제를 선택하세요...",
                min_values=1, max_values=1,
                options=options
            )
            
            async def select_callback(interaction: discord.Interaction):
                selected_id = int(select.values[0])
                await send_archived_survey_result(interaction, selected_id)
                
            select.callback = select_callback
            self.add_item(select)
            
        # Add Pagination Buttons
        prev_btn = discord.ui.Button(label="⬅️ 이전", style=discord.ButtonStyle.secondary, disabled=(self.current_page == 0))
        next_btn = discord.ui.Button(label="➡️ 다음", style=discord.ButtonStyle.secondary, disabled=(self.current_page == self.max_pages - 1))
        
        async def prev_callback(interaction: discord.Interaction):
            self.current_page -= 1
            self.update_components()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
            
        async def next_callback(interaction: discord.Interaction):
            self.current_page += 1
            self.update_components()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
            
        prev_btn.callback = prev_callback
        next_btn.callback = next_callback
        
        self.add_item(prev_btn)
        self.add_item(next_btn)

    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📚 과거 갈드컵 통계 기록 (페이지네이션)",
            color=discord.Color.purple()
        )
        
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_surveys = self.surveys[start_idx:end_idx]
        
        desc = f"총 {len(self.surveys)}개의 종료된 갈드컵 기록이 있습니다.\n아래 드롭다운 메뉴를 클릭하여 상세 결과(이미지 및 분석)를 조회해 보세요!\n\n"
        for s in page_surveys:
            time_str = s['end_time'][:10] if s['end_time'] else "알 수 없음"
            desc += f"**[ID: {s['id']}]** {s['topic']} ({time_str})\n"
            
        embed.description = desc
        embed.set_footer(text=f"페이지 {self.current_page + 1} / {self.max_pages}")
        return embed

async def setup(bot: commands.Bot):
    await bot.add_cog(Survey(bot))
