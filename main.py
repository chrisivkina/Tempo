import os
import libTempo
import discord
import dotenv
from discord.ext import commands
from embedbuilder import EmbedBuilder

version = "0.1"
DO_USE_FIRST_SEARCH_RESULT = True
DELETE_AFTER_TIME = 60
QUEUE_ITEMS_PER_PAGE = 20

# set intents
intents = discord.Intents.default()

# make the bot
bot = discord.Bot(intents=intents, activity=discord.Activity(type=discord.ActivityType.competing, name='drinking games'))
# bot = discord.Bot(intents=intents, activity=discord.Game(name='Deadly Indian Truck Driving'))
bot.settings = libTempo.load_settings(version)
bot.backends = libTempo.import_backends("Backends/Music")

# update checks
bot.ownerupdated = True
guilds = [718056560793747497, 1169287713887887442]


@bot.event
async def on_ready():
    print(f"{bot.user} is online.")
    bot.owner_id = 289432006134202390
    bot.players = {}
    for guild in bot.guilds:
        bot.players[guild.id] = libTempo.MusicPlayer(bot.backends, bot.settings["Voice"])


def is_owner():
    async def predicate(ctx):
        return ctx.author.id == bot.owner_id
    return commands.check(predicate)


@bot.slash_command(name='play', description='plays a song or playlist', guild_ids=guilds)
async def play(interaction: discord.Interaction, song: str, platform: str = None):
    # Check if the user is in a voice channel
    try:
        channel = interaction.user.voice.channel
    except:
        await interaction.response.send_message("You are not currently in a voice channel.", delete_after=DELETE_AFTER_TIME)
        return

    # Check if the bot has permissions to join and speak in the voice channel
    permissions = channel.permissions_for(interaction.guild.me)
    if not permissions.connect or not permissions.speak:
        await interaction.response.send_message("I do not have permission to play music in that voice channel.", delete_after=DELETE_AFTER_TIME)
        return

    # Check if the user is authorized to use the platform
    userbackends = libTempo.getuserdata(interaction.user.id)
    if platform is not None and platform not in userbackends["keys"] and platform != "default":
        await interaction.response.send_message("You are not authorized to use that platform.", delete_after=DELETE_AFTER_TIME)
        return

    # Send a searching message
    await interaction.response.send_message("Searching...", delete_after=DELETE_AFTER_TIME)

    # Get the user's preferred platform
    if platform is None or platform == "default":
        userbackend = libTempo.getuserbackend(interaction.user.id)
    else:
        userbackend = [platform, libTempo.getuserkey(interaction.user.id, platform)]

    result = await bot.backends[userbackend[0]].search(song, interaction.user, key=userbackend[1])

    if len(result) == 0:
        await interaction.followup.send(content="No results found.", delete_after=DELETE_AFTER_TIME)
        return

    # Check if this is a playlist result
    is_playlist = False
    if len(result) > 0 and hasattr(result[0], 'is_playlist') and result[0].is_playlist:
        is_playlist = True
        playlist_title = getattr(result[0], 'playlist_title', 'Unknown Playlist')
        playlist_count = getattr(result[0], 'playlist_count', len(result))

    if is_playlist or len(result) == 1 or DO_USE_FIRST_SEARCH_RESULT:
        # Check if the bot is actually connected to voice - if not, reset state
        connection_status = await bot.players[interaction.guild.id].check_voice_connection(interaction.guild)
        
        # Connect to voice channel if not connected or reconnect if kicked
        if not connection_status:
            try:
                print(f"Bot needs to (re)connect to voice channel")
                await bot.players[interaction.guild.id].join_channel(interaction.user.voice.channel)
            except Exception as e:
                print(f"Failed to join voice channel: {e}")
                await interaction.followup.send(
                    content="Failed to join your voice channel. I may not have the proper permissions.", 
                    delete_after=DELETE_AFTER_TIME)
                return
                
        if is_playlist:
            # For playlists, add all songs to the queue
            first_song_title = result[0].title
            first_song_added = False
            
            for song in result:
                bot.players[interaction.guild.id].add_song(song)
                if not first_song_added:
                    first_song_added = True
            
            # Use the modular embed builder for playlist added message
            is_playing = len(bot.players[interaction.guild.id].playlist) == playlist_count
            embed = EmbedBuilder.build_playlist_added_embed(
                playlist_title,
                playlist_count,
                first_song_title,
                is_playing
            )
            
            # Start playing if not already
            if is_playing:  # If queue was empty before
                bot.players[interaction.guild.id].play()
                
            await interaction.followup.send(embed=embed, delete_after=DELETE_AFTER_TIME)
        else:
            # Single song handling with beautiful embeds
            option = result[0]
            bot.players[interaction.guild.id].add_song(option)
            
            if len(bot.players[interaction.guild.id].playlist) == 1:
                # Song will play immediately
                embed = EmbedBuilder.build_song_playing_embed(option)
                bot.players[interaction.guild.id].play()
            else:
                # Song added to queue
                position_in_queue = len(bot.players[interaction.guild.id].playlist)
                embed = EmbedBuilder.build_song_added_embed(option, position_in_queue)
            
            await interaction.followup.send(embed=embed, delete_after=DELETE_AFTER_TIME)


