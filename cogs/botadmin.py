import discord
from discord.ext import commands
from discord import app_commands
import logging
import database
import os
import json
import shlex

logger = logging.getLogger('discord')

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
        max_length=200
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

    @discord.ui.button(label="승인", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.master_cog.force_new_topic(self.generated_data, interaction.user)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="✅ 승인되어 즉시 새 주제로 지정되었습니다!", view=self)

    @discord.ui.button(label="거절", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ 생성된 주제가 거절되었습니다.", view=self)


class EditTopicModal(discord.ui.Modal):
    def __init__(self, topic_data: dict, ui_view: discord.ui.View):
        super().__init__(title='대기열 주제 수정하기')
        self.topic_data = topic_data
        self.ui_view = ui_view
        
        self.topic = discord.ui.TextInput(
            label='1. 갈드컵 주제',
            style=discord.TextStyle.short,
            default=topic_data['topic'],
            required=True,
            max_length=100
        )
        self.add_item(self.topic)
        
        # Format options for editing
        options_str = []
        for opt in topic_data['options']:
            if isinstance(opt, dict):
                desc = opt.get('desc', '')
                if desc:
                    options_str.append(f"{opt.get('name')}:{desc}")
                else:
                    options_str.append(str(opt.get('name', '')))
            else:
                options_str.append(str(opt))
                
        self.options = discord.ui.TextInput(
            label='2. 선택 옵션 (이름:설명, 쉼표 구분)',
            style=discord.TextStyle.short,
            default=", ".join(options_str)[:200],
            required=True,
            max_length=200
        )
        self.add_item(self.options)

        self.allow_multiple = discord.ui.TextInput(
            label='3. 중복투표 가능여부 (O/X)',
            style=discord.TextStyle.short,
            default='O' if topic_data['allow_multiple'] else 'X',
            required=True,
            max_length=1
        )
        self.add_item(self.allow_multiple)

        self.allow_short = discord.ui.TextInput(
            label='4. 단답형 허용여부 (O/X)',
            style=discord.TextStyle.short,
            default='O' if topic_data['allow_short_answer'] else 'X',
            required=True,
            max_length=1
        )
        self.add_item(self.allow_short)
        
        self.image_url = discord.ui.TextInput(
            label='5. 대표 이미지 URL (선택사항)',
            style=discord.TextStyle.short,
            default=topic_data.get('image_url', '') or '',
            required=False,
            max_length=200
        )
        self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        topic_text = self.topic.value
        options_list = [opt.strip() for opt in self.options.value.split(',') if opt.strip()]
        if len(options_list) < 2:
            await interaction.response.send_message("옵션은 최소 2개 이상이어야 합니다.", ephemeral=True)
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

        await database.update_suggested_topic(self.topic_data['id'], topic_text, parsed_options, is_multiple, is_short, img_val)
        
        # update the UI view's internal data
        self.topic_data['topic'] = topic_text
        self.topic_data['options'] = parsed_options
        self.topic_data['allow_multiple'] = is_multiple
        self.topic_data['allow_short_answer'] = is_short
        self.topic_data['image_url'] = img_val
        
        await interaction.response.edit_message(embed=self.ui_view.get_current_embed(), view=self.ui_view)


class TopicPaginationView(discord.ui.View):
    def __init__(self, topics: list, master_cog):
        super().__init__(timeout=None)
        self.topics = topics
        self.master_cog = master_cog
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
            self.force_pick_btn.disabled = True
            self.edit_btn.disabled = True
            self.delete_btn.disabled = True
            self.ai_pick_btn.disabled = True

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
            embed.set_thumbnail(url=topic.get('image_url'))
            
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
        
    @discord.ui.button(label="이 주제로 수동 채택", style=discord.ButtonStyle.success, emoji="✅")
    async def force_pick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        topic = self.topics[self.current_page]
        await database.delete_suggested_topic(topic['id'])
        await self.master_cog.force_new_topic(topic, interaction.user)
        
        # UI에서 삭제 처리
        self.topics.pop(self.current_page)
        self.max_pages = len(self.topics)
        if self.current_page >= self.max_pages and self.current_page > 0:
            self.current_page -= 1
        self.update_buttons()
        
        await interaction.response.edit_message(
            content=f"✅ **[{topic['topic']}]** 주제가 즉시 채택되어 전체 서버 방출되었습니다!", 
            embed=self.get_current_embed(), 
            view=self
        )
        
    @discord.ui.button(label="이 주제 수정", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        topic = self.topics[self.current_page]
        await interaction.response.send_modal(EditTopicModal(topic, self))

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

    @discord.ui.button(label="AI로 가공 후 채택", style=discord.ButtonStyle.primary, emoji="🤖")
    async def ai_pick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        topic = self.topics[self.current_page]
        
        is_valid = await self.master_cog.evaluate_topic(topic['topic'], topic['options'])
        if is_valid:
            await database.delete_suggested_topic(topic['id'])
            await self.master_cog.force_new_topic(topic, interaction.user)
            await interaction.followup.send("✅ AI가 승인하여 새로운 주제로 채택, 즉시 교체되었습니다.", ephemeral=True)
        else:
            await interaction.followup.send("❌ AI가 이 주제를 부적절하다고 평가(REJECT)했습니다.", ephemeral=True)

    @discord.ui.button(label="인공지능 자체생성", style=discord.ButtonStyle.primary, emoji="✨")
    async def ai_gen_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        generated_data = await self.master_cog.generate_topic()
        
        if generated_data:
            embed = discord.Embed(
                title="✨ AI 생성 주제 결과",
                description=f"**{generated_data['topic']}**\n옵션: {', '.join(generated_data['options'])}",
                color=discord.Color.purple()
            )
            view = AIGeneratedTopicView(self.master_cog, generated_data, interaction.user)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send("❌ AI 주제 생성에 실패했습니다.", ephemeral=True)

    @discord.ui.button(label="직접 작성하여 채택", style=discord.ButtonStyle.success, emoji="✍️")
    async def manual_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DirectTopicModal(self.master_cog))


class BotAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
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
                
                await database.suggest_topic(
                    topic=generated_data['topic'],
                    options=generated_data['options'],
                    allow_multiple=generated_data.get('allow_multiple', False),
                    allow_short_answer=generated_data.get('allow_short_answer', False),
                    user_id=MASTER_ADMIN_ID,
                    image_url=image_url
                )
                success_count += 1
                
        await ctx.send(f"✅ 대기열 큐(Queue)에 **{success_count}개**의 AI 주제 충전이 완료되었습니다! (`!주제관리` 인터페이스로 확인 및 수정 가능)")

    @commands.command(name="업데이트", description="[총관리자 전용] Github 저장소에서 최신 코드를 즉시 불러오고 봇을 리로드합니다.")
    async def update_bot(self, ctx: commands.Context):
        if str(ctx.author.id) != str(MASTER_ADMIN_ID):
            await ctx.send("❌ 이 명령어는 `.env`에 설정된 총관리자 전용입니다.")
            return
            
        await ctx.send("⏳ Github에서 최신 코드를 가져오는 중입니다...")
        
        import subprocess
        try:
            # git 버전을 체크하고 pull 받음
            result = await asyncio.to_thread(
                subprocess.run,
                ['git', 'pull'],
                capture_output=True,
                text=True,
                check=True
            )
            
            output = result.stdout.strip()
            if "Already up to date" in output or "이미 업데이트 상태입니다" in output:
                await ctx.send("✅ 이미 최신 버전입니다. 업데이트할 내용이 없습니다.")
                return
                
            await ctx.send(f"📦 업데이트 내역이 감지되었습니다:\n```\n{output[:1800]}\n```\n🔄 최신 코드를 즉시 적용하기 위해 모듈들(Cogs) 무중단 패치를 시작합니다...")
            
            # Cogs 폴더의 모든 확장을 리로드
            import os
            cogs_dir = "cogs"
            reloaded = []
            for filename in os.listdir(cogs_dir):
                if filename.endswith('.py') and not filename.startswith('__'):
                    cog_name = f"cogs.{filename[:-3]}"
                    try:
                        await self.bot.reload_extension(cog_name)
                        reloaded.append(filename)
                    except Exception as e:
                        await ctx.send(f"❌ `{cog_name}` 리로드 실패: {e}")
            
            await ctx.send(f"🌌 **업데이트 완료!** 무중단 패치가 성공적으로 적용된 모듈: {', '.join(reloaded)}")
            
        except subprocess.CalledProcessError as e:
            await ctx.send(f"🚨 Github에서 코드를 가져오는 중 오류가 발생했습니다.\n```\n{e.stderr[:1800]}\n```")
        except Exception as e:
            await ctx.send(f"🚨 기타 오류 발생: {e}")

    @commands.command(name="주제관리", description="[관리자 전용] DM으로 제안된 주제들을 열람하고 AI 생성이나 수동 채택을 진행합니다.")
    async def manage_topics(self, ctx: commands.Context):
        if not await self.check_is_bot_admin(ctx):
            return
        
        # DM 전송 시도
        try:
            topics = await database.get_all_suggested_topics()
            master_cog = self.bot.get_cog('Master')
            
            view = TopicPaginationView(topics, master_cog)
            embed = view.get_current_embed()
            
            await ctx.author.send(embed=embed, view=view)
            await ctx.send("✅ DM으로 주제 관리 인터페이스를 전송했습니다.")
        except discord.Forbidden:
            await ctx.send("❌ DM 전송이 막혀있습니다. 개인 설정에서 서버 구성원의 다이렉트 메시지를 허용해주세요.")
        except Exception as e:
            logger.error(f"Error in manage_topics: {e}")
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

async def setup(bot: commands.Bot):
    await bot.add_cog(BotAdmin(bot))

