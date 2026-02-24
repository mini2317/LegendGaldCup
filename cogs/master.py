import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import database
import json
import os
import random
import google.generativeai as genai
from datetime import datetime, timezone, timedelta
import io
import asyncio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import squarify

logger = logging.getLogger('discord')

class Master(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Load API Key
        api_key = os.getenv("GEMINI_API_KEY")
        model_name = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        
        if api_key and api_key != "your_gemini_api_key_here":
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name)
        else:
            self.model = None
            logger.error("GEMINI_API_KEY is not set or invalid. AI Master features will not work.")

        # Load Prompts
        try:
            with open("prompts.json", "r", encoding="utf-8") as f:
                self.prompts = json.load(f)
        except Exception as e:
            self.prompts = {}
            logger.error(f"Failed to load prompts.json: {e}")

        self.survey_loop.start()

    def cog_unload(self):
        self.survey_loop.cancel()

    async def evaluate_topic(self, topic: str, options: list) -> bool:
        if not self.model or not self.prompts:
            return False
            
        system = self.prompts.get("system", "")
        prompt_template = self.prompts.get("evaluate_topic", "")
        prompt = f"{system}\n\n{prompt_template.format(topic=topic, options=options)}"
        
        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text.upper()
            if "APPROVE" in text:
                return True
            return False
        except Exception as e:
            logger.error(f"Error evaluating topic with Gemini: {e}")
            return False

    async def generate_topic(self) -> dict:
        if not self.model or not self.prompts:
            return None
            
        system = self.prompts.get("system", "")
        prompt_template = self.prompts.get("generate_topic", "")
        prompt = f"{system}\n\n{prompt_template}"
        
        try:
            response = await self.model.generate_content_async(prompt)
            # Remove markdown code formatting if present
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
                
            data = json.loads(text.strip())
            
            if 'image_prompt' in data:
                import urllib.parse
                prompt_encoded = urllib.parse.quote(data['image_prompt'])
                data['image_url'] = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=800&height=400&nologo=true"
                
            return data
        except Exception as e:
            logger.error(f"Error generating topic with Gemini: {e}")
            return None

    async def refine_topic(self, topic: str, options: list) -> dict:
        if not self.model or not self.prompts:
            return None
            
        system = self.prompts.get("system", "")
        # Since we might not have a dedicated prompt for refining, we'll build an ad-hoc one based on system principles
        prompt = (
            f"{system}\n\n"
            f"유저가 제안한 다음 주제와 선택지들을 바탕으로, 아주 흥미롭고 세련된 '메인스트림 인터넷 커뮤니티' 감성의 황금 밸런스 갈드컵 (VS 게임) 주제로 완전히 다듬고 가공해주세요.\n"
            f"- 유저 제안 주제: {topic}\n"
            f"- 유저 제안 옵션들: {options}\n\n"
            f"응답은 반드시 아래 JSON 형식을 엄격하게 준수해야 하며 다른 말은 하지 마세요.\n"
            f'{{\n  "topic": "가공된 흥미로운 주제 (VS 형식의 제목)",\n  "options": [\n    {{"name": "가공된 짧은 선택지명 1", "desc": "가공된 톡톡 튀는 설명"}},\n    {{"name": "가공된 짧은 선택지명 2", "desc": "가공된 톡톡 튀는 설명"}}\n  ],\n  "image_prompt": "An impressive anime illustration of [주제 영어 번역], highly detailed"\n}}'
        )
        
        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
                
            data = json.loads(text.strip())
            return data
        except Exception as e:
            logger.error(f"Error refining topic with Gemini: {e}")
            return None

    async def cluster_opinions(self, topic: str, opinions: list) -> list:
        if not self.model or not self.prompts or not opinions:
            return []
            
        system = self.prompts.get("system", "")
        prompt_template = self.prompts.get("cluster_opinions", "")
        if not prompt_template:
            return []
        
        opinions_text = "\n".join([f"- {o}" for o in opinions])
        prompt = f"{system}\n\n{prompt_template.replace('{topic}', topic).replace('{opinions}', opinions_text)}"
        
        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
                
            data = json.loads(text.strip())
            return data
        except Exception as e:
            logger.error(f"Error clustering opinions with Gemini: {e}")
            return []

    def generate_option_chart_blocking(self, options_counts: dict, survey_id: int) -> bytes:
        if not options_counts or sum(options_counts.values()) == 0:
            return None
            
        import os
        from matplotlib import font_manager
        
        # Load explicit font
        font_path = os.path.join("src", "fonts", "BMJUA_ttf.ttf")
        if os.path.exists(font_path):
            font_prop = font_manager.FontProperties(fname=font_path)
        else:
            font_prop = font_manager.FontProperties(family='Malgun Gothic') # fallback
            
        # Sort data
        sorted_items = sorted(options_counts.items(), key=lambda x: x[1])
        labels = [item[0] for item in sorted_items]
        sizes = [item[1] for item in sorted_items]
        
        fig, ax = plt.subplots(figsize=(8, 7))
        
        # Strip emojis for font rendering safety
        import re
        def remove_emoji(text):
            return re.sub(r'[^\w\s,\.\?\!\(\)\-\:\u3131-\u3163\uac00-\ud7a3]', '', text).strip()
            
        safe_labels = [remove_emoji(l) for l in labels]
        
        # Pie/Donut Chart without inner labels
        colors = plt.cm.Set3.colors[:len(labels)]
        wedges, texts, autotexts = ax.pie(
            sizes, labels=None, autopct='%1.1f%%',
            startangle=140, colors=colors,
            wedgeprops=dict(width=0.4, edgecolor='w', linewidth=2),
            textprops=dict(fontproperties=font_prop, fontsize=12)
        )
        
        for autotext in autotexts:
            autotext.set_fontproperties(font_prop)
            autotext.set_fontsize(14)
            autotext.set_fontweight('bold')
                    
        # Add legend outside the pie to prevent overlapping
        ax.legend(wedges, safe_labels,
                  title="옵션 항목",
                  loc="center left",
                  bbox_to_anchor=(1, 0, 0.5, 1),
                  prop=font_prop)
                  
        ax.set_title('📊 갈드컵 득표 비율', fontproperties=font_prop, fontsize=18, pad=20)
        
        plt.tight_layout()
        
        # Save to Local Disk Archive
        os.makedirs(os.path.join("data", "charts"), exist_ok=True)
        archive_path = os.path.join("data", "charts", f"survey_{survey_id}.png")
        plt.savefig(archive_path, format='png', dpi=150, bbox_inches='tight', transparent=False, facecolor='#f8f9fa')
        
        # Also return bytes for immediate upload
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', transparent=False, facecolor='#f8f9fa')
        plt.close()
        return buf.getvalue()

    @tasks.loop(minutes=1)
    async def survey_loop(self):
        # Prevent initial instant execution bug
        active_survey = await database.get_active_survey()
        if not active_survey:
            logger.info("No active survey found on loop check. Starting a new one.")
            await self.process_survey_rotation()
            return
            
        start_time_str = active_survey['start_time']
        try:
            start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if now - start_time >= timedelta(hours=72):
                logger.info("72 hours passed since last survey started. Rotating.")
                await self.process_survey_rotation()
        except Exception as e:
            logger.error(f"Error in survey_loop time check: {e}")

    @survey_loop.before_loop
    async def before_survey_loop(self):
        logger.info("Waiting for bot to be ready before starting survey loop...")
        await self.bot.wait_until_ready()

    async def process_survey_rotation(self, forced_next_topic: dict = None, admin_user: discord.User = None):
        active_survey = await database.get_active_survey()
        channels = await database.get_all_active_announcement_channels()
        channel_ids = [c[1] for c in channels]
        guild_ids = [c[0] for c in channels]
        
        if active_survey:
            survey_id = active_survey['id']
            await database.deactivate_survey(survey_id)
            votes = await database.get_votes_for_survey(survey_id)
            
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

            # Prepare stats string
            stats_str = f"총 참여인원: {total_votes_users}명\n"
            for opt, cnt in sorted(options_counts.items(), key=lambda item: item[1], reverse=True):
                ratio = (cnt / total_votes_users * 100) if total_votes_users > 0 else 0
                stats_str += f"- **{opt}**: {ratio:.1f}% ({cnt}표)\n"

            # Prepare Cross-Server Opinion Exchange
            server_opinions = {}
            for v in votes:
                if v['opinion']:
                    if v['server_id'] not in server_opinions:
                        server_opinions[v['server_id']] = []
                    server_opinions[v['server_id']].append(f"[{v['selected_option']}] {v['opinion']}")

            chart_bytes = await asyncio.to_thread(self.generate_option_chart_blocking, options_counts, survey_id)
            
            clustered_data = []
            if all_opinions:
                clustered_data = await self.cluster_opinions(active_survey['topic'], all_opinions)

            # Save results text to JSON archive for lookup feature
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

            for guild_id, channel_id in channels:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        # Fallback try fetching if not in cache
                        channel = await self.bot.fetch_channel(channel_id)
                except Exception as e:
                    logger.warning(f"Could not fetch channel {channel_id}: {e}")
                    continue

                embed = discord.Embed(
                    title=f"🏁 갈드컵 종료: {active_survey['topic']}",
                    description=stats_str,
                    color=discord.Color.red()
                )



                # Add clustering summary text and quotes if available
                if clustered_data:
                    cluster_text = ""
                    valid_clusters = [c for c in clustered_data if c.get('count', 0) > 0]
                    for idx, c in enumerate(valid_clusters):
                        quote = c.get('quote', '')
                        quote_str = f'\n> 💬 "{quote}"' if quote else ''
                        cluster_text += f"**{idx+1}. {c.get('name', '그룹')}** ({c.get('count', 0)}명)\n*{c.get('summary', '')}*{quote_str}\n\n"
                    if cluster_text:
                        embed.add_field(name="🤖 AI 여론 분석 (유형별 대표 의견)", value=cluster_text[:1024], inline=False)

                files = []
                if chart_bytes:
                    image_file = discord.File(io.BytesIO(chart_bytes), filename="chart.png")
                    embed.set_image(url="attachment://chart.png")
                    files.append(image_file)

                try:
                    from cogs.survey import OpinionPaginationView
                    from cogs.survey import OpinionPaginationView
                    all_ops_formatted = [f"[{v['selected_option']}] \"{v['opinion']}\"" for v in votes if v['opinion']]
                    
                    # 먼저 통계 및 차트를 전송
                    await channel.send(embed=embed, files=files)
                    
                    # 의견이 있으면 별도의 메세지로 페이지네이션 뷰를 전송
                    if all_ops_formatted:
                        view = OpinionPaginationView(active_survey['topic'], all_ops_formatted)
                        await channel.send(embed=view.get_embed(), view=view)
                except Exception as e:
                    logger.error(f"Failed to send result to channel {channel_id}: {e}")

        # Pick new survey topic
        new_topic_data = forced_next_topic
        is_master = False
        
        if not new_topic_data:
            # 1순위: 대기열(Queue)에서 가장 첫 번째 주제 꺼내기
            new_topic_data = await database.get_next_queued_topic()

            if not new_topic_data:
                # 2순위: 큐가 비어있다면 AI 자동 생성(Gemini)
                is_master = True
                new_topic_data = await self.generate_topic()
                
                if not new_topic_data:
                    # 3순위: AI API 호출마저 실패 시 하드코딩된 폴백 주제
                    new_topic_data = {
                        "topic": "평생 여름 vs 평생 겨울",
                        "options": [
                            {"name": "평생 여름", "desc": "매일매일 폭염과 모기와 싸우며 에어컨 없이 살지 못하기"}, 
                            {"name": "평생 겨울", "desc": "매일매일 혹한과 싸우며 꽁꽁 얼어붙고 난방비 걱정하기"}
                        ],
                        "allow_multiple": False,
                        "allow_short_answer": False,
                        "image_prompt": "A dramatic clash between blazing hot summer sun and freezing winter blizzard, split screen"
                    }

        await self._apply_new_topic(new_topic_data, is_master=is_master, admin_force_user=admin_user)

    async def force_new_topic(self, topic_data: dict, admin_user: discord.User):
        """Called by botadmin cog to force a topic override and gracefully end the current one"""
        await self.process_survey_rotation(forced_next_topic=topic_data, admin_user=admin_user)
        # Note: we no longer restart survey_loop here because the 1-minute polled loop naturally handles the timing.

    async def _apply_new_topic(self, new_topic_data: dict, is_master: bool=False, admin_force_user: discord.User=None):
        channels = await database.get_all_active_announcement_channels()
        
        # Determine image_url
        image_url = new_topic_data.get('image_url')
        if is_master and 'image_prompt' in new_topic_data:
            import urllib.parse
            prompt_encoded = urllib.parse.quote(new_topic_data['image_prompt'])
            image_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=800&height=400&nologo=true"
            
        # Create new survey
        new_survey_id = await database.create_survey(
            topic=new_topic_data['topic'], 
            options=new_topic_data['options'], 
            allow_multiple=new_topic_data.get('allow_multiple', False), 
            allow_short_answer=new_topic_data.get('allow_short_answer', False),
            image_url=image_url
        )
        
        new_topic_data['id'] = new_survey_id
        
        # Announce new survey
        for guild_id, channel_id in channels:
            await self.announce_new_topic(guild_id, channel_id, new_topic_data, is_master, admin_force_user)
            
    async def announce_new_topic(self, guild_id, channel_id, new_topic_data, is_master:bool = False, admin_force_user: discord.User = None, is_new_channel:bool = False):
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                channel = await self.bot.fetch_channel(channel_id)
        except discord.NotFound:
            # Channel deleted! Disable it and DM server owner
            await database.set_announcement_enabled(guild_id, 0)
            try:
                guild = self.bot.get_guild(guild_id)
                if guild and guild.owner:
                    await guild.owner.send(f"⚠️ **[레전드 갈드컵]** 서버({guild.name})의 공지 채널이 삭제되었거나 봇이 접근할 수 없어 갈드컵 알림 송출이 자동 비활성화되었습니다. 서버 설정에서 다시 `/공지채널설정`을 진행해주세요.")
            except Exception:
                pass
            return
        except Exception:
            return

        manager_text = ""
        if admin_force_user:
            manager_text = f"🚨 **봇 관리자({admin_force_user.name})에 의해 갈드컵 주제가 긴급 변경되었습니다!**"
        elif is_master:
            manager_text = "✨ 마스터(AI)가 새롭고 흥미로운 갈드컵 주제를 가져왔습니다!"
        else:
            manager_text = "🎉 제안 목록 심사를 통과하여 선정된 이번 주 갈드컵 주제입니다!"
        
        from datetime import datetime, timezone, timedelta
        if 'start_time' in new_topic_data and isinstance(new_topic_data['start_time'], str):
            start_time = datetime.strptime(new_topic_data['start_time'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            end_time = int((start_time + timedelta(hours=72)).timestamp())
        else:
            end_time = int((datetime.now(timezone.utc) + timedelta(hours=72)).timestamp())

        embed = discord.Embed(
            title=f"{'📣 새로운 주제' if not is_new_channel else '📢 현재 진행 중인 갈드컵 주제'}: {new_topic_data['topic']}",
            description=f"{manager_text}\n\n아래 선택바를 클릭해 당신의 선택과 의견을 남겨주세요!\n⏳ **투표 마감 예정:** <t:{end_time}:R>",
            color=(discord.Color.green() if not is_new_channel else discord.Color.yellow()) if not admin_force_user else discord.Color.brand_red()
        )
        
        options = new_topic_data['options']
        if isinstance(options, str):
            import json
            options = json.loads(options)
            
        desc_text = ""
        for idx, opt in enumerate(options):
            if isinstance(opt, dict):
                desc_text += f"**{idx+1}. {opt.get('name', '옵션')}**\n- {opt.get('desc', '')}\n\n"
            else:
                desc_text += f"**{idx+1}. {opt}**\n"
                
        if desc_text:
            embed.add_field(name="선택지", value=desc_text.strip(), inline=False)
            
        image_url = new_topic_data.get('image_url')
        if image_url:
            import urllib.parse
            parsed = urllib.parse.urlparse(image_url)
            is_image = parsed.path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')) or 'pollinations.ai' in image_url
            
            if is_image:
                embed.set_image(url=image_url)
            else:
                embed.add_field(name="🔗 참고 링크", value=image_url, inline=False)
        
        from cogs.survey import VoteSelectView
        survey_id = new_topic_data.get('id', 0)
        view = VoteSelectView(
            survey_id, 
            options, 
            bool(new_topic_data.get('allow_short_answer', False)), 
            bool(new_topic_data.get('allow_multiple', False))
        )
        
        # 이전 메시지 고정 해제 및 버튼 제거 (bot 메시지만 추출)
        try:
            pins = await channel.pins()
            for p_msg in pins:
                if p_msg.author == self.bot.user and p_msg.embeds and ("📣 새로운 주제" in str(p_msg.embeds[0].title) or "📢 현재 진행 중인" in str(p_msg.embeds[0].title)):
                    await p_msg.unpin()
                    try:
                        await p_msg.edit(view=None)
                    except Exception:
                        pass
                    break
        except Exception:
            pass
            
        try:
            msg = await channel.send(embed=embed, view=view)
            try:
                await msg.pin(reason="최신 갈드컵 주제 메시지 지정을 위해 고정")
            except discord.Forbidden:
                # 핀 고정 권한이 없는 경우 조용히 무시하되, 메시지 하단에 경고 문구 추가
                embed.description += "\n\n⚠️ *(봇에게 **'메시지 관리'** 권한이 없어 이 메시지를 상단 고정할 수 없습니다. 채널 권한 설정을 확인해주세요!)*"
                await msg.edit(embed=embed)
        except discord.Forbidden:
            # 메시지 채널 전송 권한 자체가 없는 경우
            await database.set_announcement_enabled(guild_id, 0)
            try:
                guild = self.bot.get_guild(guild_id)
                if guild and guild.owner:
                    await guild.owner.send(f"⚠️ **[레전드 갈드컵]** 서버({guild.name})의 공지 채널에 메시지 전송 권한이 없어 송출에 실패했습니다. 알림이 자동 비활성화되었으니 봇에게 권한을 주고 다시 `/공지채널설정`을 올려주세요.")
            except Exception:
                pass
        except Exception as e:
            pass

    @app_commands.command(name="강제주기전환_테스트용", description="[관리자 전용] 3일 주기를 무시하고 즉시 다음 설문조사로 넘어갑니다.")
    @app_commands.default_permissions(administrator=True)
    async def force_skip(self, interaction: discord.Interaction):
        await interaction.response.send_message("⚙️ 강제로 주제 마감 및 새 주제 생성을 시작합니다... (이 작업은 몇 초 정도 걸릴 수 있습니다.)", ephemeral=True)
        await self.process_survey_rotation()

async def setup(bot: commands.Bot):
    await bot.add_cog(Master(bot))
