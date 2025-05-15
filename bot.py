import discord
from discord.ext import commands
import os
import asyncio
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

scheduler = AsyncIOScheduler()

# Estado do jogo
players = []
roles = {}
game_started = False
channel_game = None
witch_potions = {"heal": True, "kill": True}
player_actions = {}  # Guarda se jogador agiu na fase atual

# Papéis possíveis
possible_roles = [
    "assassino sombrio",
    "oráculo da luz",
    "alquimista arcana",
    "civil"
]

# Tempos em segundos
TIME_STANDBY_INTERVAL = 300  # 5 minutos para mensagem standby
TIME_ACTION = 60  # 60 segundos para realizar ação na fase noturna
TIME_GAME_RESTART = 120  # 2 minutos após fim para reiniciar

# ------- FUNÇÕES AUXILIARES --------

def assign_roles():
    import random
    global players, roles
    roles.clear()
    shuffled = players[:]
    random.shuffle(shuffled)
    # Simplificação: 1 assassino, 1 oráculo, 1 alquimista, resto civis
    for i, p in enumerate(shuffled):
        if i == 0:
            roles[p] = "assassino sombrio"
        elif i == 1:
            roles[p] = "oráculo da luz"
        elif i == 2:
            roles[p] = "alquimista arcana"
        else:
            roles[p] = "civil"

def player_acted(player):
    return player_actions.get(player.id, False)

def reset_player_actions():
    player_actions.clear()

async def checar_vitoria():
    global game_started, players, roles
    assassinos = [p for p in players if roles.get(p) == "assassino sombrio"]
    civis = [p for p in players if roles.get(p) != "assassino sombrio"]
    if len(assassinos) == 0:
        await channel_game.send("🏆 **Civis venceram!** Os heróis salvaram Havrenna!")
        await finalizar_jogo()
    elif len(assassinos) >= len(civis):
        await channel_game.send("☠️ **Assassinos venceram!** Havrenna mergulha na escuridão!")
        await finalizar_jogo()
    # Caso contrário, continua

async def finalizar_jogo():
    global players, roles, game_started, witch_potions
    game_started = False
    players.clear()
    roles.clear()
    witch_potions = {"heal": True, "kill": True}
    reset_player_actions()
    await channel_game.send("🔚 O jogo Heroes of Havrenna chegou ao fim.")
    scheduler.add_job(reset_game, 'date', run_date=datetime.datetime.now() + datetime.timedelta(seconds=TIME_GAME_RESTART))

async def reset_game():
    await channel_game.send("🔄 Novo desafio começará em breve! Use `!entrar` para juntar-se.")

# --------- AGENDAMENTOS E TIMEOUTS -----------

async def standby_message():
    global game_started, channel_game
    if not game_started and channel_game:
        await channel_game.send("🌟 O desafio de Havrenna aguarda heróis! Use `!entrar` para participar.")

async def assassin_timeout(player):
    if not player_acted(player):
        if player in players:
            players.remove(player)
            await channel_game.send(f"💀 {player.display_name} foi removido por inatividade durante a fase noturna.")
            await checar_vitoria()

async def oracle_timeout(player):
    if not player_acted(player):
        await player.send("⏰ Tempo esgotado para usar o Oráculo da Luz.")

async def alchemist_timeout(player):
    if not player_acted(player):
        await player.send("⏰ Tempo esgotado para usar a Alquimista Arcana.")

# ------------ FASES DO JOGO -------------------

async def begin_night_phase():
    reset_player_actions()
    await channel_game.send("🌙 **Noite cai sobre Havrenna...** Heróis, preparem-se para suas ações.")
    await assassin_turn()

async def assassin_turn():
    assassinos = [p for p in players if roles.get(p) == "assassino sombrio"]
    if not assassinos:
        await channel_game.send("Nenhum assassino para agir.")
        await begin_day_phase()
        return

    for a in assassinos:
        try:
            await a.send("🗡️ Você é o Assassino Sombrio. Escolha alguém para matar com `!matar @usuario` (tempo: 60s).")
        except:
            await channel_game.send(f"⚠️ Não consegui enviar DM para {a.display_name}.")
        scheduler.add_job(asyncio.create_task, args=[assassin_timeout(a)], trigger='date', run_date=datetime.datetime.now() + datetime.timedelta(seconds=TIME_ACTION))

