import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import time

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='/', intents=intents)

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch',
    'quiet': True,
    'retries': 10,                # 重試次數增加
    'socket_timeout': 15,         # 增加網路超時秒數 
}

IDLE_TIMEOUT = 180  # 3分鐘無播放自動斷開
EMPTY_TIMEOUT = 60  # 1分鐘沒人自動斷開

queues = {}          # {guild_id: [ {'url':..., 'title':...}, ... ]}
last_play_times = {} # {guild_id: timestamp}
empty_times = {}     # {guild_id: timestamp}

status_messages = {}  # {guild_id: discord.Message} 用來存播放狀態訊息
playing_info = {}     # {guild_id: dict} 包含 title, duration, start_time, paused_time 等播放資訊

def get_queue(guild_id):
    return queues.setdefault(guild_id, [])

async def update_last_play_time(guild_id):
    last_play_times[guild_id] = time.time()
    empty_times.pop(guild_id, None)  # 有人在聽音樂，清空沒人計時

async def update_empty_time(guild_id):
    if guild_id not in empty_times:
        empty_times[guild_id] = time.time()

# 更新機器人 Discord 狀態列，顯示正在聽歌，或清除狀態
async def update_bot_presence(title=None, artist=None):
    if title and artist:
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{title} - {artist}"
        )
    else:
        activity = None
    await bot.change_presence(activity=activity)

async def check_idle():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = time.time()
        guilds_with_voice = set(vc.guild.id for vc in bot.voice_clients)

        all_guild_ids = list(queues.keys())
        for guild_id in all_guild_ids:
            if guild_id not in guilds_with_voice:
                queues.pop(guild_id, None)
                last_play_times.pop(guild_id, None)
                empty_times.pop(guild_id, None)
                status_messages.pop(guild_id, None)
                playing_info.pop(guild_id, None)
                print(f"清除 {guild_id} 的播放佇列，因為不在語音頻道")

        for vc in bot.voice_clients:
            guild_id = vc.guild.id
            channel = vc.channel
            members = [m for m in channel.members if not m.bot]

            if len(members) == 0:
                await update_empty_time(guild_id)
                if now - empty_times.get(guild_id, now) > EMPTY_TIMEOUT:
                    await vc.disconnect()
                    queues.pop(guild_id, None)
                    last_play_times.pop(guild_id, None)
                    empty_times.pop(guild_id, None)
                    status_messages.pop(guild_id, None)
                    playing_info.pop(guild_id, None)
                    print(f"離開 {vc.guild.name}，因為頻道沒人超過1分鐘")
            else:
                empty_times.pop(guild_id, None)
                if not vc.is_playing():
                    last_play = last_play_times.get(guild_id, now)
                    if now - last_play > IDLE_TIMEOUT:
                        await vc.disconnect()
                        queues.pop(guild_id, None)
                        last_play_times.pop(guild_id, None)
                        status_messages.pop(guild_id, None)
                        playing_info.pop(guild_id, None)
                        print(f"離開 {vc.guild.name}，因為超過3分鐘沒有播放歌曲")

        await asyncio.sleep(15)

def seconds_to_timestamp(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02}"

def create_time_display(elapsed, total):
    return f"{seconds_to_timestamp(elapsed)} / {seconds_to_timestamp(total)}"

async def update_status_embed(guild_id):
    msg = status_messages.get(guild_id)
    if not msg:
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=msg.guild)
    if not voice_client or not voice_client.is_connected():
        try:
            await msg.delete()
        except:
            pass
        status_messages.pop(guild_id, None)
        playing_info.pop(guild_id, None)
        return

    info = playing_info.get(guild_id, None)
    if not info:
        return

    if voice_client.is_playing():
        state = "▶️ 播放中"
    elif voice_client.is_paused():
        state = "⏸ 暫停中"
    else:
        state = "⏹ 停止"

    embed = discord.Embed(title=f"音樂播放狀態 - {state}", color=discord.Color.blurple())
    embed.add_field(name="目前歌曲", value=info['title'], inline=False)

    try:
        await msg.edit(embed=embed, view=MusicControls(msg))
    except Exception as e:
        print(f"更新播放狀態訊息失敗: {e}")

