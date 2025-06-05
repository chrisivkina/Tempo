import os
import importlib
import sys
import asyncio
import sqlite3
import discord
import random
import numpy as np
import json


def load_settings(version):
    # create the database if it doesn't already exist
    with sqlite3.connect("tempo.db") as db:
        cursor = db.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, data TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS DBInfo (version TEXT)")
        # set version if databse was just created (first run)
        cursor.execute("SELECT * FROM DBInfo")
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO DBInfo(version) VALUES (?)", (version,))
        else:
            pass  # handle version updates here
        db.commit()
        default = {
            "UpdateDM": True,
            "Default": "youtube",
            "Key": None,
            "Voice": False
        }
        cursor.execute("INSERT OR IGNORE INTO users (id, data) VALUES (?, ?)", (0, json.dumps(default)))
        rows = cursor.execute("SELECT * FROM users WHERE id=?", (0,)).fetchall()
        return json.loads(rows[0][1])


def getuserbackend(id):
    userdata = getuserdata(id)
    platform = userdata["platform"]
    if platform == "default":
        settings = load_settings(None)
        platform = settings["Default"]
        key = settings["Key"]
    else:
        key = userdata["keys"].get(platform)
    return platform, key


def getuserdata(id):
    with sqlite3.connect("tempo.db") as db:
        cursor = db.cursor()
        rows = cursor.execute("SELECT * FROM users WHERE id=?", (id,)).fetchall()
        if rows:
            return json.loads(rows[0][1])
        else:
            default = {
                "platform": "default",
                "keys": {"youtube": None}
            }
            cursor.execute("INSERT INTO users (id, data) VALUES (?, ?)", (id, json.dumps(default)))
            return default


def saveuserdata(id, data):
    with sqlite3.connect("tempo.db") as db:
        cursor = db.cursor()
        cursor.execute("UPDATE users SET data=? WHERE id=?", (json.dumps(data), id))
        db.commit()


def setuserplatform(id, platform):
    userdata = getuserdata(id)
    if platform not in userdata["keys"] and platform != "default":
        return False
    userdata["platform"] = platform
    saveuserdata(id, userdata)
    return True


def setuserkey(id, platform, key):
    userdata = getuserdata(id)
    userdata["keys"][platform] = key
    saveuserdata(id, userdata)


def rmuserkey(id, platform):
    userdata = getuserdata(id)
    userdata["keys"][platform] = None
    if platform == userdata["platform"]:
        userdata["platform"] = "youtube"
    saveuserdata(id, userdata)


def getuserkey(id, platform):
    userdata = getuserdata(id)
    return userdata["keys"][platform]


def import_backends(backends_folder: str):
    """Imports all valid backends from the Backends folder and returns a dictionary of them."""
    backends = {}

    sys.path.append(backends_folder)

    backend_files = [file for file in os.listdir(backends_folder) if file.endswith(".py") and file != "verify.py"]
    verify = importlib.import_module("verify", "Backends/Music/verify.py")
    for file in backend_files:
        module_name = os.path.splitext(file)[0]
        try:
            module = importlib.import_module(module_name)
            backendtype = verify.verify(module)
            if backendtype != 0:
                backends[module_name] = module
                backends[module_name].type = backendtype
            else:
                print(f"Failed to import backend {module_name}: Backend is missing 1 or more required functions.")
                continue
        except ImportError as e:
            print(f"Failed to import backend {module_name}: {e}")

    return backends


class Song:
    def __init__(self, user, title, author, backend, length, url):
        self.user = user
        self.title = title
        self.author = author
        self.backend = backend
        self.length = length
        self.url = url


class Playlist:
    def __init__(self, title: str, entries: list):
        self.title = title
        self.entries = [[i, entry] for i, entry in enumerate(entries)]
        self.shuffle = False
        self.loop = 0  # 0 is off, 1 is full queue, 2 is song

    def __len__(self):
        return len(self.entries)

    def delete(self, index):
        self.entries.pop(index)

    def add(self, entry):
        self.entries.append([max([i[0] for i in self.entries]) + 1 if len(self.entries) > 0 else 0, entry])

    def move(self, index, newindex):
        self.entries.insert(newindex, self.entries.pop(index))

    def GetCurrentEntry(self):
        return self.entries[0][1]

    def next(self):
        if self.loop == 1:
            self.entries.append(self.entries[0])
        if len(self.entries) > 0 and self.loop != 2:
            self.entries.pop(0)

    def getAll(self):
        return [entry[1] for entry in self.entries]

    def SetShuffle(self, mode: bool):
        if not self.shuffle and mode == True:
            currentsong = self.entries.pop(0)
            random.shuffle(self.entries)
            self.entries.insert(0, currentsong)
        if mode == False:
            currentsong = self.entries.pop(0)
            self.entries.sort()
            self.entries.insert(0, currentsong)

    def SetLoop(self, mode: int):
        if mode not in [0, 1, 2]:
            raise ValueError("Loop mode must be [0,1,2]")
        self.loop = mode


