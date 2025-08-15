import os
from dotenv import load_dotenv

import discord
from discord.ext import commands
import json
import os
import asyncio
from datetime import datetime, timedelta
import signal
import sys

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
USER_ID = os.getenv("USER_ID")
GAME_NAME = os.getenv("GAME_NAME")

# Configuration
CONFIG = {
    'TOKEN': os.getenv("BOT_TOKEN"),  # Replace with your bot token
    'TARGET_USER_ID': int(os.getenv("USER_ID")),  # Replace with your Discord user ID (as integer)
    'TARGET_GAME': os.getenv("GAME_NAME"),
    'DATA_FILE': 'bot_data.json',
    'GUILD_ID': os.getenv("GUILD_ID")  # Optional: Set to your server ID for faster command sync, or leave None for global commands
}

class CrabChampionsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.presences = True
        intents.members = True
        intents.message_content = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        self.data = {
            'global_counter': 0,
            'last_opened_time': None,
            'last_closed_time': None,
            'is_currently_playing': False
        }
        
        self.setup_signal_handlers()

    def setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        def signal_handler(signum, frame):
            print(f'\nReceived signal {signum}, shutting down gracefully...')
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def load_data(self):
        """Load bot data from file"""
        try:
            if os.path.exists(CONFIG['DATA_FILE']):
                with open(CONFIG['DATA_FILE'], 'r') as f:
                    loaded_data = json.load(f)
                    self.data.update(loaded_data)
                print('✅ Data loaded successfully')
            else:
                print('📄 No existing data file found, starting fresh')
        except Exception as e:
            print(f'❌ Error loading data: {e}')

    async def save_data(self):
        """Save bot data to file"""
        try:
            with open(CONFIG['DATA_FILE'], 'w') as f:
                json.dump(self.data, f, indent=2)
            print('💾 Data saved successfully')
        except Exception as e:
            print(f'❌ Error saving data: {e}')

    async def setup_hook(self):
        """Called when the bot is starting up"""
        await self.load_data()
        
        # Sync slash commands (either to specific guild or globally)
        try:
            if CONFIG['GUILD_ID']:
                # Sync to specific guild for faster updates during development
                guild = discord.Object(id=CONFIG['GUILD_ID'])
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f'✅ Synced {len(synced)} command(s) to guild {CONFIG["GUILD_ID"]}')
            else:
                # Sync globally (takes up to 1 hour to propagate)
                synced = await self.tree.sync()
                print(f'✅ Synced {len(synced)} command(s) globally')
        except Exception as e:
            print(f'❌ Failed to sync commands: {e}')

    async def on_ready(self):
        """Called when the bot is ready"""
        print(f'🦀 Bot logged in as {self.user}!')
        print(f'🏠 Connected to {len(self.guilds)} server(s):')
        for guild in self.guilds:
            print(f'   - {guild.name} (ID: {guild.id})')
        print(f'👀 Monitoring user ID: {CONFIG["TARGET_USER_ID"]}')
        print(f'🎮 Target game: {CONFIG["TARGET_GAME"]}')
        
        # Check initial presence
        await self.check_initial_presence()

    async def check_initial_presence(self):
        """Check if target user is already playing when bot starts"""
        try:
            target_user = None
            for guild in self.guilds:
                member = guild.get_member(CONFIG['TARGET_USER_ID'])
                if member:
                    target_user = member
                    break
            
            if not target_user:
                print(f'⚠️  Target user {CONFIG["TARGET_USER_ID"]} not found in any server')
                return
                
            if target_user.activities:
                is_playing = self.is_playing_target_game(target_user.activities)
                if is_playing and not self.data['is_currently_playing']:
                    print(f'🎮 User {target_user.display_name} was already playing on bot startup')
                    self.data['is_currently_playing'] = True
                    self.data['last_opened_time'] = datetime.now().timestamp()
                    await self.save_data()
        except Exception as e:
            print(f'❌ Error checking initial presence: {e}')

    async def on_presence_update(self, before, after):
        """Handle presence updates"""
        # Only monitor the target user
        if after.id != CONFIG['TARGET_USER_ID']:
            return
            
        was_playing = self.is_playing_target_game(before.activities) if before.activities else False
        is_playing = self.is_playing_target_game(after.activities) if after.activities else False

        # Game started
        if not was_playing and is_playing:
            print(f'🎮 {CONFIG["TARGET_GAME"]} started!')
            self.data['is_currently_playing'] = True
            self.data['last_opened_time'] = datetime.now().timestamp()
            await self.save_data()
        
        # Game stopped
        elif was_playing and not is_playing:
            print(f'🛑 {CONFIG["TARGET_GAME"]} stopped!')
            self.data['is_currently_playing'] = False
            self.data['last_closed_time'] = datetime.now().timestamp()
            self.data['global_counter'] = 0  # Reset counter on game close
            await self.save_data()
            print('🔄 Global counter reset to 0')

    def is_playing_target_game(self, activities):
        """Check if target game is being played"""
        if not activities:
            return False
            
        for activity in activities:
            if (activity.type == discord.ActivityType.playing and 
                activity.name == CONFIG['TARGET_GAME']):
                return True
        return False

    def format_duration(self, seconds):
        """Format duration in a human-readable way"""
        if seconds < 60:
            return f'{int(seconds)}s'
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f'{minutes}m {secs}s'
        elif seconds < 86400:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f'{hours}h {minutes}m'
        else:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            minutes = int((seconds % 3600) // 60)
            return f'{days}d {hours}h {minutes}m'

    async def shutdown(self):
        """Gracefully shutdown the bot"""
        await self.save_data()
        await self.close()
        sys.exit(0)

# Create bot instance
bot = CrabChampionsBot()

@bot.tree.command(name='time', description=f'Show time since {CONFIG["TARGET_GAME"]} was last opened')
async def time_command(interaction: discord.Interaction):
    """Handle /time command"""
    embed = discord.Embed(
        title='🦀 Crab Champions Time Tracker',
        color=0xFF6B35
    )

    try:
        if bot.data['is_currently_playing']:
            if bot.data['last_opened_time']:
                play_time = datetime.now().timestamp() - bot.data['last_opened_time']
                embed.description = f'🎮 Currently playing!\nSession started: {bot.format_duration(play_time)} ago'
            else:
                embed.description = '🎮 Currently playing! (No start time recorded)'
        elif bot.data['last_closed_time']:
            time_since_last_play = datetime.now().timestamp() - bot.data['last_closed_time']
            embed.description = f'⏰ Last played: {bot.format_duration(time_since_last_play)} ago'
        elif bot.data['last_opened_time']:
            time_since_last_open = datetime.now().timestamp() - bot.data['last_opened_time']
            embed.description = f'⏰ Last opened: {bot.format_duration(time_since_last_open)} ago'
        else:
            embed.description = '❓ No play history recorded yet'

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f'❌ Error: {e}', ephemeral=True)

