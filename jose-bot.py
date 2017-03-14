# -*- coding: utf-8 -*-
import sys
import time
import asyncio
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import traceback
import logging
import readline
import discord

import josecommon as jcommon
import ext.jose as jose_bot
import jcoin.josecoin as josecoin
import joseconfig as jconfig
import joseerror as je

# profiling
from pympler import tracker
from random import SystemRandom
random = SystemRandom()

logging.basicConfig(level=logging.INFO, \
    format='[%(levelname)7s] [%(name)s] %(message)s')

start_time = time.time()

#default stuff
client = discord.Client()
jcommon.set_client(client) # to jcommon

# initialize jose instance
jose = jose_bot.JoseBot(client)
env = jose.env

counter = 0

def load_module(n, n_cl):
    t_start = time.time()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(jose.load_ext(n, n_cl, None))

    time_taken_ms = (time.time() - t_start) * 1000
    jcommon.logger.info("%s took %.3fms to load", n, time_taken_ms)

def load_all_modules():
    # essential stuff
    load_module('joselang', 'JoseLanguage')
    load_module('josehelp', 'JoseHelp')
    load_module('jcoin', 'JoseCoin')
    load_module('josestats', 'JoseStats')
    load_module('josemagicword', 'JoseMagicWord')
    load_module('josewatch', 'JoseWatch')
    load_module('josemod', 'JoseMod')
    load_module('josespeak', 'JoseSpeak')

    # the other stuff
    load_module('josememes', 'JoseMemes')
    load_module('joseimages', 'JoseImages')
    load_module('josedatamosh', 'JoseDatamosh')
    load_module('josextra', 'joseXtra')
    load_module('josegambling', 'JoseGambling')
    load_module('josemath', 'JoseMath')

    # load events
    jose.ev_empty()
    jose.ev_load(True)

async def do_event(event_name, args):
    for handler in jose.event_tbl[event_name]:
        if isinstance(args[0], discord.Message):
            cxt = jcommon.Context(client, args[0], time.time(), jose)
            await handler(cxt.message, cxt)
        else:
            await handler(*args)

async def check_message(message):
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return False

    if len(message.content) <= 0:
        return False

    if jose.command_lock:
        return False

    # Block DMs altogether
    if message.server is None:
        return False

    if message.server.id in jose.blocks['servers']:
        return False

    if jose.dev_mode:
        # Ignore messages from other servers
        if message.server.id != jcommon.JOSE_DEV_SERVER_ID:
            return False

        # Ignore non-admins
        if message.author.id not in jcommon.ADMIN_IDS:
            return False

    # configdb is langdb but with more bits
    botblock = await jcommon.configdb_get(message.server.id, 'botblock')
    if botblock and message.author.bot:
        return False

    return True

async def do_command(method, message, args, cxt, t_start, st):
    # try/except is WAY FASTER than checking if/else
    try:
        jose_method = getattr(jose, method)
    except AttributeError:
        return

    try:
        await jose_method(message, args, cxt)

    except je.PermissionError:
        jcommon.logger.warning("thrown PermissionError at %r from %s(%r)", \
            str(message.author), method, args)

        await cxt.say("Permission ¯\_(ツ)_/¯ 💠 ¯\_(ツ)_/¯ Error")

    except RuntimeError as err:
        jcommon.logger.error("RuntimeError happened with %s[%s] from %s(%r)", \
            str(message.author), message.author.id, method, args, exc_info=True)
        await cxt.say(':interrobang: RuntimeError: %r' % err)

    except je.CommonError as err:
        jcommon.logger.error("CommonError to %r from %s(%r): %r", \
            str(message.author), method, args, repr(err))

        await cxt.say('```\nCommonError: %r```', (err,))

    except je.JoseCoinError as err:
        await cxt.say('err: `%r`', (err,))

    except asyncio.TimeoutError as err:
        jcommon.logger.error("TimeoutError to %r from %s(%r): %r", \
            str(message.author), method, args, repr(err))
        await cxt.say("`[timeout] Timeout Reached`")

    except je.LimitError:
        pass

    del t_start

    delta = time.time() - st
    if delta > 10:
        jcommon.logger.warning("HIGH DELTA %r from %s[%s]: %.4fs", \
            message.content, message.author, message.author.id, delta)

    # signal python to clean this shit
    del delta, st, jose_method

    # kthxbye
    return

async def do_cooldown(message, cxt):
    # Check for cooldowns from the author of the command
    authorid = message.author.id
    now = time.time()

    # timestamp to terminate the cooldown
    if authorid in env['cooldowns']:
        cdown_term_time = env['cooldowns'][authorid]
        if now < cdown_term_time:
            secleft = cdown_term_time - now

            if secleft > 0.5:
                # say to the user they're being a shit person
                m = await cxt.say("Please cool down!(**%.1f** seconds left)", \
                    (secleft,))
                # wait secleft before deleting and removing cooldown from user
                await asyncio.sleep(secleft)
                await client.delete_message(m)

                # that code repetiton was needed, sorry
                try:
                    del env['cooldowns'][authorid]
                    return True
                except Exception as e:
                    jcommon.logger.error("do_cooldown: error removing cooldown for %d: %r", \
                        authorid, e)
            else:
                try:
                    del env['cooldowns'][authorid]
                except Exception as e:
                    jcommon.logger.error("do_cooldown: error removing cooldown for %d: %r", \
                        authorid, e)

    # always update user's cooldown
    env['cooldowns'][authorid] = now + jcommon.COOLDOWN_SECONDS
    return False

