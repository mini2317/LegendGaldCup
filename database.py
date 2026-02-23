import aiosqlite
import json
import logging

DB_FILE = "legend_galdcup.db"
logger = logging.getLogger("discord")

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # 서버 정보 테이블
        await db.execute('''
            CREATE TABLE IF NOT EXISTS servers (
                guild_id INTEGER PRIMARY KEY,
                announcement_channel_id INTEGER,
                announcement_enabled INTEGER DEFAULT 1
            )
        ''')
        
        try:
            await db.execute('ALTER TABLE servers ADD COLUMN announcement_enabled INTEGER DEFAULT 1')
        except Exception:
            pass
        
        # 설문조사 메인 테이블
        await db.execute('''
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                options TEXT NOT NULL,
                allow_multiple INTEGER DEFAULT 0,
                allow_short_answer INTEGER DEFAULT 0,
                image_url TEXT,
                is_active INTEGER DEFAULT 1,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP
            )
        ''')
        
        try:
            await db.execute('ALTER TABLE surveys ADD COLUMN image_url TEXT')
        except Exception:
            pass
        
        # 투표 기록 테이블
        # user_id는 중복투표 확인용, opinion은 300자 이내
        await db.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                server_id INTEGER NOT NULL,
                selected_option TEXT NOT NULL,
                opinion TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(survey_id, user_id)
            )
        ''')
        
        # 유저가 제안한 주제 테이블
        await db.execute('''
            CREATE TABLE IF NOT EXISTS suggested_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                options TEXT NOT NULL,
                allow_multiple INTEGER DEFAULT 0,
                allow_short_answer INTEGER DEFAULT 0,
                suggested_by INTEGER NOT NULL,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        try:
            await db.execute('ALTER TABLE suggested_topics ADD COLUMN image_url TEXT')
        except Exception:
            pass
        
        # 봇 관리자 테이블 (부관리자 목록)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.commit()
        logger.info("Database initialized successfully.")


# --- Helper Functions ---

async def set_announcement_channel(guild_id: int, channel_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO servers (guild_id, announcement_channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET announcement_channel_id=excluded.announcement_channel_id
        ''', (guild_id, channel_id))
        await db.commit()

async def get_announcement_channel(guild_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT announcement_channel_id FROM servers WHERE guild_id = ?', (guild_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_announcement_enabled(guild_id: int, enabled: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE servers SET announcement_enabled = ? WHERE guild_id = ?
        ''', (enabled, guild_id))
        await db.commit()

async def get_all_active_announcement_channels():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT guild_id, announcement_channel_id FROM servers WHERE announcement_channel_id IS NOT NULL AND announcement_enabled = 1') as cursor:
            return await cursor.fetchall()

async def create_survey(topic: str, options: list, allow_multiple: bool, allow_short_answer: bool, image_url: str = None):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('''
            INSERT INTO surveys (topic, options, allow_multiple, allow_short_answer, image_url)
            VALUES (?, ?, ?, ?, ?)
        ''', (topic, json.dumps(options, ensure_ascii=False), int(allow_multiple), int(allow_short_answer), image_url)) as cursor:
            survey_id = cursor.lastrowid
        await db.commit()
        return survey_id

async def get_active_survey():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM surveys WHERE is_active = 1 ORDER BY id DESC LIMIT 1') as cursor:
            row = await cursor.fetchone()
            if row:
                survey = dict(row)
                survey['options'] = json.loads(survey['options'])
                survey['allow_multiple'] = bool(survey['allow_multiple'])
                survey['allow_short_answer'] = bool(survey['allow_short_answer'])
                return survey
            return None

async def deactivate_survey(survey_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE surveys SET is_active = 0, end_time = CURRENT_TIMESTAMP WHERE id = ?', (survey_id,))
        await db.commit()

async def save_vote(survey_id: int, user_id: int, server_id: int, selected_option: str, opinion: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO votes (survey_id, user_id, server_id, selected_option, opinion, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(survey_id, user_id) DO UPDATE SET 
                selected_option=excluded.selected_option, 
                opinion=excluded.opinion,
                server_id=excluded.server_id,
                updated_at=CURRENT_TIMESTAMP
        ''', (survey_id, user_id, server_id, selected_option, opinion))
        await db.commit()

async def get_user_vote(survey_id: int, user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM votes WHERE survey_id = ? AND user_id = ?', (survey_id, user_id)) as cursor:
            return await cursor.fetchone()

async def get_votes_for_survey(survey_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM votes WHERE survey_id = ? ORDER BY updated_at DESC', (survey_id,)) as cursor:
            return await cursor.fetchall()

async def has_pending_suggestion(user_id: int) -> bool:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT 1 FROM suggested_topics WHERE suggested_by = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row)

async def suggest_topic(topic: str, options: list, allow_multiple: bool, allow_short_answer: bool, user_id: int, image_url: str = None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO suggested_topics (topic, options, allow_multiple, allow_short_answer, suggested_by, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (topic, json.dumps(options, ensure_ascii=False), int(allow_multiple), int(allow_short_answer), user_id, image_url))
        await db.commit()

async def pop_random_suggested_topic():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM suggested_topics ORDER BY RANDOM() LIMIT 1') as cursor:
            row = await cursor.fetchone()
            if row:
                await db.execute('DELETE FROM suggested_topics WHERE id = ?', (row['id'],))
                await db.commit()
                topic_data = dict(row)
                topic_data['options'] = json.loads(topic_data['options'])
                topic_data['allow_multiple'] = bool(topic_data['allow_multiple'])
                topic_data['allow_short_answer'] = bool(topic_data['allow_short_answer'])
                return topic_data
            return None

async def get_past_surveys(limit=5):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM surveys WHERE is_active = 0 ORDER BY end_time DESC LIMIT ?', (limit,)) as cursor:
            return await cursor.fetchall()

# --- Bot Admin Functions ---
async def add_bot_admin(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)', (user_id,))
        await db.commit()

async def remove_bot_admin(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('DELETE FROM bot_admins WHERE user_id = ?', (user_id,))
        await db.commit()

async def is_bot_admin(user_id: int, master_id: int) -> bool:
    if user_id == master_id:
        return True
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT 1 FROM bot_admins WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row)

async def get_all_bot_admins():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT user_id FROM bot_admins') as cursor:
            rows = await cursor.fetchall()
            return [str(row[0]) for row in rows]

async def get_all_suggested_topics():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM suggested_topics ORDER BY id ASC') as cursor:
            rows = await cursor.fetchall()
            topics = []
            for row in rows:
                t = dict(row)
                t['options'] = json.loads(t['options'])
                t['allow_multiple'] = bool(t['allow_multiple'])
                t['allow_short_answer'] = bool(t['allow_short_answer'])
                topics.append(t)
            return topics

async def update_suggested_topic(topic_id: int, topic: str, options: list, allow_multiple: bool, allow_short_answer: bool, image_url: str = None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE suggested_topics 
            SET topic = ?, options = ?, allow_multiple = ?, allow_short_answer = ?, image_url = ?
            WHERE id = ?
        ''', (topic, json.dumps(options, ensure_ascii=False), int(allow_multiple), int(allow_short_answer), image_url, topic_id))
        await db.commit()

async def delete_suggested_topic(topic_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('DELETE FROM suggested_topics WHERE id = ?', (topic_id,))
        await db.commit()