@bot.tree.command(name='status', description='Show current bot status and counter information')
async def status_command(interaction: discord.Interaction):
    """Handle /status command"""
    embed = discord.Embed(
        title='🤖 Bot Status',
        color=0x0099FF
    )

    try:
        embed.add_field(
            name='🎮 Currently Playing',
            value='Yes' if bot.data['is_currently_playing'] else 'No',
            inline=True
        )
        embed.add_field(
            name='🔢 Global Counter',
            value=str(bot.data['global_counter']),
            inline=True
        )
        embed.add_field(
            name='👤 Monitoring',
            value=f'<@{CONFIG["TARGET_USER_ID"]}>',
            inline=True
        )

        if bot.data['last_opened_time']:
            last_opened = datetime.fromtimestamp(bot.data['last_opened_time'])
            embed.add_field(
                name='⏰ Last Opened',
                value=last_opened.strftime('%Y-%m-%d %H:%M:%S'),
                inline=True
            )

        if bot.data['last_closed_time']:
            last_closed = datetime.fromtimestamp(bot.data['last_closed_time'])
            embed.add_field(
                name='🛑 Last Closed',
                value=last_closed.strftime('%Y-%m-%d %H:%M:%S'),
                inline=True
            )

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f'❌ Error: {e}', ephemeral=True)

@bot.tree.command(name='counter', description='Show or modify the global counter')
@discord.app_commands.describe(
    action='What to do with the counter',
    value='Value to set (only for set action)'
)
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name='show', value='show'),
    discord.app_commands.Choice(name='set', value='set'),
    discord.app_commands.Choice(name='increment', value='increment'),
    discord.app_commands.Choice(name='decrement', value='decrement')
])
async def counter_command(interaction: discord.Interaction, action: str, value: int = None):
    """Handle /counter command"""
    try:
        if action == 'show':
            embed = discord.Embed(
                title='🔢 Global Counter',
                description=f'Current value: **{bot.data["global_counter"]}**',
                color=0x00FF00
            )
            await interaction.response.send_message(embed=embed)
        
        elif action == 'set':
            if value is None:
                await interaction.response.send_message('❌ Please provide a value to set!', ephemeral=True)
                return
                
            bot.data['global_counter'] = value
            await bot.save_data()
            
            embed = discord.Embed(
                title='🔢 Counter Updated',
                description=f'Global counter set to: **{value}**',
                color=0xFFFF00
            )
            await interaction.response.send_message(embed=embed)
        
        elif action == 'increment':
            bot.data['global_counter'] += 1
            await bot.save_data()
            
            embed = discord.Embed(
                title='🔢 Counter Incremented',
                description=f'Global counter is now: **{bot.data["global_counter"]}**',
                color=0x00FF00
            )
            await interaction.response.send_message(embed=embed)
        
        elif action == 'decrement':
            bot.data['global_counter'] -= 1
            await bot.save_data()
            
            embed = discord.Embed(
                title='🔢 Counter Decremented',
                description=f'Global counter is now: **{bot.data["global_counter"]}**',
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed)
            
    except Exception as e:
        await interaction.response.send_message(f'❌ Error: {e}', ephemeral=True)

# Run the bot
if __name__ == '__main__':
    print("🚀 Starting Crab Champions Discord Bot...")
    print("📋 Setup Instructions:")
    print("1. Replace 'YOUR_BOT_TOKEN_HERE' with your bot token")
    print("2. Replace the TARGET_USER_ID with your Discord user ID")
    print("3. Make sure the bot has been invited to your server with proper permissions")
    print("4. Ensure the bot can see your presence (you must be in a server where the bot is present)")
    print("-" * 60)
    
    try:
        bot.run(CONFIG['TOKEN'])
    except KeyboardInterrupt:
        print('\n🛑 Bot stopped by user')
    except Exception as e:
        print(f'❌ Error running bot: {e}')