@client.event
async def on_message(message):
    global jose
    global counter

    t_start = time.time()

    is_good = await check_message(message)
    if not is_good:
        return

    if message.author.id in josecoin.data:
        account = josecoin.data[message.author.id]
        if str(message.author) != account['name']:
            account['name'] = str(message.author)

    st = time.time()

    # any_message event
    await do_event('any_message', [message])

    # get command and push it to jose
    if message.content.startswith(jcommon.JOSE_PREFIX):
        # use jcommon.parse_command
        command, args, method = jcommon.parse_command(message)
        if len(command.strip()) == '':
            return

        cxt = jcommon.Context(client, message, t_start, jose)

        try:
            getattr(jose, method)
            stop = await do_cooldown(message, cxt)
            if stop:
                return
        except AttributeError:
            return

        try:
            await do_command(method, message, args, cxt, t_start, st)
        except Exception as e:
            jcommon.logger.error("Exception at %s, made by %s", method, \
                str(message.author), exc_info=True)
            # signal user
            await cxt.say("jose.py_err: ```%s```", (traceback.format_exc(),))

        return

    # handle e_on_message
    await do_event('on_message', [message])

t_allowed = True

async def _timer_playing():
    playing_phrase = random.choice(jcommon.JOSE_PLAYING_PHRASES)
    playing_name = '%s | v%s | %d guilds | %shjose' % (playing_phrase, jcommon.JOSE_VERSION, \
        len(client.servers), jcommon.JOSE_PREFIX)

    return playing_name

async def timer_playing():
    global t_allowed
    if t_allowed:
        while True:
            game_str = await _timer_playing()
            g = discord.Game(name=game_str, url=game_str)
            await client.change_presence(game=g)

            t_allowed = False
            sec = random.randint(jcommon.PL_MIN_MINUTES * 60, \
                jcommon.PL_MAX_MINUTES * 60)

            minutes = int((sec % (60 * 60)) / 60)
            seconds = int(sec % 60)

            jcommon.logger.info("Playing %r for %dmin:%dsec", \
                game_str, minutes, seconds)

            await asyncio.sleep(sec)

@client.event
async def on_ready():
    global t_allowed
    print("="*25)
    jcommon.logger.info("josé ready, name = %s, id = %s", client.user.name, client.user.id)
    print('='*25)
    jose.command_lock = False

    await do_event('client_ready', [client])

    if not jose.dev_mode:
        await timer_playing()
    else:
        await jose.do_dev_mode()

    t_allowed = False

@client.event
async def on_server_join(server):
    for channel in server.channels:
        if channel.is_default:
            await do_event('server_join', [server, channel])

            jcommon.logger.info("New server: %s[%s]", server, server.id)
            await client.send_message(channel, jcommon.WELCOME_MESSAGE)

@client.event
async def on_error(event, *args, **kwargs):
    err = traceback.format_exc()
    jcommon.logger.error("Error at %s(%s, %s), %s" % \
        (str(event), args, kwargs, err))

    if str(event) == 'on_message':
        message = args[0]
        jcommon.logger.error("Message error happened at ServerID %s name %r" % \
            (message.server.id, message.server.name))

@client.event
async def on_member_join(member):
    await do_event('member_join', [member])

@client.event
async def on_member_remove(member):
    await do_event('member_remove', [member])

@client.event
async def on_server_remove(server):
    await do_event('server_remove', [server])

async def main_task():
    global client
    startupdelta = time.time() - jose.start_time
    jcommon.logger.info("--- STARTUP TOOK %.2f SECONDS ---", startupdelta)

    try:
        jcommon.logger.info("[start] logging")
        client.loop.create_task(jcommon.setup_logging())

        jcommon.logger.info("[start] discord client")
        await client.start(jconfig.discord_token)
        jcommon.logger.info("[exit] discord client")
    except discord.GatewayNotFound:
        jcommon.logger.error("Received GatewayNotFound from discord.")
    except Exception as err:
        jcommon.logger.error("Received %r from client.start", err, exc_info=True)

def main(args):
    try:
        mode = args[1]
    except:
        mode = 'normal'

    tr = tracker.SummaryTracker()

    if mode == 'dev':
        print("===ENTERING DEVELOPER MODE===")
        jose.dev_mode = True
        logging.basicConfig(level=logging.DEBUG)

    # load all josé's modules
    load_all_modules()

    loop = asyncio.get_event_loop()
    try:
        jcommon.logger.info("[start] main_task")
        loop.run_until_complete(main_task())
        jcommon.logger.info("[exit] main_task")
    except KeyboardInterrupt:
        jcommon.logger.info("received KeyboardInterrupt, exiting")
    except Exception as err:
        jcommon.logger.error("Received %r from main function, exiting", err)
        jcommon.logger.error("This is the error: %s", traceback.format_exc())
    finally:
        if not jose.made_gshutdown:
            jcommon.logger.info("[general_shutdown]")
            loop.run_until_complete(jose.general_shutdown(None))
        else:
            jcommon.logger.info("[general_shutdown] already done")

        jcommon.logger.info("[asyncio] Closing event loop")
        loop.close()

    tr.print_diff()

    jcommon.logger.info("[exit] main")
    logging.shutdown()
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
