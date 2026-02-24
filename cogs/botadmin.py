import discord
from discord.ext import commands
from discord import app_commands
import logging
import database
import os
import json
import shlex
import asyncio

logger = logging.getLogger('discord')

async def check_and_trigger_empty_survey(bot: commands.Bot):
    """대기열에 새로 주제가 들어왔을 때, 현재 진행 중인 투표가 없으면 즉시 시작시킵니다."""
    active_survey = await database.get_active_survey()
    if not active_survey:
        master_cog = bot.get_cog('Master')
        if master_cog:
            await master_cog.process_survey_rotation()

MASTER_ADMIN_ID = int(os.getenv("MASTER_ADMIN_ID", "0"))

class DirectTopicModal(discord.ui.Modal, title='갈드컵 강제 새 주제 지정'):
    topic = discord.ui.TextInput(
        label='1. 갈드컵 주제',
        style=discord.TextStyle.short,
        placeholder='예: 평생 탕수육 소스는?',
        required=True,
        max_length=100
    )
    
    options = discord.ui.TextInput(
        label='2. 선택 옵션 (쉼표로 구분. 띄어쓰기는 " " 사용)',
        style=discord.TextStyle.short,
        placeholder='예: 부먹, 찍먹, "매운 소스"',
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
        max_length=4000
    )

    def __init__(self, master_cog):
        super().__init__()
        self.master_cog = master_cog

    async def on_submit(self, interaction: discord.Interaction):
        topic_text = self.topic.value
        
        # Use shlex to parse the options string, respecting double quotes but allowing commas
        raw_options = self.options.value
        # Temporarily replace commas with spaces outside of quotes to let shlex split it, 
        # or simply parse commas properly using csv.
        # The user requested to use "" for spaces, which means they might just type:
        # "Option 1" "Option 2" OR Option1, "Option 2"
        # We will split by commas first, then strip quotes if they used them to encapsulate.
        
        options_list = []
        for opt in raw_options.split(','):
            opt = opt.strip()
            if opt.startswith('"') and opt.endswith('"'):
                opt = opt[1:-1]
            if opt:
                options_list.append(opt)
        
        if len(options_list) < 2:
            await interaction.response.send_message("옵션은 최소 2개 이상 입력해야 합니다.", ephemeral=True)
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

        new_topic_data = {
            "topic": topic_text,
            "options": parsed_options,
            "allow_multiple": is_multiple,
            "allow_short_answer": is_short,
            "image_url": img_val
        }

        # 마스터 Cog의 주제 강제전환 함수 호출
        await self.master_cog.force_new_topic(new_topic_data, interaction.user)
        await interaction.response.send_message("✅ 직접 작성한 주제로 긴급 교체되었습니다!", ephemeral=True)


