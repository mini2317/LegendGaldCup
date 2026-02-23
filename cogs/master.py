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
            return data
        except Exception as e:
            logger.error(f"Error generating topic with Gemini: {e}")
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

    def generate_opinion_chart_blocking(self, clustered_data: list) -> bytes:
        if not clustered_data:
            return None
            
        # Filter out invalid or zero-count clusters to prevent squarify ZeroDivisionError
        valid_data = [item for item in clustered_data if item.get('count', 0) > 0]
        if not valid_data:
            return None
            
        plt.rcParams['font.family'] = 'Malgun Gothic'
        plt.rcParams['axes.unicode_minus'] = False
        
        sizes = [item.get('count', 1) for item in valid_data]
        labels = [f"{item.get('name', '그룹')}\n({item.get('count', 0)})" for item in valid_data]
        
        # If there are more clusters than colors, we can loop colors or slice safely
        colors = list(plt.cm.Pastel1.colors)
        if len(valid_data) > len(colors):
            colors = colors * (len(valid_data) // len(colors) + 1)
        
        plt.figure(figsize=(8, 6))
        squarify.plot(sizes=sizes, label=labels, color=colors[:len(valid_data)], alpha=0.8, text_kwargs={'fontsize':11, 'weight':'bold'})
        plt.axis('off')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
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
            options_counts = {opt: 0 for opt in active_survey['options']}
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

            # AI Clustering and Chart Generation
            all_opinions = [v['opinion'] for v in votes if v['opinion']]
            chart_bytes = None
            clustered_data = []
            if all_opinions:
                clustered_data = await self.cluster_opinions(active_survey['topic'], all_opinions)
                if clustered_data:
                    chart_bytes = await asyncio.to_thread(self.generate_opinion_chart_blocking, clustered_data)

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

                # Local server's opinions
                local_ops = server_opinions.get(guild_id, [])
                if local_ops:
                    sample_local = random.sample(local_ops, min(3, len(local_ops)))
                    embed.add_field(
                        name="🔥 우리 서버의 반응", 
                        value="\n".join([f"- {opt}" for opt in sample_local]), 
                        inline=False
                    )

                # Pick a random OTHER server's opinions
                other_servers = [sid for sid in server_opinions.keys() if sid != guild_id]
                if other_servers:
                    picked_server = random.choice(other_servers)
                    opinions = server_opinions[picked_server]
                    # Show up to 3 random opinions from that server
                    sample_opinions = random.sample(opinions, min(3, len(opinions)))
                    embed.add_field(
                        name="💌 타 서버의 익명 반응 도착!", 
                        value="\n".join([f"- {opt}" for opt in sample_opinions]), 
                        inline=False
                    )
                else:
                    embed.add_field(name="💌 타 서버 반응", value="타 서버에서 등록된 의견이 충분하지 않습니다.", inline=False)

                # Add clustering summary text if available
                if clustered_data:
                    cluster_text = ""
                    valid_clusters = [c for c in clustered_data if c.get('count', 0) > 0]
                    for idx, c in enumerate(valid_clusters):
                        cluster_text += f"**{idx+1}. {c.get('name', '그룹')}** ({c.get('count', 0)}명)\n*{c.get('summary', '')}*\n\n"
                    if cluster_text:
                        embed.add_field(name="🤖 AI 여론 분석 결과", value=cluster_text[:1024], inline=False)

                files = []
                if chart_bytes:
                    image_file = discord.File(io.BytesIO(chart_bytes), filename="chart.png")
                    embed.set_image(url="attachment://chart.png")
                    files.append(image_file)

                try:
                    await channel.send(embed=embed, files=files)
                except Exception as e:
                    logger.error(f"Failed to send result to channel {channel_id}: {e}")

        # Pick new survey topic
        new_topic_data = forced_next_topic
        is_master = False
        
        if not new_topic_data:
            # Try finding a user-suggested topic
            for _ in range(10): # Try up to 10 randomly picked user topics
                topic_row = await database.pop_random_suggested_topic()
                if not topic_row:
                    break
                    
                is_valid = await self.evaluate_topic(topic_row['topic'], topic_row['options'])
                if is_valid:
                    new_topic_data = topic_row
                    break

            if not new_topic_data:
                # Fallback to Gemini generation
                is_master = True
                new_topic_data = await self.generate_topic()
                
                if not new_topic_data:
                    # Absolute fallback if API fails
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
        
        # Announce new survey
        for guild_id, channel_id in channels:
            try:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                continue

            manager_text = ""
            if admin_force_user:
                manager_text = f"🚨 **봇 관리자({admin_force_user.name})에 의해 갈드컵 주제가 긴급 변경되었습니다!**"
            elif is_master:
                manager_text = "✨ 마스터(AI)가 새롭고 흥미로운 갈드컵 주제를 가져왔습니다!"
            else:
                manager_text = "🎉 제안 목록 심사를 통과하여 선정된 이번 주 갈드컵 주제입니다!"
            
            embed = discord.Embed(
                title=f"📣 새로운 주제: {new_topic_data['topic']}",
                description=f"{manager_text}\n\n채팅창에 `/투표` 를 입력해 당신의 선택과 의견을 남겨주세요!",
                color=discord.Color.green() if not admin_force_user else discord.Color.brand_red()
            )
            
            desc_text = ""
            for idx, opt in enumerate(new_topic_data['options']):
                if isinstance(opt, dict):
                    desc_text += f"**{idx+1}. {opt.get('name', '옵션')}**\n- {opt.get('desc', '')}\n\n"
                else:
                    desc_text += f"**{idx+1}. {opt}**\n"
                    
            if desc_text:
                embed.add_field(name="선택지", value=desc_text.strip(), inline=False)
                
            if image_url:
                embed.set_image(url=image_url)
            
            try:
                await channel.send(embed=embed)
            except Exception as e:
                pass



    @app_commands.command(name="강제주기전환_테스트용", description="[관리자 전용] 3일 주기를 무시하고 즉시 다음 설문조사로 넘어갑니다.")
    @app_commands.default_permissions(administrator=True)
    async def force_skip(self, interaction: discord.Interaction):
        await interaction.response.send_message("⚙️ 강제로 주제 마감 및 새 주제 생성을 시작합니다... (이 작업은 몇 초 정도 걸릴 수 있습니다.)", ephemeral=True)
        await self.process_survey_rotation()

async def setup(bot: commands.Bot):
    await bot.add_cog(Master(bot))