class MusicControls(discord.ui.View):
    def __init__(self, message):
        super().__init__(timeout=None)
        self.message = message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # 任何人都能使用按鈕
        return True

    @discord.ui.button(label="暫停", style=discord.ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            playing_info[interaction.guild.id]['paused_at'] = time.time()
            await interaction.response.send_message("⏸ 已暫停播放", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂", ephemeral=True)

    @discord.ui.button(label="繼續", style=discord.ButtonStyle.success)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            paused_duration = time.time() - playing_info[interaction.guild.id].get('paused_at', time.time())
            playing_info[interaction.guild.id]['paused_time'] = playing_info[interaction.guild.id].get('paused_time', 0) + paused_duration
            vc.resume()
            await interaction.response.send_message("▶️ 已繼續播放", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 音樂沒有被暫停", ephemeral=True)

    class MusicControls(discord.ui.View):
        def __init__(self, message):
            super().__init__(timeout=None)
            self.message = message

    @discord.ui.button(label="停止", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()
            guild_id = interaction.guild.id

            # 刪除狀態訊息
            msg = status_messages.pop(guild_id, None)
            if msg:
                try:
                    await msg.delete()
                except Exception as e:
                    print(f"刪除狀態訊息失敗: {e}")

            playing_info.pop(guild_id, None)
            await update_bot_presence()  # 清除機器人狀態列
            await interaction.response.send_message("🛑 已停止播放並離開語音頻道", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 我不在語音頻道", ephemeral=True)


    @discord.ui.button(label="跳過", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()  # 會觸發 play_next
            await interaction.response.send_message("⏭ 已跳過當前歌曲", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 沒有正在播放的音樂", ephemeral=True)

    @discord.ui.button(label="清單", style=discord.ButtonStyle.secondary)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        queue = get_queue(guild_id)
        if not queue:
            await interaction.response.send_message("📭 播放佇列是空的", ephemeral=True)
            return
        msg = "📃 播放佇列：\n"
        for i, song in enumerate(queue, start=1):
            msg += f"{i}. {song['title']}\n"
        await interaction.response.send_message(msg, ephemeral=True)

async def play_next(ctx):
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not queue:
        try:
            ch = ctx.channel if hasattr(ctx, 'channel') else ctx.interaction.channel
            await ch.send("📭 播放清單已空，請使用 /play 加入更多歌曲。")
        except Exception as e:
            print(f"傳送訊息失敗: {e}")
        # 清除播放資訊和狀態
        playing_info.pop(guild_id, None)
        msg = status_messages.pop(guild_id, None)
        if msg:
            try:
                await msg.delete()
            except:
                pass
        # 清除機器人狀態
        await update_bot_presence()
        return

    current = queue.pop(0)
    url = current['url']

    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            audio_url = info['url']
            duration = info.get('duration', 0)
            title = info.get('title', '未知')

        source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)

        def after_play(error):
            fut = asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
            try:
                fut.result()
            except Exception as e:
                print(f'播放下一首錯誤: {e}')

        voice_client.play(source, after=after_play)

        # 記錄播放資訊
        playing_info[guild_id] = {
            'title': title,
            'duration': duration,
            'start_time': time.time(),
            'paused_time': 0,
            'paused_at': None,
        }

        await update_last_play_time(guild_id)

        # 更新播放狀態訊息
        if guild_id in status_messages:
            try:
                await update_status_embed(guild_id)
            except Exception as e:
                print(f"更新狀態訊息失敗: {e}")
        else:
            try:
                ch = ctx.channel if hasattr(ctx, 'channel') else ctx.interaction.channel
                view = MusicControls(None)
                msg = await ch.send(f"🎶 正在播放: **{title}**", view=view)
                status_messages[guild_id] = msg
                view.message = msg
            except Exception as e:
                print(f"發送狀態訊息失敗: {e}")

        # 更新機器人狀態列，顯示正在聽
        await update_bot_presence(title=title, artist="YouTube")

    except Exception as e:
        print(f'播放錯誤: {e}')
        await play_next(ctx)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    await bot.tree.sync()
    print("✅ Slash commands synced.")
    bot.loop.create_task(check_idle())

    async def status_update_loop():
        await bot.wait_until_ready()
        while not bot.is_closed():
            for guild_id in list(status_messages.keys()):
                await update_status_embed(guild_id)
            await asyncio.sleep(1)
    bot.loop.create_task(status_update_loop())

@bot.tree.command(name="join", description="讓機器人加入你的語音頻道")
async def join(interaction: discord.Interaction):
    if interaction.user.voice and interaction.user.voice.channel:
        channel = interaction.user.voice.channel
        await channel.connect()
        await interaction.response.send_message("✅ 已加入語音頻道", ephemeral=True)
    else:
        await interaction.response.send_message("❌ 你不在語音頻道！", ephemeral=True)

@bot.tree.command(name="leave", description="讓機器人離開語音頻道")
async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        guild_id = interaction.guild.id
        queues.pop(guild_id, None)
        last_play_times.pop(guild_id, None)
        empty_times.pop(guild_id, None)
        status_messages.pop(guild_id, None)
        playing_info.pop(guild_id, None)
        await update_bot_presence()
        await interaction.response.send_message("👋 已離開語音頻道", ephemeral=True)
    else:
        await interaction.response.send_message("❌ 我不在語音頻道", ephemeral=True)


@bot.tree.command(name="play", description="播放 YouTube 音樂")
@app_commands.describe(url="YouTube 影片網址、關鍵字")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True)

    voice_client = interaction.guild.voice_client
    if not voice_client:
        if interaction.user.voice and interaction.user.voice.channel:
            channel = interaction.user.voice.channel
            voice_client = await channel.connect()
        else:
            await interaction.followup.send("❌ 你不在語音頻道！", ephemeral=True)
            return

    guild_id = interaction.guild.id
    queue = get_queue(guild_id)

    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)

            # 判斷是否是播放清單
            if 'entries' in info:
                count = 0
                for entry in info['entries']:
                    if entry is None:
                        continue
                    title = entry.get('title', '未知')
                    video_url = entry.get('webpage_url')
                    if video_url:
                        queue.append({'url': video_url, 'title': title})
                        count += 1
                if count == 0:
                    await interaction.followup.send("❌ 播放清單中找不到有效影片", ephemeral=True)
                    return
                await interaction.followup.send(f"🎶 已加入播放清單，共 {count} 首歌曲", ephemeral=True)
            else:
                title = info.get('title', '未知')
                video_url = info.get('webpage_url')
                queue.append({'url': video_url, 'title': title})
                await interaction.followup.send(f"🎶 已加入佇列: **{title}**", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ 取得音樂資訊失敗：{e}", ephemeral=True)
        return

    if not voice_client.is_playing():
        await play_next(interaction)

    await update_last_play_time(guild_id)

@bot.tree.command(name="pause", description="暫停")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        playing_info[interaction.guild.id]['paused_at'] = time.time()
        await interaction.response.send_message("⏸ 已暫停播放", ephemeral=True)
        # 更新狀態列顯示暫停中
        await update_status_embed(interaction.guild.id)
    else:
        await interaction.response.send_message("❌ 沒有正在播放的音樂", ephemeral=True)

@bot.tree.command(name="resume", description="繼續")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        paused_duration = time.time() - playing_info[interaction.guild.id].get('paused_at', time.time())
        playing_info[interaction.guild.id]['paused_time'] = playing_info[interaction.guild.id].get('paused_time', 0) + paused_duration
        vc.resume()
        await interaction.response.send_message("▶️ 已繼續播放", ephemeral=True)
        # 更新狀態列顯示播放中
        await update_status_embed(interaction.guild.id)
    else:
        await interaction.response.send_message("❌ 音樂沒有被暫停", ephemeral=True)

@bot.tree.command(name="stop", description="停止播放並離開語音頻道")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
        guild_id = interaction.guild.id
        queues.pop(guild_id, None)
        last_play_times.pop(guild_id, None)
        empty_times.pop(guild_id, None)
        status_messages.pop(guild_id, None)
        playing_info.pop(guild_id, None)
        await update_bot_presence()
        await interaction.response.send_message("🛑 已停止播放並離開語音頻道", ephemeral=True)
    else:
        await interaction.response.send_message("❌ 我不在語音頻道", ephemeral=True)

@bot.tree.command(name="skip", description="跳過當前歌曲")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()  # 會觸發 play_next
        await interaction.response.send_message("⏭ 已跳過當前歌曲", ephemeral=True)
    else:
        await interaction.response.send_message("❌ 沒有正在播放的音樂", ephemeral=True)

@bot.tree.command(name="queue", description="顯示待播放佇列")
async def queue_cmd(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)
    if not queue:
        await interaction.response.send_message("📭 待播放佇列是空的", ephemeral=True)
        return
    msg = "📃 待播放佇列：\n"
    for i, song in enumerate(queue, start=1):
        msg += f"{i}. {song['title']}\n"
    await interaction.response.send_message(msg, ephemeral=True)

# 你的 Discord Token (請自行替換成你的 Token)
TOKEN = "ur-token-key"

bot.run(TOKEN)