class MusicPlayer:
    def __init__(self, backends, voice: bool = False):
        self.playlist = Playlist("queue", [])
        self.vc = None
        self.active = False
        self.backends = backends
        self.mixer = Mixer()
        self._voice = voice
        self._commands = ["play", "resume", "pause", "stop"]
        self._is_listening = False
        self._results = []
        self._skip = False
        self._paused = False
        self._stop = False
        self._timeout_task = None
        self._empty_channel_task = None

    async def check_voice_connection(self, guild):
        """
        Checks if the bot is actually connected to a voice channel and updates state if needed.
        Returns True if connected, False if not.
        """
        # Check if we have a voice client for this guild
        voice_client = guild.voice_client
        
        # Case 1: We think we're connected but Discord says we're not
        if self.active and (voice_client is None or not voice_client.is_connected()):
            print(f"Bot thinks it's connected but actually isn't. Resetting state.")
            self.vc = None
            self.active = False
            if self._empty_channel_task:
                self._empty_channel_task.cancel()
                self._empty_channel_task = None
            return False
        
        # Case 2: We have a voice client but our internal reference is wrong
        if voice_client and voice_client.is_connected() and self.vc != voice_client:
            print(f"Updating voice client reference")
            self.vc = voice_client
            return True
        
        # Return connection status
        return self.vc is not None and voice_client is not None and voice_client.is_connected()

    async def _play(self):
        self.active = True
        
        # Start monitoring for empty voice channel
        if self._empty_channel_task is None and self.vc is not None:
            self._empty_channel_task = asyncio.create_task(self._monitor_voice_channel())
            
        while len(self.playlist) > 0:
            song = self.playlist.GetCurrentEntry()
            stream = await self.backends[song.backend].getstream(song.url, song.user.id)
            self.mixer.set_source1(stream)
            self.vc.play(self.mixer)
            while self.vc.is_playing() or self.mixer.is_paused():
                if self._stop:
                    self.mixer.stop()
                    self._stop = False

                if self._skip:
                    self.mixer.stop()
                    self._skip = False

                if self._paused:
                    if not self.mixer.is_paused():
                        self.mixer.pause()
                else:
                    if self.mixer.is_paused():
                        self.mixer.resume()

                await asyncio.sleep(0.1)

            self.playlist.next()

        # Queue is empty, start timeout for disconnection
        self._start_timeout()  
        self.active = False

    async def join_channel(self, vc: discord.VoiceChannel):
        self.vc = await vc.connect()
        
        # Start monitoring for empty voice channel
        if self._empty_channel_task is None:
            self._empty_channel_task = asyncio.create_task(self._monitor_voice_channel())
            
        if self._timeout_task:
            self._timeout_task.cancel()

    async def leave_channel(self):
        if self.vc:
            await self.vc.disconnect()
            self.vc = None
        if self._timeout_task:
            self._timeout_task.cancel()
        if self._empty_channel_task:
            self._empty_channel_task.cancel()
            self._empty_channel_task = None

    def add_song(self, song: Song):
        self.playlist.add(song)
        if self._timeout_task:
            self._timeout_task.cancel()

    def play(self):
        if self.vc is not None:
            if not self.active:
                asyncio.create_task(self._play())
            else:
                raise RuntimeError("MusicPlayer.play() cannot be run twice concurrently.")
        else:
            raise RuntimeError("MusicPlayer must be bound to a vc to play.")

    def pause(self):
        if self.active:
            self._paused = True
        else:
            raise RuntimeError("Nothing is playing.")

    def resume(self):
        if self.active:
            self._paused = False
        else:
            raise RuntimeError("Nothing is playing.")

    def stop(self):
        self.playlist = Playlist("queue", [])
        self._stop = True

    def getQueue(self):
        entries = self.playlist.getAll()
        return [[entry.title, entry.author, entry.length] for entry in entries]

    def skip(self):
        self._skip = True

    def _start_timeout(self):
        if self._timeout_task:
            self._timeout_task.cancel()
        self._timeout_task = asyncio.create_task(self._timeout())

    async def _timeout(self):
        await asyncio.sleep(60)  # Wait for 1 minute
        if self.vc and not self.vc.is_playing():
            await self.leave_channel()
            
    async def _monitor_voice_channel(self):
        """Monitors the voice channel and disconnects if empty for 1 minute."""
        empty_since = None
        
        while self.vc and self.vc.is_connected():
            # Check if channel is empty (only the bot is there)
            if self.vc.channel and len(self.vc.channel.members) <= 1:
                # Channel is empty or only has the bot
                if empty_since is None:
                    empty_since = asyncio.get_event_loop().time()
                    print(f"Voice channel is empty, starting 1-minute countdown")
                
                # Check if it's been empty for more than 60 seconds
                if asyncio.get_event_loop().time() - empty_since >= 60:
                    print(f"Voice channel has been empty for 1 minute, disconnecting")
                    self.stop()  # Stop the current playlist
                    await self.leave_channel()
                    break
            else:
                # Channel has users, reset the timer
                if empty_since is not None:
                    print(f"Users have rejoined the voice channel")
                    empty_since = None
            
            await asyncio.sleep(5)  # Check every 5 seconds