# view class to select the correct song.
class PlaySelectListView(discord.ui.View):
    def __init__(self, *, timeout=180, options: dict, interaction: discord.Interaction, results: list):
        super().__init__(timeout=timeout)
        self.add_item(PlaySelectSong(option=options, interaction=interaction, results=results))


class PlaySelectSong(discord.ui.Select):
    def __init__(self, option: dict, interaction: discord.Interaction, results: list):
        self.results = results
        self.original_interaction = interaction
        super().__init__(placeholder="Select an option", options=option)

    # Update the PlaySelectSong callback method
    async def callback(self, interaction: discord.Interaction):
        selection = int(self.values[0].split(") ")[0]) - 1
        option = self.results[selection]
        if not bot.players[interaction.guild.id].active:
            try:
                await bot.players[interaction.guild.id].join_channel(self.original_interaction.user.voice.channel)
            except:
                await self.original_interaction.followup.send(
                    content="You are not currently in a voice channel.", delete_after=DELETE_AFTER_TIME)
                return
                
        bot.players[interaction.guild.id].add_song(option)
        
        if len(bot.players[interaction.guild.id].playlist) == 1:
            # Song will play immediately
            embed = EmbedBuilder.build_song_playing_embed(option)
            bot.players[interaction.guild.id].play()
        else:
            # Song added to queue
            position_in_queue = len(bot.players[interaction.guild.id].playlist)
            embed = EmbedBuilder.build_song_added_embed(option, position_in_queue)
        
        await self.original_interaction.followup.send(embed=embed, delete_after=DELETE_AFTER_TIME)
        await interaction.response.defer()