async def begin_day_phase():
    reset_player_actions()
    await channel_game.send("☀️ **O dia amanhece em Havrenna.** É hora de discutir e votar!")
    await channel_game.send("Use `!votar @usuario` para votar em quem será banido.")
    # Pode adicionar timeout para votação

# --------- COMANDOS DO BOT --------------

@bot.command(name="entrar")
async def entrar(ctx):
    global game_started, channel_game
    if game_started:
        await ctx.send("⛔ O jogo já começou, aguarde a próxima rodada.")
        return
    if ctx.author in players:
        await ctx.send("⚠️ Você já está na lista dos jogadores.")
        return
    players.append(ctx.author)
    channel_game = ctx.channel
    await ctx.send(f"✅ {ctx.author.display_name} entrou no desafio!")
    if len(players) >= 4:
        await ctx.send("👑 Mínimo de jogadores alcançado! Use `!iniciar` para começar.")

@bot.command(name="sair")
async def sair(ctx):
    if ctx.author in players:
        players.remove(ctx.author)
        await ctx.send(f"🚪 {ctx.author.display_name} saiu do desafio.")
    else:
        await ctx.send("❌ Você não está participando.")

@bot.command(name="iniciar")
async def iniciar(ctx):
    global game_started
    if game_started:
        await ctx.send("⚠️ O jogo já está em andamento.")
        return
    if len(players) < 4:
        await ctx.send("⚠️ Número insuficiente de jogadores para iniciar (mínimo 4).")
        return
    game_started = True
    assign_roles()
    await ctx.send("🔥 O jogo Heroes of Havrenna começou!")
    await enviar_roles()
    scheduler.add_job(begin_night_phase, 'date', run_date=datetime.datetime.now() + datetime.timedelta(seconds=5))

async def enviar_roles():
    for p in players:
        role = roles.get(p)
        try:
            await p.send(f"🃏 Seu papel: **{role.title()}**")
        except:
            await channel_game.send(f"⚠️ Não consegui enviar DM para {p.display_name}.")

@bot.command(name="matar")
async def matar(ctx, target: discord.Member):
    if not game_started:
        await ctx.send("⛔ Nenhum jogo em andamento.")
        return
    if roles.get(ctx.author) != "assassino sombrio":
        await ctx.send("🚫 Você não é o Assassino Sombrio.")
        return
    if target not in players:
        await ctx.send("❌ Jogador inválido.")
        return
    if player_acted(ctx.author):
        await ctx.send("⏳ Você já executou sua ação.")
        return
    players.remove(target)
    player_actions[ctx.author.id] = True
    await ctx.send(f"💀 {target.display_name} foi assassinado durante a noite.")
    await checar_vitoria()
    await begin_day_phase()

@bot.command(name="votar")
async def votar(ctx, target: discord.Member):
    # Aqui você pode adicionar lógica para contar votos, sistema mais complexo, etc.
    await ctx.send(f"{ctx.author.display_name} votou para banir {target.display_name}. (Sistema de votos não implementado ainda)")

@bot.command(name="usar_pocao")
async def usar_pocao(ctx, tipo: str, target: discord.Member = None):
    if roles.get(ctx.author) != "alquimista arcana":
        await ctx.send("🚫 Você não é a Alquimista Arcana.")
        return
    if tipo.lower() not in witch_potions:
        await ctx.send("❌ Tipo de poção inválido. Use `heal` ou `kill`.")
        return
    if not witch_potions[tipo.lower()]:
        await ctx.send(f"⚠️ A poção `{tipo}` já foi usada.")
        return
    # Exemplo simplificado
    witch_potions[tipo.lower()] = False
    player_actions[ctx.author.id] = True
    await ctx.send(f"✨ {ctx.author.display_name} usou a poção `{tipo}`!")
    # Exemplo efeito da poção (a implementar)

# EVENTO ON READY

@bot.event
async def on_ready():
    global channel_game
    print(f"🤖 Heroes of Havrenna online como {bot.user}")
    scheduler.start()
    # Agendar mensagem standby a cada 5 minutos
    scheduler.add_job(lambda: asyncio.create_task(standby_message()), IntervalTrigger(seconds=TIME_STANDBY_INTERVAL))
    # (Se quiser, pode restaurar estado de jogo aqui)

# RODA O BOT

if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()
    TOKEN = os.getenv("DISCORD_TOKEN")
    bot.run(TOKEN)
