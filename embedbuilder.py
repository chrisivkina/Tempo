import discord
import re
from typing import List, Tuple, Union, Optional


class EmbedBuilder:
    """Modular utility class for building consistent Discord embeds across the application"""
    
    @classmethod
    def create_embed(cls, title=None, description=None, color=None, url=None) -> discord.Embed:
        """Creates a base embed with the specified properties"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            url=url
        )
        return embed
    
    @staticmethod
    def add_thumbnail(embed: discord.Embed, url: str) -> discord.Embed:
        """Adds a thumbnail to the embed"""
        embed.set_thumbnail(url=url)
        return embed
    
    @staticmethod
    def add_field(embed: discord.Embed, name: str, value: str, inline: bool = True) -> discord.Embed:
        """Adds a field to the embed"""
        embed.add_field(name=name, value=value, inline=inline)
        return embed
        
    @staticmethod
    def add_footer(embed: discord.Embed, text: str, icon_url: str = None) -> discord.Embed:
        """Adds a footer to the embed"""
        embed.set_footer(text=text, icon_url=icon_url)
        return embed
        
    @staticmethod
    def extract_youtube_thumbnail(url: str) -> Optional[str]:
        """Extracts a YouTube thumbnail URL from a video URL"""
        if "youtube.com" in url or "youtu.be" in url:
            match = re.search(r'(?:v=|youtu\.be\/|ytsearch.*?)([a-zA-Z0-9_-]{11})', url)
            if match:
                return f"https://img.youtube.com/vi/{match.group(1)}/mqdefault.jpg"
        return None
        
    @staticmethod
    def format_duration(seconds: Union[int, float, None]) -> str:
        """Formats seconds into a mm:ss string, handling None values"""
        if seconds is None:
            seconds = 0
        minutes, seconds = divmod(int(seconds), 60)
        return f"{minutes}:{seconds:02d}"
    
    # Factory methods that use the modular approach
    
    @classmethod
    def build_now_playing_embed(cls, entry, player) -> discord.Embed:
        """Creates a formatted embed for the currently playing song"""
        embed = cls.create_embed(
            title="🎵 Now Playing",
            description=f"**[{entry.title}]({entry.url})**",
            color=0x3498db
        )
        
        # Add song metadata
        cls.add_field(embed, "Artist", entry.author)
        
        # Format duration
        if entry.length > 0:
            duration = cls.format_duration(entry.length)
            cls.add_field(embed, "Duration", duration)
            
        # Add queue position
        queue_position = 1  # Current song is always position 1
        queue_length = len(player.playlist)
        cls.add_field(embed, "Queue Position", f"{queue_position}/{queue_length}")
        
        # Add player status
        play_status = "▶️ Playing"
        if hasattr(player, '_paused') and player._paused:
            play_status = "⏸️ Paused"
        cls.add_field(embed, "Status", play_status)
        
        # Add loop/shuffle status
        loop_mode = ["Off", "Queue", "Song"][player.playlist.loop]
        shuffle = 'On' if player.playlist.shuffle is not False else 'Off'
        cls.add_field(embed, "Playback Settings", f"Loop: {loop_mode} | Shuffle: {shuffle}")
        
        # Add requester info
        if hasattr(entry, 'user') and entry.user:
            cls.add_footer(
                embed,
                f"Requested by {entry.user.display_name}",
                entry.user.display_avatar.url if entry.user.display_avatar else None
            )
            
        # Add YouTube thumbnail
        thumbnail_url = cls.extract_youtube_thumbnail(entry.url)
        if thumbnail_url:
            cls.add_thumbnail(embed, thumbnail_url)
            
        return embed
        
    @classmethod
    def build_error_embed(cls, message: str) -> discord.Embed:
        """Creates a standardized error embed"""
        return cls.create_embed(
            title="❌ Error",
            description=message,
            color=0xff0000
        )

    @classmethod
    def build_playlist_added_embed(cls, playlist_title: str, song_count: int, first_song: str, is_playing: bool) -> discord.Embed:
        """Creates an embed for when a playlist is added to the queue"""
        embed = cls.create_embed(
            title="🎵 Playlist Added to Queue",
            description=f"**{playlist_title}**",
            color=0x3498db
        )
        
        cls.add_field(embed, "Songs", f"{song_count} songs added to queue")
        cls.add_field(embed, "First Song", first_song)
        cls.add_field(
            embed, 
            "Status", 
            "▶️ Now Playing" if is_playing else "Added to queue",
            inline=False
        )
        
        return embed
    
    @classmethod
    def build_song_playing_embed(cls, song) -> discord.Embed:
        """Creates an embed for when a single song starts playing immediately"""
        embed = cls.create_embed(
            title="▶️ Now Playing",
            description=f"**[{song.title}]({song.url})**",
            color=0x1DB954  # Spotify green color
        )
        
        # Add song metadata
        cls.add_field(embed, "Artist", song.author)
        
        # Format duration if available
        if song.length > 0:
            duration = cls.format_duration(song.length)
            cls.add_field(embed, "Duration", duration)
        
        # Add requester info
        if hasattr(song, 'user') and song.user:
            cls.add_footer(
                embed,
                f"Requested by {song.user.display_name}",
                song.user.display_avatar.url if song.user.display_avatar else None
            )
        
        # Add YouTube thumbnail
        thumbnail_url = cls.extract_youtube_thumbnail(song.url)
        if thumbnail_url:
            cls.add_thumbnail(embed, thumbnail_url)
        
        return embed

    @classmethod
    def build_song_added_embed(cls, song, position_in_queue) -> discord.Embed:
        """Creates an embed for when a song is added to the queue"""
        embed = cls.create_embed(
            title="🎵 Added to Queue",
            description=f"**[{song.title}]({song.url})**",
            color=0x3498db  # Blue color
        )
        
        # Add song metadata
        cls.add_field(embed, "Artist", song.author)
        
        # Format duration
        if song.length > 0:
            duration = cls.format_duration(song.length)
            cls.add_field(embed, "Duration", duration)
        
        # Add position in queue
        cls.add_field(embed, "Position in Queue", f"#{position_in_queue}")
        
        # Add requester info
        if hasattr(song, 'user') and song.user:
            cls.add_footer(
                embed,
                f"Requested by {song.user.display_name}",
                song.user.display_avatar.url if song.user.display_avatar else None
            )
        
        # Add YouTube thumbnail
        thumbnail_url = cls.extract_youtube_thumbnail(song.url)
        if thumbnail_url:
            cls.add_thumbnail(embed, thumbnail_url)
        
        return embed

    @classmethod
    def build_queue_embed(cls, entries: List[Tuple[str, str, int]], player, page=0, items_per_page=25) -> discord.Embed:
        """Creates a formatted embed for displaying the song queue, with pagination support"""
        # Reserve fields for metadata (playback settings, total duration, total songs)
        RESERVED_FIELDS = 3
        max_song_fields = items_per_page - RESERVED_FIELDS
        
        # Calculate total number of pages based on available song fields
        total_pages = max(1, (len(entries) + max_song_fields - 1) // max_song_fields)
        
        # Calculate start and end indices for current page
        start_idx = page * max_song_fields
        end_idx = min(start_idx + max_song_fields, len(entries))
        
        # Get entries for current page
        page_entries = entries[start_idx:end_idx]
        
        embed = cls.create_embed(
            title="🎶 Current Queue",
            description=f"Page {page + 1}/{total_pages}",
            color=0x00ff00
        )
        
        # Calculate total duration - handle None values by converting to 0
        total_duration = sum(duration or 0 for _, _, duration in entries)
        total_duration_str = cls.format_duration(total_duration)
        
        # Check if any songs have playlist information
        playlist_info_exists = False
        for index, item in enumerate(player.playlist.entries):
            song = item[1]
            if hasattr(song, 'is_playlist') and song.is_playlist and hasattr(song, 'playlist_title'):
                playlist_info_exists = True
                break
                
        # Add song details to the embed
        for i, (title, author, duration) in enumerate(page_entries):
            # Calculate the actual index in the full queue
            index = start_idx + i
            
            # Handle None durations
            duration_str = cls.format_duration(duration or 0)
            
            # Get original song object to check for playlist info
            playlist_badge = ""
            if playlist_info_exists and index < len(player.playlist.entries):
                song = player.playlist.entries[index][1]
                if hasattr(song, 'is_playlist') and song.is_playlist and hasattr(song, 'playlist_title'):
                    playlist_badge = f" [🎵 {song.playlist_title}]"
                    
            if index == 0:
                cls.add_field(
                    embed,
                    f"**{index + 1}. {title} [Now Playing]{playlist_badge}**",
                    f"By {author} | Duration: {duration_str}",
                    inline=False
                )
            else:
                cls.add_field(
                    embed,
                    f"**{index + 1}. {title}{playlist_badge}**",
                    f"By {author} | Duration: {duration_str}",
                    inline=False
                )
                    
        # Add playback settings
        cls.add_field(
            embed,
            "Playback Settings",
            f"🔀 Shuffle: {'On' if player.playlist.shuffle else 'Off'} | " +
            f"🔁 Loop: {['Off', 'Queue', 'Song'][player.playlist.loop]}",
            inline=False
        )
        
        # Add total duration
        cls.add_field(embed, "Total Duration", total_duration_str, inline=True)
        cls.add_field(embed, "Total Songs", str(len(entries)), inline=True)
        cls.add_footer(embed, f"Page {page + 1}/{total_pages} • {start_idx + 1}-{end_idx} of {len(entries)} songs")
        
        return embed
