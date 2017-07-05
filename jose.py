import logging
import random
import time
import sys
import traceback
import asyncio
import collections

import discord
import aiohttp

import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

from discord.ext import commands

import joseconfig as config
from ext.common import SayException

logging.basicConfig(level=logging.INFO, \
    format='[%(levelname)7s] [%(name)s] %(message)s')

log = logging.getLogger(__name__)


extensions = [
    'config', 'admin', 'exec', 'pipupdates',
    'coins', 'coins+',
    'basic',
    'gambling',
    'speak',
    'math',
    'datamosh',
    'memes',
    'extra',
    'stars',
    'stats',
    'mod', 'botcollection',
    'channel_logging',
    'playing',
]


CHECK_FAILURE_PHRASES = [
    'br?',
    'u died [real] [Not ClickBait]',
    'rEEEEEEEEEEEEE',
    'not enough permissions lul',
]


BAD_ARG_MESSAGES = [
    'dude give me the right thing',
    'u can\'t give me this and think i can do something',
    'succ my rod',
    'i\'m not a god, fix your args',
]


class JoseContext(commands.Context):
    async def ok(self):
        try:
            await self.message.add_reaction('👌')
        except discord.Forbidden:
            await self.message.channel.send('ok')

    async def not_ok(self):
        try:
            await self.message.add_reaction('❌')
        except discord.Forbidden:
            await self.message.channel.send('not ok')

    async def success(self, flag):
        if flag:
            await self.ok()
        else:
            await self.not_ok()


class JoseBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_time = time.time()
        self.config = config
        self.session = aiohttp.ClientSession()
        self.simple_exc = [SayException]

        # reeeeee dont query mongo every message god damn it
        self.block_cache = {}

    async def on_ready(self):
        log.info(f'Logged in! {self.user!s}')

    async def is_blocked(self, user_id: int):
        """Returns If a user is blocked to use José. Uses cache"""
        if user_id in self.block_cache:
            return self.block_cache[user_id]

        blocked = await self.block_coll.find_one({'user_id': user_id})
        is_blocked = bool(blocked)
        self.block_cache[user_id] = is_blocked
        
        return is_blocked

    async def is_blocked_guild(self, guild_id: int):
        """Returns if a guild is blocked to use José. Uses cache"""
        if guild_id in self.block_cache:
            return self.block_cache[guild_id]

        blocked = await self.block_coll.find_one({'guild_id': guild_id})
        is_blocked = bool(blocked)
        self.block_cache[guild_id] = is_blocked
        
        return is_blocked

    async def on_command(self, ctx):
        # thanks dogbot ur a good
        author = ctx.message.author
        checks = [c.__qualname__.split('.')[0] for c in ctx.command.checks]
        location = '[DM]' if isinstance(ctx.channel, discord.DMChannel) else '[Guild]'
        log.info('%s [cmd] %s(%d) "%s" checks=%s', location, author, author.id, ctx.message.content,
                 ','.join(checks) or '(none)')

    async def on_command_error(self, ctx, error):
        message = ctx.message

        if isinstance(error, commands.errors.CommandInvokeError):
            orig = error.original
            if isinstance(orig, SayException):
                await ctx.send(orig.args[0])
                return

            tb = ''.join(traceback.format_exception(
                type(error.original), error.original,
                error.original.__traceback__
            ))

            if isinstance(orig, tuple(self.simple_exc)):
                log.error(f'Errored at {message.content!r} from {message.author!s}\n{error.original!r}')
            else:
                log.error(f'Errored at {message.content!r} from {message.author!s}\n{tb}')

            if isinstance(orig, self.cogs['Coins'].TransferError):
                await ctx.send(f'JoséCoin error: `{error.original!r}`')
                return

            await ctx.send(f'fucking 🅱enis, u 🅱roke the bot ```py\n{tb}\n```')
        elif isinstance(error, commands.errors.BadArgument):
            await ctx.send(f'bad arg — {random.choice(BAD_ARG_MESSAGES)}')
        elif isinstance(error, commands.errors.CheckFailure):
            await ctx.send(f'check fail — {random.choice(CHECK_FAILURE_PHRASES)}')

    async def on_message(self, message):
        author_id = message.author.id

        if await self.is_blocked(author_id):
            return

        try:
            guild_id = message.guild.id

            if await self.is_blocked_guild(guild_id):
                return
        except AttributeError:
            # in a DM
            pass

        ctx = await self.get_context(message, cls=JoseContext)
        await self.invoke(ctx)


jose = JoseBot(
    command_prefix=getattr(config, 'prefix', None) or 'j!',
    description='henlo dis is jose',
    pm_help=None
)

if __name__ == '__main__':
    for extension in extensions:
        try:
            t_start = time.monotonic()
            jose.load_extension(f'ext.{extension}')
            t_end = time.monotonic()
            delta = round((t_end - t_start) * 1000, 2)
            log.info(f"[load] {extension} took {delta}ms")
        except Exception as err:
            log.error(f'Failed to load {extension}', exc_info=True)
            sys.exit(1)

    jose.run(config.token)
