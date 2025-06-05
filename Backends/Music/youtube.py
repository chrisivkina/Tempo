import sys
import os
import asyncio
import discord
import libTempo
import yt_dlp as youtube_dl
import re

# Add the parent directory to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def search(query: str, user: discord.User, count: int = 3, key=None):
    # Check if the query is a YouTube playlist
    is_playlist = False
    if 'youtube.com' in query and ('playlist?list=' in query or '&list=' in query):
        is_playlist = True
        count = 50  # Increase limit for playlists, modify as needed
    
    ydl_opts = {
        'format': 'bestaudio',
        'default_search': 'ytsearch',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': not is_playlist,  # Only process playlists when intended
        'extract_flat': 'in_playlist' if is_playlist else True,  # Better playlist extraction
        'skip_download': True,
        'ignoreerrors': True,
        'noprogress': True,
        'nopart': True,
        'max_downloads': count,
        'youtube_include_dash_manifest': False,
        'cachedir': False,
        'geo_bypass': True,
        'socket_timeout': 5,  # Reduced timeout for faster response
        'extractor_retries': 2,  # Slightly more retries for playlists
        'nocheckcertificate': True,
        'no_color': True,  # Disable colored output
    }

    loop = asyncio.get_event_loop()
    search_query = query if is_playlist else f"ytsearch{count}:{query}"
    
    try:
        print(f"Searching for: {search_query}")
        print(f"Playlist mode: {is_playlist}")
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            search_results = await loop.run_in_executor(
                None, 
                lambda: ydl.extract_info(search_query, download=False)
            )
        
        if not search_results:
            print(f"No search results found")
            return []
            
        # print(f"Found search results with keys: {list(search_results.keys())}")
        # if 'entries' in search_results:
            print(f"Found {len(search_results['entries'])} entries")
            
        results = []
        if search_results:
            # For playlists, handle entries differently
            if is_playlist and 'entries' in search_results:
                playlist_title = search_results.get('title', 'Unknown Playlist')
                # print(f"Processing playlist: {playlist_title}")
                
                # Process each entry in the playlist
                for result in search_results['entries']:
                    if not result:  # Skip if no result
                        continue
                    
                    # Debug the playlist entry
                    # print(f"Entry keys: {list(result.keys()) if result else 'No result'}")
                        
                    # Ensure we always have a valid YouTube URL
                    if result.get('id'):
                        url = f"https://www.youtube.com/watch?v={result['id']}"
                    elif result.get('url'):
                        url = result.get('url')
                    else:
                        # Skip if we can't construct a valid URL
                        print(f"Skipping entry without ID or URL")
                        continue
                    
                    song = libTempo.Song(
                        user,
                        result.get('title', 'Unknown Title'),
                        result.get('uploader', result.get('channel', 'Unknown Channel')),
                        "youtube",
                        result.get('duration', 0),
                        url
                    )
                    
                    # Add the playlist flag to each song for queue display
                    song.is_playlist = True
                    song.playlist_title = playlist_title
                    
                    results.append(song)
                
                # For playlists, add playlist data to the first song for later use
                if results:
                    results[0].playlist_count = len(results)
                    print(f"Successfully processed {len(results)} songs from playlist")
                else:
                    print("No valid entries found in playlist")
            
            # Regular search results handling
            elif not is_playlist and 'entries' in search_results:
                for result in search_results['entries'][:count]:
                    if not result:  # Skip if no result
                        continue
                        
                    # Ensure we always have a valid YouTube URL
                    if result.get('id'):
                        url = f"https://www.youtube.com/watch?v={result['id']}"
                    else:
                        # Skip if we can't construct a valid URL
                        continue
                    
                    results.append(libTempo.Song(
                        user,
                        result.get('title', 'Unknown Title'),
                        result.get('uploader', result.get('channel', 'Unknown Channel')),
                        "youtube",
                        result.get('duration', 0),
                        url
                    ))
        return results
    except Exception as e:
        print(f"Error searching YouTube: {e}")
        import traceback
        traceback.print_exc()
        return []


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        youtube_dl.utils.bug_reports_message = lambda: ''
        ydl_opts = {
            'format': 'bestaudio/best',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': None,  # Disable search functionality in streaming
            'source_address': '0.0.0.0',
            'socket_timeout': 10,
            'extractor_retries': 3,  # More retries for actual playback
            'geo_bypass': True
        }
        ffmpeg_options = {
            'options': '-vn',
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        }
        
        ytdl = youtube_dl.YoutubeDL(ydl_opts)
        loop = loop or asyncio.get_event_loop()
        
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
            if not data:
                raise ValueError(f"Could not extract info from {url}")
                
            if 'entries' in data:
                # Take first item from a playlist
                data = data['entries'][0]

            filename = data['url'] if stream else ytdl.prepare_filename(data)
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
        except Exception as e:
            print(f"Error streaming YouTube: {e}")
            raise


async def getstream(url: str, user: discord.User = None):
    # Always ensure we have a proper YouTube URL format
    if not url.startswith('https://www.youtube.com/watch?v='):
        # Extract video ID if possible
        import re
        # Match both v= format and direct video IDs
        match = re.search(r'(?:v=|youtu\.be/|ytsearch.*?)([a-zA-Z0-9_-]{11})', url)
        if match:
            url = f"https://www.youtube.com/watch?v={match.group(1)}"
        else:
            raise ValueError(f"Invalid YouTube URL format: {url}")
    
    return await YTDLSource.from_url(url, loop=asyncio.get_event_loop(), stream=True)


def auth(username, key):
    return ""