class AIGeneratedTopicView(discord.ui.View):
    def __init__(self, master_cog, generated_data: dict, invoker: discord.User):
        super().__init__(timeout=None)
        self.master_cog = master_cog
        self.generated_data = generated_data
        self.invoker = invoker

    @discord.ui.button(label="대기열 가록 (Queue) 추가", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        import database
        await database.add_to_queue({
            'topic': self.generated_data['topic'],
            'options': self.generated_data['options'],
            'allow_multiple': self.generated_data.get('allow_multiple', False),
            'allow_short_answer': self.generated_data.get('allow_short_answer', False),
            'suggested_by': interaction.user.id,
            'image_url': self.generated_data.get('image_url')
        })
        await check_and_trigger_empty_survey(interaction.client)
        
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="✅ **AI 제안 주제가 대기열 리스트 끝에 신규로 장전되었습니다!**", view=self)

    @discord.ui.button(label="거절", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ 생성된 주제가 거절되었습니다.", view=self)



class TopicPaginationView(discord.ui.View):
    def __init__(self, topics: list, master_cog, active_topic_sessions: dict, user_id: int):
        super().__init__(timeout=None)
        self.topics = topics
        self.master_cog = master_cog
        self.active_topic_sessions = active_topic_sessions
        self.user_id = user_id
        self.current_page = 0
        self.max_pages = len(topics)
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page == self.max_pages - 1
        
        # 주제가 없을 때
        if self.max_pages == 0:
            self.prev_btn.disabled = True
            self.next_btn.disabled = True
            self.queue_add_btn.disabled = True
            self.force_pick_btn.disabled = True
            self.edit_btn.disabled = True
            self.delete_btn.disabled = True
            self.ai_pick_btn.disabled = True
            self.ai_gen_btn.disabled = True
        else:
            self.queue_add_btn.disabled = False
            self.force_pick_btn.disabled = False
            self.edit_btn.disabled = False
            self.delete_btn.disabled = False
            self.ai_pick_btn.disabled = False
            self.ai_gen_btn.disabled = False

    def get_current_embed(self) -> discord.Embed:
        if not self.topics:
            return discord.Embed(title="대기열 비어있음", description="아직 제안된/대기 중인 주제가 없습니다.", color=discord.Color.red())
            
        topic = self.topics[self.current_page]
        embed = discord.Embed(
            title=f"대기열 주제 [{self.current_page + 1}/{self.max_pages}] (ID: {topic['id']})",
            description=f"**{topic['topic']}**",
            color=discord.Color.blue()
        )
        
        desc = ""
        for idx, opt in enumerate(topic['options']):
            if isinstance(opt, dict):
                desc += f"**{idx+1}. {opt.get('name', '옵션')}**\n- {opt.get('desc', '')}\n\n"
            else:
                desc += f"**{idx+1}. {opt}**\n"
                
        embed.add_field(name="옵션", value=desc.strip(), inline=False)
        embed.add_field(name="중복허용", value="O" if topic['allow_multiple'] else "X", inline=True)
        embed.add_field(name="단답허용", value="O" if topic['allow_short_answer'] else "X", inline=True)
        
        if topic.get('image_url'):
            import urllib.parse
            parsed = urllib.parse.urlparse(topic['image_url'])
            is_image = parsed.path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')) or 'pollinations.ai' in topic['image_url']
            
            if is_image:
                embed.set_thumbnail(url=topic['image_url'])
            else:
                embed.add_field(name="🔗 참고 링크", value=topic['image_url'], inline=False)
            
        embed.add_field(name="제안자", value=f"<@{topic['suggested_by']}>", inline=False)
        return embed

    @discord.ui.button(label="이전", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="다음", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)
        
    @discord.ui.button(label="추가하기", style=discord.ButtonStyle.success, emoji="✅")
    async def queue_add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        topic = self.topics[self.current_page]
        await database.delete_suggested_topic(topic['id'])
        await database.add_to_queue(topic)
        await check_and_trigger_empty_survey(interaction.client)
        
        # UI에서 삭제 처리
        self.topics.pop(self.current_page)
        self.max_pages = len(self.topics)
        if self.current_page >= self.max_pages and self.current_page > 0:
            self.current_page -= 1
        self.update_buttons()
        
        await interaction.response.edit_message(
            content=f"✅ **[{topic['topic']}]** 주제가 다음 송출을 위해 대기열 큐(Queue)에 배치되었습니다!", 
            embed=self.get_current_embed(), 
            view=self
        )
        
    @discord.ui.button(label="즉시 강제시작", style=discord.ButtonStyle.danger, emoji="⚠️", row=1)
    async def force_pick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        topic = self.topics[self.current_page]
        await database.delete_suggested_topic(topic['id'])
        master_cog = interaction.client.get_cog('Master')
        if master_cog:
            await master_cog.force_new_topic(topic, interaction.user)
        else:
            await interaction.response.send_message("❌ Master 모듈을 찾을 수 없습니다. 봇을 재구동하거나 모듈을 리로드하세요.", ephemeral=True)
            return
        
        # UI에서 삭제 처리
        self.topics.pop(self.current_page)
        self.max_pages = len(self.topics)
        if self.current_page >= self.max_pages and self.current_page > 0:
            self.current_page -= 1
        self.update_buttons()
        
        await interaction.response.edit_message(
            content=f"🚨 **[{topic['topic']}]** 주제가 즉시 채택되어 전체 서버 방출되었습니다!", 
            embed=self.get_current_embed(), 
            view=self
        )
        
    @discord.ui.button(label="이 주제 수정하기", style=discord.ButtonStyle.primary, emoji="🛠️", row=1)
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        topic = self.topics[self.current_page]
        from cogs.survey import SuggestionBuilderView
        view = SuggestionBuilderView(
            topic=topic['topic'],
            master_cog=self.master_cog,
            user_id=topic['suggested_by'],
            edit_target_id=topic['id'],
            existing_options=topic['options'],
            allow_multiple=topic['allow_multiple'],
            allow_short=topic['allow_short_answer'],
            image_url=topic.get('image_url')
        )
        embed = view.get_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="이 주제 거절(삭제)", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        topic_id = self.topics[self.current_page]['id']
        await database.delete_suggested_topic(topic_id)

        
        self.topics.pop(self.current_page)
        self.max_pages = len(self.topics)
        if self.current_page >= self.max_pages and self.current_page > 0:
            self.current_page -= 1
            
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="AI로 가공 후 추가", style=discord.ButtonStyle.primary, emoji="🤖")
    async def ai_pick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        topic = self.topics[self.current_page]
        
        is_valid = await self.master_cog.evaluate_topic(topic['topic'], topic['options'])
        if is_valid:
            # AI 승인되었다고 간주, 추가 텍스트(image_prompt 등) 부여를 위해 생성 요청
            # 하지만 단순 승인일 경우 evaluate_topic은 True만 리턴하므로,
            # 여기서는 제안자의 구성을 유지하면서 이미지만 생성해본다고 가정
            image_url = topic.get('image_url')

            await database.delete_suggested_topic(topic['id'])
            await database.add_to_queue({
                'topic': topic['topic'],
                'options': topic['options'],
                'allow_multiple': topic['allow_multiple'],
                'allow_short_answer': topic['allow_short_answer'],
                'suggested_by': topic['suggested_by'],
                'image_url': image_url
            })
            await check_and_trigger_empty_survey(interaction.client)
            
            self.topics.pop(self.current_page)
            self.max_pages = len(self.topics)
            if self.current_page >= self.max_pages and self.current_page > 0:
                self.current_page -= 1
            self.update_buttons()

            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                content="✅ AI가 주제 구성을 가공 및 승인하여 큐(Queue)에 배치했습니다.", 
                embed=self.get_current_embed(), 
                view=self
            )
        else:
            await interaction.followup.send("❌ AI가 이 주제를 부적절하다고 평가(REJECT)했습니다.", ephemeral=True)

    @discord.ui.button(label="인공지능 자체생성", style=discord.ButtonStyle.primary, emoji="✨")
    async def ai_gen_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        generated_data = await self.master_cog.generate_topic()
        
        if generated_data:
            # options format handling (either list of strings or list of dicts)
            desc = ""
            for idx, opt in enumerate(generated_data['options']):
                if isinstance(opt, dict):
                    desc += f"**{idx+1}. {opt.get('name', '옵션')}**\n- {opt.get('desc', '')}\n\n"
                else:
                    desc += f"**{idx+1}. {opt}**\n"
                    
            embed = discord.Embed(
                title="✨ AI 생성 주제 결과",
                description=f"**{generated_data['topic']}**",
                color=discord.Color.purple()
            )
            embed.add_field(name="새로운 선택지 구조", value=desc.strip(), inline=False)
            
            view = AIGeneratedTopicView(self.master_cog, generated_data, interaction.user)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send("❌ AI 주제 생성에 실패했습니다.", ephemeral=True)

    @discord.ui.button(label="🔄 새로고침", style=discord.ButtonStyle.secondary, row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        import database
        self.topics = await database.get_all_suggested_topics()
        self.max_pages = len(self.topics)
        if self.current_page >= self.max_pages and self.current_page > 0:
            self.current_page = self.max_pages - 1
        elif self.max_pages == 0:
            self.current_page = 0
            
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    async def on_timeout(self):
        if self.user_id in self.active_topic_sessions:
            del self.active_topic_sessions[self.user_id]


class QueuePaginationView(discord.ui.View):
    def __init__(self, topics: list, master_cog, active_queue_sessions: dict, user_id: int):
        super().__init__(timeout=None)
        self.topics = topics
        self.master_cog = master_cog
        self.active_queue_sessions = active_queue_sessions
        self.user_id = user_id
        self.current_page = 0
        self.max_pages = len(topics)
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page == self.max_pages - 1
        
        if self.max_pages == 0:
            self.prev_btn.disabled = True
            self.next_btn.disabled = True
            self.force_pick_btn.disabled = True
            self.delete_btn.disabled = True
            self.move_up_btn.disabled = True
            self.move_down_btn.disabled = True
            self.return_btn.disabled = True
        else:
            self.force_pick_btn.disabled = False
            self.delete_btn.disabled = False
            self.return_btn.disabled = False
            self.move_up_btn.disabled = (self.current_page == 0)
            self.move_down_btn.disabled = (self.current_page == self.max_pages - 1)

    def get_current_embed(self) -> discord.Embed:
        if not self.topics:
            return discord.Embed(title="진행 대기열(Queue) 비어있음", description="아직 큐에 예약된 주제가 없습니다.", color=discord.Color.red())
            
        topic = self.topics[self.current_page]
        embed = discord.Embed(
            title=f"진행 대기열(Queue) 주제 [{self.current_page + 1}/{self.max_pages}] (ID: {topic['id']})",
            description=f"**{topic['topic']}**",
            color=discord.Color.green()
        )
        
        desc = ""
        for idx, opt in enumerate(topic['options']):
            if isinstance(opt, dict):
                desc += f"**{idx+1}. {opt.get('name', '옵션')}**\n- {opt.get('desc', '')}\n\n"
            else:
                desc += f"**{idx+1}. {opt}**\n"
                
        embed.add_field(name="옵션", value=desc.strip(), inline=False)
        embed.add_field(name="중복허용", value="O" if topic['allow_multiple'] else "X", inline=True)
        embed.add_field(name="단답허용", value="O" if topic['allow_short_answer'] else "X", inline=True)
        
        if topic.get('image_url'):
            import urllib.parse
            parsed = urllib.parse.urlparse(topic['image_url'])
            is_image = parsed.path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')) or 'pollinations.ai' in topic['image_url']
            
            if is_image:
                embed.set_thumbnail(url=topic['image_url'])
            else:
                embed.add_field(name="🔗 참고 링크", value=topic['image_url'], inline=False)
            
        embed.add_field(name="제안자", value=f"<@{topic['suggested_by']}>", inline=False)
        return embed

    @discord.ui.button(label="이전", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="다음", style=discord.ButtonStyle.secondary, emoji="➡️", row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)
        
    @discord.ui.button(label="순서 위로", style=discord.ButtonStyle.secondary, emoji="🔼", row=0)
    async def move_up_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            import database
            id1 = self.topics[self.current_page]['id']
            id2 = self.topics[self.current_page - 1]['id']
            await database.swap_queue_items(id1, id2)
            
            # ID swap in UI list directly to mirror DB change
            temp = self.topics[self.current_page]['id']
            self.topics[self.current_page]['id'] = self.topics[self.current_page - 1]['id']
            self.topics[self.current_page - 1]['id'] = temp
            
            self.topics[self.current_page], self.topics[self.current_page - 1] = self.topics[self.current_page - 1], self.topics[self.current_page]
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="순서 아래로", style=discord.ButtonStyle.secondary, emoji="🔽", row=0)
    async def move_down_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_pages - 1:
            import database
            id1 = self.topics[self.current_page]['id']
            id2 = self.topics[self.current_page + 1]['id']
            await database.swap_queue_items(id1, id2)
            
            # ID swap in UI list directly to mirror DB change
            temp = self.topics[self.current_page]['id']
            self.topics[self.current_page]['id'] = self.topics[self.current_page + 1]['id']
            self.topics[self.current_page + 1]['id'] = temp
            
            self.topics[self.current_page], self.topics[self.current_page + 1] = self.topics[self.current_page + 1], self.topics[self.current_page]
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_current_embed(), view=self)
        
    # 대기열(Queue)에서는 수정하기 버튼을 사용하지 않습니다.

    @discord.ui.button(label="주제제시로 반환", style=discord.ButtonStyle.primary, emoji="🔙", row=1)
    async def return_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        topic = self.topics[self.current_page]
        import database
        await database.return_queue_to_suggested(topic['id'])
        
        self.topics.pop(self.current_page)
        self.max_pages = len(self.topics)
        if self.current_page >= self.max_pages and self.current_page > 0:
            self.current_page -= 1
            
        self.update_buttons()
        await interaction.response.edit_message(
            content=f"✅ **[{topic['topic']}]** 대기열 주제를 다시 유저 건의 목록(`!주제관리`)으로 되돌렸습니다.",
            embed=self.get_current_embed(), 
            view=self
        )

    @discord.ui.button(label="이 대기열 제거", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        topic = self.topics[self.current_page]
        import database
        await database.delete_queued_topic(topic['id'])
        
        self.topics.pop(self.current_page)
        self.max_pages = len(self.topics)
        if self.current_page >= self.max_pages and self.current_page > 0:
            self.current_page -= 1
            
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="즉시 강제시작", style=discord.ButtonStyle.danger, emoji="⚠️", row=2)
    async def force_pick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        topic = self.topics[self.current_page]
        import database
        await database.delete_queued_topic(topic['id'])
        master_cog = interaction.client.get_cog('Master')
        if master_cog:
            await master_cog.force_new_topic(topic, interaction.user)
        else:
            await interaction.response.send_message("❌ Master 모듈을 찾을 수 없습니다. 봇을 재구동하거나 모듈을 리로드하세요.", ephemeral=True)
            return
        
        self.topics.pop(self.current_page)
        self.max_pages = len(self.topics)
        if self.current_page >= self.max_pages and self.current_page > 0:
            self.current_page -= 1
        self.update_buttons()
        
        await interaction.response.edit_message(
            content=f"🚨 **[{topic['topic']}]** 대기열 주제가 즉시 채택되어 전체 서버 방출되었습니다!", 
            embed=self.get_current_embed(), 
            view=self
        )

    @discord.ui.button(label="🔄 새로고침", style=discord.ButtonStyle.secondary, row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        import database
        self.topics = await database.get_all_queued_topics()
        self.max_pages = len(self.topics)
        if self.current_page >= self.max_pages and self.current_page > 0:
            self.current_page = self.max_pages - 1
        elif self.max_pages == 0:
            self.current_page = 0
            
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    async def on_timeout(self):
        if self.user_id in self.active_queue_sessions:
            del self.active_queue_sessions[self.user_id]

class BotAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_topic_sessions = {}
        self.active_queue_sessions = {}
        
    async def check_is_master(self, ctx: commands.Context) -> bool:
        if ctx.author.id != MASTER_ADMIN_ID:
            await ctx.send("❌ 이 명령어는 총관리자(MASTER) 전용입니다.")
            return False
        return True

    async def check_is_bot_admin(self, ctx: commands.Context) -> bool:
        is_admin = await database.is_bot_admin(ctx.author.id, MASTER_ADMIN_ID)
        if not is_admin:
            await ctx.send("❌ 이 명령어는 봇 관리자(총관리자/부관리자) 전용입니다.")
            return False
        return True

    @commands.command(name="부관리자추가", description="[총관리자 전용] 부관리자를 임명합니다.")
    async def add_subadmin(self, ctx: commands.Context, member: discord.Member):
        if not await self.check_is_master(ctx):
            return
        await database.add_bot_admin(member.id)
        await ctx.send(f"✅ {member.mention} 님이 봇 부관리자로 임명되었습니다.")
        
        try:
            await member.send(
                f"🎉 축하합니다! {ctx.author.name} 님에 의해 레전드 갈드컵 봇의 부관리자로 임명되었습니다!\n"
                f"채팅창에 `!주제관리` 및 `!주제강제종료` 명령어를 입력해 갈드컵 주제와 흐름을 쥐락펴락할 수 있습니다."
            )
        except discord.Forbidden:
            pass

    @commands.command(name="부관리자제거", description="[총관리자 전용] 부관리자를 해임합니다.")
    async def remove_subadmin(self, ctx: commands.Context, member: discord.Member):
        if not await self.check_is_master(ctx):
            return
        await database.remove_bot_admin(member.id)
        await ctx.send(f"✅ {member.mention} 님의 봇 부관리자 권한이 박탈되었습니다.")

    @commands.command(name="관리자목록", description="[관리자 전용] 등록된 총관리자와 부관리자 목록을 확인합니다.")
    async def admin_list(self, ctx: commands.Context):
        if not await self.check_is_bot_admin(ctx):
            return
            
        bot_admins = await database.get_all_bot_admins()
        
        embed = discord.Embed(
            title="🛡️ 레전드 갈드컵 관리자 목록",
            color=discord.Color.blue()
        )
        embed.add_field(name="👑 총관리자 (Master)", value=f"<@{MASTER_ADMIN_ID}>", inline=False)
        
        if bot_admins:
            sub_admins = "\n".join([f"- <@{admin_id}>" for admin_id in bot_admins])
            embed.add_field(name="👥 부관리자 (Sub Admins)", value=sub_admins, inline=False)
        else:
            embed.add_field(name="👥 부관리자 (Sub Admins)", value="등록된 부관리자가 없습니다.", inline=False)
            
        await ctx.send(embed=embed)

    @commands.command(name="AI주제충전", description="[관리자 전용] 대기열에 AI가 생성한 주제를 지정한 개수(1~5개)만큼 채워넣습니다.")
    async def charge_ai_topics(self, ctx: commands.Context, count: int = 1):
        if not await self.check_is_bot_admin(ctx):
            return
            
        if count < 1 or count > 5:
            await ctx.send("❌ 한 번에 1개에서 5개까지만 충전할 수 있습니다.")
            return
            
        await ctx.send(f"⏳ 인공지능이 새로운 주제 {count}개를 구상하고 있습니다. 잠시만 기다려주세요...")
        
        master_cog = self.bot.get_cog('Master')
        success_count = 0
        for _ in range(count):
            generated_data = await master_cog.generate_topic()
            if generated_data:
                import urllib.parse
                image_url = None
                if 'image_prompt' in generated_data:
                    prompt_encoded = urllib.parse.quote(generated_data['image_prompt'])
                    image_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=800&height=400&nologo=true"
                
                await database.add_to_queue({
                    'topic': generated_data['topic'],
                    'options': generated_data['options'],
                    'allow_multiple': generated_data.get('allow_multiple', False),
                    'allow_short_answer': generated_data.get('allow_short_answer', False),
                    'suggested_by': MASTER_ADMIN_ID,
                    'image_url': image_url
                })
                success_count += 1
                
        await check_and_trigger_empty_survey(self.bot) # Added call here
        await ctx.send(f"✅ 대기열 큐(Queue)에 **{success_count}개**의 AI 주제 충전이 완료되었습니다! (`!주제관리` 인터페이스로 확인 및 수정 가능)")

    @commands.command(name="관리자가이드", aliases=["관리자설명서"], description="[관리자 전용] 레전드 갈드컵 봇의 관리 시스템 및 흐름을 안내합니다.")
    async def admin_guide(self, ctx: commands.Context):
        if not await self.check_is_bot_admin(ctx):
            return
            
        import os
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        
        embed = discord.Embed(
            title="📖 레전드 갈드컵 봇 관리 요약",
            description="3일마다 새로운 딜레마(주제)를 자동 송출하며, 유저의 익명 투표를 집계함.\n관리 흐름은 아래 3단계 명일관리가 핵심임.",
            color=discord.Color.teal()
        )
        
        embed.add_field(
            name="1. 📥 아이디어 건의 목록 (`!주제관리`)",
            value=(
                "- 일반 유저들이 `/주제제시` 로 건의한 아이디어 임시 보관소\n"
                "- 내용을 심사/수정 후 마음에 들면 **[대기열 추가]** 클릭 시 방송 큐로 넘어감\n"
                "- **[AI로 가공 후 추가]** 시 AI가 찰지게 다듬어서 큐로 넘겨줌"
            ),
            inline=False
        )
        
        embed.add_field(
            name="2. ⏱️ 실제 방송 대기열 (`!대기열관리`)",
            value=(
                "- 다음 차례에 전체 서버로 런칭될 '확정된' **찐 대기열(Queue)**임\n"
                "- 3일 타이머 종료 시 (또는 큐가 비어서 즉각 발동 시) 여기서 가장 1번 타자가 송출됨\n"
                "- 큐 순서를 모니터링/수정/삭제 가능\n"
                "- **[즉시 강제시작]** 누르면 타이머 무시하고 해당 주제를 즉시 런칭시킴"
            ),
            inline=False
        )
        
        embed.add_field(
            name="3. 🤖 AI 자동 생산 (`!AI주제충전 <개수>`)",
            value=(
                "- 유저 제안이 말랐을 때 쓰는 치트키 명령어\n"
                "- AI가 즉석에서 생성한 주제와 이미지를 큐에 다이렉트로 장전해줌\n"
                f"- 탑재 AI: `{model_name}`\n"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚠️ 주의사항",
            value=(
                "• 관리 UI는 DM으로 전송됨\n"
                "• `!주제관리` 및 `!대기열관리` 독립 조작 가능하나 중복 창 띄우기는 제한됨\n"
                "• 큐가 아예 비어있으면 봇이 알아서 AI 주제를 쏘거나 기본 주제를 발동시킴"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.command(name="업데이트", description="[총관리자 전용] Github 저장소에서 최신 코드를 즉시 불러오고 봇을 리로드합니다.")
    async def update_bot(self, ctx: commands.Context):
        if str(ctx.author.id) != str(MASTER_ADMIN_ID):
            await ctx.send("❌ 이 명령어는 `.env`에 설정된 총관리자 전용입니다.")
            return
            
        await ctx.send("⏳ Github에서 최신 코드를 가져오는 중입니다...")
        
        import subprocess
        try:
            # 1. git fetch --all
            await asyncio.to_thread(
                subprocess.run,
                ['git', 'fetch', '--all'],
                capture_output=True,
                text=True,
                check=True
            )
            
            # 2. git reset --hard origin/main
            result = await asyncio.to_thread(
                subprocess.run,
                ['git', 'reset', '--hard', 'origin/main'],
                capture_output=True,
                text=True,
                check=True
            )
            
            output = result.stdout.strip()
            # Note: "HEAD is now at" is the typical output of git reset --hard
            if not output:
                await ctx.send("✅ 이미 최신 상태이거나 출력이 없습니다.")
                return
                
            await ctx.send(f"📦 업데이트 내역이 감지되었습니다:\n```\n{output[:1800]}\n```\n🔄 새 종속성 설치 및 완전한 패치 적용을 위해 봇 프로세스를 **강제 재기동**합니다. 잠시 후 다시 시작됩니다...")
            
            # Ensure all .sh files remain executable after git operations
            if os.name != 'nt':  # Only needed on Linux/macOS
                try:
                    subprocess.run(['chmod', '+x', 'start_bot.sh', 'stop_bot.sh', 'restart_bot.sh'], check=False)
                except Exception as chmod_err:
                    logger.warning(f"Failed to set executable permissions: {chmod_err}")

            # Use platform-independent way to restart if possible, or trigger the shell script
            import sys
            if os.path.exists('restart_bot.sh') and os.name != 'nt':
                # Linux/macOS environment
                subprocess.Popen(['bash', 'restart_bot.sh'], start_new_session=True)
            else:
                # Fallback to python restart
                subprocess.Popen([sys.executable, 'main.py'], start_new_session=True)
            
            # Kill current process gracefully
            await self.bot.close()
            os._exit(0)
            
        except subprocess.CalledProcessError as e:
            await ctx.send(f"🚨 Github에서 코드를 가져오는 중 오류가 발생했습니다.\n```\n{e.stderr[:1800]}\n```")
        except Exception as e:
            await ctx.send(f"🚨 기타 오류 발생: {e}")

    @commands.command(name="주제관리", description="[관리자 전용] DM으로 제안된 아이디어들을 열람하고 대기열로 넘깁니다.")
    async def manage_topics(self, ctx: commands.Context):
        if not await self.check_is_bot_admin(ctx):
            return
            
        # 중복 체크
        if ctx.author.id in self.active_topic_sessions:
            await ctx.send("❌ 이미 활성화된 주제 관리 창이 있습니다. 이전 인터페이스를 그대로 사용해주세요.")
            return
        
        # DM 전송 시도
        try:
            self.active_topic_sessions[ctx.author.id] = True
            topics = await database.get_all_suggested_topics()
            master_cog = self.bot.get_cog('Master')
            
            view = TopicPaginationView(topics, master_cog, self.active_topic_sessions, ctx.author.id)
            embed = view.get_current_embed()
            
            await ctx.author.send(embed=embed, view=view)
            await ctx.send("✅ DM으로 아이디어 주제 관리 인터페이스를 전송했습니다.")
        except discord.Forbidden:
            if ctx.author.id in self.active_topic_sessions: del self.active_topic_sessions[ctx.author.id]
            await ctx.send("❌ DM 전송이 막혀있습니다. 개인 설정에서 서버 구성원의 다이렉트 메시지를 허용해주세요.")
        except Exception as e:
            if ctx.author.id in self.active_topic_sessions: del self.active_topic_sessions[ctx.author.id]
            logger.error(f"Error in manage_topics: {e}")
            await ctx.send("❌ 명령어 처리 중 오류가 발생했습니다.")

    @commands.command(name="대기열관리", description="[관리자 전용] DM으로 실제 송출 예정인 대기열(Queue) 안의 주제 현황을 관리합니다.")
    async def manage_queue(self, ctx: commands.Context):
        if not await self.check_is_bot_admin(ctx):
            return
            
        # 중복 체크
        if ctx.author.id in self.active_queue_sessions:
            await ctx.send("❌ 이미 활성화된 대기열 관리 창이 있습니다. 이전 인터페이스를 그대로 사용해주세요.")
            return
            
        try:
            self.active_queue_sessions[ctx.author.id] = True
            topics = await database.get_all_queued_topics()
            master_cog = self.bot.get_cog('Master')
            
            view = QueuePaginationView(topics, master_cog, self.active_queue_sessions, ctx.author.id)
            embed = view.get_current_embed()
            
            await ctx.author.send(embed=embed, view=view)
            await ctx.send("✅ DM으로 진행 대기열(Queue) 관리 인터페이스를 전송했습니다.")
        except discord.Forbidden:
            if ctx.author.id in self.active_queue_sessions: del self.active_queue_sessions[ctx.author.id]
            await ctx.send("❌ DM 전송이 막혀있습니다. 개인 설정에서 서버 구성원의 다이렉트 메시지를 허용해주세요.")
        except Exception as e:
            if ctx.author.id in self.active_queue_sessions: del self.active_queue_sessions[ctx.author.id]
            logger.error(f"Error in manage_queue: {e}")
            await ctx.send("❌ 명령어 처리 중 오류가 발생했습니다.")

    @commands.command(name="주제강제종료", description="[관리자 전용] 현재 진행 중인 갈드컵 투표를 즉시 마감하고 다음 주제로 넘어갑니다.")
    async def force_finish_survey(self, ctx: commands.Context):
        if not await self.check_is_bot_admin(ctx):
            return
            
        await ctx.send("⚙️ 현재 진행 중인 투표를 즉시 종료하고 결과를 집계하여 공지합니다...")
        master_cog = self.bot.get_cog('Master')
        
        # This will trigger the rotation, print stats, and fetch the next topic immediately
        await master_cog.process_survey_rotation()
        # Note: No need to restart survey_loop since it polls every minute

    @commands.command(name="차트테스트", description="[관리자 전용] 현재 진행 중인 주제의 예상 마감 결과(차트 및 AI 분석)를 미리 생성해 확인합니다.")
    async def chart_test(self, ctx: commands.Context):
        if not await self.check_is_bot_admin(ctx):
            return
            
        active_survey = await database.get_active_survey()
        if not active_survey:
            await ctx.send("❌ 현재 진행 중인 갈드컵 주제가 없어 테스트할 수 없습니다.")
            return

        survey_id = active_survey['id']
        votes = await database.get_votes_for_survey(survey_id)
        if not votes:
            await ctx.send("❌ 등록된 표가 없기 때문에 차트 및 여론 분석 테스트를 진행할 수 없습니다.")
            return

        await ctx.send("📊 현재까지의 투표 데이터를 바탕으로 차트와 AI 분류 텍스트를 생성 중입니다. (약 5~10초 소요)...")
        master_cog = self.bot.get_cog('Master')

        total_votes_users = len(votes)
        options_counts = {}
        for opt in active_survey['options']:
            opt_name = opt.get('name', opt) if isinstance(opt, dict) else opt
            options_counts[opt_name] = 0
            
        for v in votes:
            chosen = [c.strip() for c in v['selected_option'].split(',')]
            for c in chosen:
                if c in options_counts:
                    options_counts[c] += 1
                else:
                    options_counts[c] = 1

        stats_str = f"테스트 투표 참여인원: {total_votes_users}명\n"
        for opt, cnt in sorted(options_counts.items(), key=lambda item: item[1], reverse=True):
            ratio = (cnt / total_votes_users * 100) if total_votes_users > 0 else 0
            stats_str += f"- **{opt}**: {ratio:.1f}% ({cnt}표)\n"

        server_opinions = {}
        for v in votes:
            if v['opinion']:
                if v['server_id'] not in server_opinions:
                    server_opinions[v['server_id']] = []
                server_opinions[v['server_id']].append(f"[{v['selected_option']}] {v['opinion']}")

        all_opinions = [v['opinion'] for v in votes if v['opinion']]
        import asyncio
        chart_bytes = await asyncio.to_thread(master_cog.generate_option_chart_blocking, options_counts, survey_id)
        
        clustered_data = []
        if all_opinions:
            clustered_data = await master_cog.cluster_opinions(active_survey['topic'], all_opinions)

        import os
        import json
        os.makedirs(os.path.join("data", "charts"), exist_ok=True)
        result_data = {
            "survey_id": survey_id,
            "topic": active_survey['topic'],
            "total_votes": total_votes_users,
            "options_counts": options_counts,
            "stats_str": stats_str,
            "clustered_data": clustered_data
        }
        with open(os.path.join("data", "charts", f"survey_{survey_id}.json"), 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=4)

        embed = discord.Embed(
            title=f"🛠️ [테스트] 갈드컵 중간 결과: {active_survey['topic']}",
            description=stats_str,
            color=discord.Color.blue()
        )

        if clustered_data:
            cluster_text = ""
            valid_clusters = [c for c in clustered_data if c.get('count', 0) > 0]
            for idx, c in enumerate(valid_clusters):
                quote = c.get('quote', '')
                quote_str = f'\n> 💬 "{quote}"' if quote else ''
                cluster_text += f"**{idx+1}. {c.get('name', '그룹')}** ({c.get('count', 0)}명)\n*{c.get('summary', '')}*{quote_str}\n\n"
            if cluster_text:
                embed.add_field(name="🤖 AI 여론 분석 (유형별 대표 의견)", value=cluster_text[:1024], inline=False)

        import io
        files = []
        if chart_bytes:
            image_file = discord.File(io.BytesIO(chart_bytes), filename="chart_test.png")
            embed.set_image(url="attachment://chart_test.png")
            files.append(image_file)

        from cogs.survey import OpinionPaginationView
        all_ops_formatted = [f"[{v['selected_option']}] \"{v['opinion']}\"" for v in votes if v['opinion']]
        
        # 먼저 통계 및 차트 전송
        await ctx.send(embed=embed, files=files)
        
        # 의견이 있으면 별도의 메세지로 페이지네이션 뷰를 전송
        if all_ops_formatted:
            view = OpinionPaginationView(active_survey['topic'], all_ops_formatted)
            await ctx.send(embed=view.get_embed(), view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(BotAdmin(bot))