class QueuePaginationView(discord.ui.View):
    def __init__(self, entries, player, timeout=180):
        super().__init__(timeout=timeout)
        self.entries = entries
        self.player = player
        self.current_page = 0
        
        # Reserve space for metadata fields (3 fields: playback, duration, count)
        self.reserved_fields = 3
        self.items_per_page = QUEUE_ITEMS_PER_PAGE - self.reserved_fields
        
        # Calculate total pages based on available song fields
        self.total_pages = max(1, (len(entries) + self.items_per_page - 1) // self.items_per_page)
        
        # We'll update button states after they're created in the methods below
    
    def update_buttons(self):
        # Disable previous button on first page
        self.previous_button.disabled = (self.current_page == 0)
        # Disable next button on last page
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
    
    async def update_embed(self, interaction):
        # Create a new embed for the current page
        embed = EmbedBuilder.build_queue_embed(
            self.entries,
            self.player,
            page=self.current_page,
            items_per_page=QUEUE_ITEMS_PER_PAGE  # This now handles the reserved fields internally
        )
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await self.update_embed(interaction)
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await self.update_embed(interaction)
            

@bot.slash_command(name='stop', description='Stops the current session', guild_ids=guilds)
async def stop(interaction: discord.Interaction):
    if not bot.players[interaction.guild.id].active:
        await interaction.response.send_message("There is nothing to stop.", delete_after=DELETE_AFTER_TIME)
        return
    bot.players[interaction.guild.id].stop()
    await interaction.response.send_message("Session stopped.", delete_after=DELETE_AFTER_TIME)


@bot.slash_command(name='pause', description='Pauses the current song', guild_ids=guilds)
async def pause(interaction: discord.Interaction):
    if not bot.players[interaction.guild.id].active:
        await interaction.response.send_message("There is nothing to pause.", delete_after=DELETE_AFTER_TIME)
        return
    bot.players[interaction.guild.id].pause()
    await interaction.response.send_message(
        f"Paused {bot.players[interaction.guild.id].playlist.GetCurrentEntry().title}.", delete_after=DELETE_AFTER_TIME)


@bot.slash_command(name='resume', description='Resumes the current song', guild_ids=guilds)
async def resume(interaction: discord.Interaction):
    if not bot.players[interaction.guild.id].active:
        await interaction.response.send_message("There is nothing to resume.", delete_after=DELETE_AFTER_TIME)
        return
    bot.players[interaction.guild.id].resume()
    await interaction.response.send_message(
        f"Resumed {bot.players[interaction.guild.id].playlist.GetCurrentEntry().title}.", delete_after=DELETE_AFTER_TIME)


@bot.slash_command(name='skip', description='Skips the current song', guild_ids=guilds)
async def skip(interaction: discord.Interaction):
    if not bot.players[interaction.guild.id].active:
        await interaction.response.send_message("There is nothing to skip.", delete_after=DELETE_AFTER_TIME)
        return
    title = bot.players[interaction.guild.id].playlist.GetCurrentEntry().title
    bot.players[interaction.guild.id].skip()
    await interaction.response.send_message(f"Skipped {title}.", delete_after=DELETE_AFTER_TIME)

@bot.slash_command(name='queue', description='Shows the Queue', guild_ids=guilds)
async def queue(interaction: discord.Interaction):
    player = bot.players[interaction.guild.id]
    
    if len(player.playlist) == 0:
        error_embed = EmbedBuilder.build_error_embed("There is no music in the queue.")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    entries = player.getQueue()
    
    # Reserve fields for metadata
    max_song_fields = QUEUE_ITEMS_PER_PAGE - 3  # 3 fields reserved for metadata
    
    # If queue is small, just show a single embed without pagination
    if len(entries) <= max_song_fields:
        embed = EmbedBuilder.build_queue_embed(entries, player)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        # For larger queues, create paginated view
        view = QueuePaginationView(entries, player)
        embed = EmbedBuilder.build_queue_embed(
            entries, 
            player,
            page=0, 
            items_per_page=QUEUE_ITEMS_PER_PAGE
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.slash_command(name='shuffle', description='Toggles shuffle mode.', guild_ids=guilds)
async def shuffle(interaction: discord.Interaction):
    current_mode = bot.players[interaction.guild.id].playlist.shuffle
    new_mode = not current_mode  # Toggle between True and False
    bot.players[interaction.guild.id].playlist.SetShuffle(new_mode)
    await interaction.response.send_message(f"Shuffle mode {'enabled' if new_mode else 'disabled'}.", delete_after=DELETE_AFTER_TIME)


@bot.slash_command(name='loop', description='Toggles loop mode.', guild_ids=guilds)
async def loop(interaction: discord.Interaction):
    current_mode = bot.players[interaction.guild.id].playlist.loop
    new_mode = (current_mode + 1) % 3  # Toggle between 0, 1, and 2
    bot.players[interaction.guild.id].playlist.SetLoop(new_mode)
    mode_names = ["off", "queue", "song"]
    await interaction.response.send_message(f"Loop mode set to {mode_names[new_mode]}.", delete_after=DELETE_AFTER_TIME)


@bot.slash_command(name='auth', description='Authorizes user for a platform', guild_ids=guilds)
@is_owner()
async def auth(interaction: discord.Interaction, platform: str, username: str, key: str):
    if platform not in bot.backends:
        await interaction.response.send_message("Invalid platform.", ephemeral=True, delete_after=DELETE_AFTER_TIME)
        return
    key = bot.backends[platform].auth(username, key)
    if key == None:
        await interaction.response.send_message("Invalid credentials.", ephemeral=True, delete_after=DELETE_AFTER_TIME)
        return
    libTempo.setuserkey(interaction.user.id, platform, key)
    await interaction.response.send_message(f"Authorized {platform} account.", ephemeral=True, delete_after=DELETE_AFTER_TIME)


@bot.slash_command(name='deauth', description='Deauthorizes user for a platform', guild_ids=guilds)
@is_owner()
async def deauth(interaction: discord.Interaction, platform: str):
    if platform not in bot.backends:
        await interaction.response.send_message("Invalid platform.", delete_after=DELETE_AFTER_TIME, ephemeral=True)
        return
    libTempo.rmuserkey(interaction.user.id, platform)
    await interaction.response.send_message(f"Deauthorized {platform} account.", ephemeral=True, delete_after=DELETE_AFTER_TIME)


@bot.slash_command(name='setplatform', description='sets a users preferred platform', guild_ids=guilds)
async def setplatform(interaction: discord.Interaction, platform: str):
    if platform not in bot.backends and platform != "default":
        await interaction.response.send_message("Invalid platform.", delete_after=DELETE_AFTER_TIME)
        return
    set = libTempo.setuserplatform(interaction.user.id, platform)
    if set:
        await interaction.response.send_message(f"Set preferred platform to {platform}.", delete_after=DELETE_AFTER_TIME)
    else:
        await interaction.response.send_message(f"You do not have access to {platform}.", ephemeral=True, delete_after=DELETE_AFTER_TIME)


@bot.slash_command(name='settings', description='Shows the current settings', guild_ids=guilds)
@is_owner()
async def settings(interaction: discord.Interaction):
    embed = discord.Embed(title="Current Settings", color=0x00ff00)
    for key, value in bot.settings.items():
        if key not in ["Key"]:  # don't show the key
            embed.add_field(name=key, value=value, inline=False)
    await interaction.response.send_message(embed=embed, delete_after=DELETE_AFTER_TIME, ephemeral=True)


@bot.slash_command(name='setsetting', description='Sets a setting', guild_ids=guilds)
@is_owner()
async def setsetting(interaction: discord.Interaction, setting: str, value: str):
    if setting not in bot.settings or setting == "Key":
        await interaction.response.send_message("Invalid setting.", delete_after=DELETE_AFTER_TIME, ephemeral=True)
        return
    if setting.lower() == "voice":
        await interaction.response.send_message("Voice is currently disabled, wait for a future update to enable it.", delete_after=DELETE_AFTER_TIME, ephemeral=True)
        return
    try:
        if setting in ["Voice", "updateDM"]:
            value = bool(value)
    except:
        await interaction.response.send_message("Invalid value.", delete_after=DELETE_AFTER_TIME, ephemeral=True)
        return
    bot.settings[setting] = value
    settings = bot.settings
    settings[setting] = value
    libTempo.saveuserdata(0, settings)
    await interaction.response.send_message(f"Set {setting} to {value}. A restart is required to apply changes.", delete_after=DELETE_AFTER_TIME, ephemeral=True)


@bot.slash_command(name='move', description='moves songs in the queue', guild_ids=guilds)
async def move(interaction: discord.Interaction, start: int, end: int):
    if not bot.players[interaction.guild.id].active:
        await interaction.response.send_message("There is no music playing.", delete_after=DELETE_AFTER_TIME)
        return
    if start < 1 or end < 1 or start > len(bot.players[interaction.guild.id].playlist) or end > len(
            bot.players[interaction.guild.id].playlist):
        await interaction.response.send_message("Invalid position.", delete_after=DELETE_AFTER_TIME)
        return
    bot.players[interaction.guild.id].playlist.move(start - 1, end - 1)
    await interaction.response.send_message(f"Moved song from position {start} to {end}.", delete_after=DELETE_AFTER_TIME)


@bot.slash_command(name='playing', description='Shows the currently playing song', guild_ids=guilds)
async def playing(interaction: discord.Interaction):
    player = bot.players[interaction.guild.id]
    
    if not player.active:
        error_embed = EmbedBuilder.build_error_embed("There is no music playing.")
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return

    entry = player.playlist.GetCurrentEntry()
    embed = EmbedBuilder.build_now_playing_embed(entry, player)
    await interaction.response.send_message(embed=embed, ephemeral=True)


print("Starting...")
dotenv.load_dotenv()
token = os.environ['token']
bot.run(token)