def overlay_audio(audio1_bytes, audio2_bytes, sample_width=2, num_channels=2, sample_rate=48000,
                  volume: int = 0.3):
    # Number of samples per 20ms for stereo audio
    num_samples = int(0.02 * sample_rate * num_channels)

    # Convert bytes-like objects to numpy arrays
    audio1 = np.frombuffer(audio1_bytes, dtype=np.int16).reshape(-1, num_channels).copy().astype(float)
    audio2 = np.frombuffer(audio2_bytes, dtype=np.int16).reshape(-1, num_channels)

    # lower audio so you can hear the DJ
    audio1 *= volume

    # Ensure both audio samples have the same length
    min_length = min(len(audio1), len(audio2))
    audio1 = audio1[:min_length]
    audio2 = audio2[:min_length]

    # Overlay the audio by summing the samples
    combined_audio = audio1 + audio2

    # Prevent clipping by scaling the combined audio
    max_val = np.iinfo(np.int16).max
    min_val = np.iinfo(np.int16).min
    combined_audio = np.clip(combined_audio, min_val, max_val)

    # Convert the combined audio back to bytes
    combined_audio_bytes = combined_audio.astype(np.int16).tobytes()

    return combined_audio_bytes


class Mixer(discord.AudioSource):
    def __init__(self, source1: discord.AudioSource = None, source2: discord.AudioSource = None):
        self.source1 = source1
        self.source2 = source2
        self._paused = False

    def read(self):
        if self.source1 is not None and self._paused == False:
            a = self.source1.read()
        else:
            a = None

        if self.source2 is not None:
            b = self.source2.read()
        else:
            b = None

        if a and b:
            return overlay_audio(a, b)
        elif a:
            return a
        elif b:
            return b
        else:
            return b''

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self.source1 = None

    def is_paused(self):
        return self._paused

    def set_source1(self, new_source: discord.AudioSource):
        # Set the new source1
        self.source1 = new_source

    def set_source2(self, new_source: discord.AudioSource):
        # Set the new source1
        self.source2 = new_source


class BytesAudioSource(discord.AudioSource):
    def __init__(self, byte_io):
        self.byte_io = byte_io

    def read(self):
        # Read 20ms worth of audio (3840 bytes)
        return self.byte_io.read(3840)

    def cleanup(self):
        # Cleanup when the source is no longer needed
        self.byte_io.close()


def _classify_and_extract_song(text):
    # Define the possible commands and their corresponding keywords
    commands = {"play": ["play", "play song"],
                "stop": ["stop"],
                "pause": ["pause"],
                "resume": ["resume"]}

    # Initialize song name as None
    song_name = None

    # Classify the input text
    for command, keywords in commands.items():
        if any(keyword in text.lower() for keyword in keywords):
            if command == "play":
                # Split the text to separate the song name from the "play" command
                words = text.split()
                if len(words) > 1:
                    song_name = ' '.join(words[1:])
            return command, song_name

    return None, None


class TextAssistant:
    def __init__(self):
        pass

    @staticmethod
    def run(text):
        return _classify_and_extract_song(text)
