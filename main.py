import discord
from discord.ext import commands
import os
import random
import asyncio
import threading
import json
from flask import Flask
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

# ===== KEEP-ALIVE - deixa o bot com porta aberta pro Render nao dormir =====
app = Flask(__name__)

@app.route("/")
def home():
    return "TENGU BOT ON - TROPA REINA"

def rodar_site():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=rodar_site, daemon=True)
    t.start()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

x1_ativo = False
x1_jogo = {}

# ===== PLACAR X1 - salva em placar.json =====
ARQUIVO_PLACAR = "placar.json"

def carregar_placar():
    try:
        with open(ARQUIVO_PLACAR, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def salvar_placar(placar):
    try:
        with open(ARQUIVO_PLACAR, "w", encoding="utf-8") as f:
            json.dump(placar, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar placar: {e}")

def pegar_stats(placar, user):
    dados = placar.get(str(user.id), {"nome": user.display_name, "vitorias": 0, "derrotas": 0})
    dados["nome"] = user.display_name
    return dados

def registrar_resultado(vencedor, perdedor):
    placar = carregar_placar()
    v = pegar_stats(placar, vencedor)
    d = pegar_stats(placar, perdedor)
    v["vitorias"] += 1
    d["derrotas"] += 1
    placar[str(vencedor.id)] = v
    placar[str(perdedor.id)] = d
    salvar_placar(placar)
    return v, d

@bot.event
async def on_ready():
    print(f"Logado como {bot.user}")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! {round(bot.latency * 1000)}ms")

@bot.command(name="lista")
async def lista(ctx):
    embed = discord.Embed(title="LISTA DE COMANDOS - TENGU", description="Todos os comandos do bot:", color=0xFF8000)
    embed.add_field(name="!ping", value="Ver se o bot ta on e o ping", inline=False)
    embed.add_field(name="!falar @pessoa frase", value="Manda uma frase com a foto e o nick da pessoa marcada", inline=False)
    embed.add_field(name="!raid", value="Manda 10x TROPA REINA (cooldown de 30s)", inline=False)
    embed.add_field(name="!x1", value="Chama alguem pro X1 - os 2 escolhem juntos: atacar / defender / curar, depois rolam juntos", inline=False)
    embed.add_field(name="!lista", value="Mostra essa lista aqui", inline=False)
    embed.add_field(name="!placarx1", value="Mostra o placar de vitorias / derrotas do X1", inline=False)
    embed.add_field(name="!placarx1 @pessoa", value="Mostra o placar de uma pessoa especifica", inline=False)
    embed.set_footer(text="Prefixo: !")
    await ctx.send(embed=embed)

@bot.command(name="falar")
async def falar(ctx, member: discord.Member = None, *, frase: str = None):
    try:
        await ctx.message.delete()
    except:
        pass
    if not member or not frase:
        return
    try:
        webhooks = await ctx.channel.webhooks()
        for w in webhooks:
            if w.name == "resenha-falar":
                await w.delete()
        webhook = await ctx.channel.create_webhook(name="resenha-falar")
        await webhook.send(
            content=frase + " \U0001F440",
            username=member.display_name,
            avatar_url=member.display_avatar.url,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False)
        )
    except Exception as e:
        print(f"Erro no !falar: {e}")

@bot.command(name="raid")
@commands.cooldown(1, 30, commands.BucketType.channel)
async def raid(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.send("TROPA REINA\n" * 10)

# ===== X1 - SIMULTANEO + CURAR + APAGAR PAINEL ANTIGO =====

def barra_vida(vida):
    cheio = max(0, min(10, int(vida / 10)))
    return "\u2764\uFE0F" * cheio + "\U0001F5A4" * (10 - cheio) + f" {vida}/100"

async def apagar_painel_antigo(jogo):
    msg = jogo.get("painel_msg") if jogo else None
    if msg:
        try:
            await msg.delete()
        except:
            pass
    if jogo:
        jogo["painel_msg"] = None

async def enviar_painel_escolha(canal, jogo):
    await apagar_painel_antigo(jogo)
    jogo["escolhas"] = {}
    jogo["dados"] = {}
    embed = discord.Embed(title=f"X1 - ROUND {jogo['round']} - ESCOLHAM AO MESMO TEMPO!", color=0xFF8000)
    embed.add_field(name=f"{jogo['jogadores'][0].display_name}", value=barra_vida(jogo["vida"][0]), inline=False)
    embed.add_field(name=f"{jogo['jogadores'][1].display_name}", value=barra_vida(jogo["vida"][1]), inline=False)
    embed.add_field(name="Como funciona", value="Os 2 escolhem escondido: ATACAR / DEFENDER / CURAR\nDepois os 2 rolam o dado juntos e o round resolve!\n\nATACAR: dado 1-10, dano = dado x 5 (10 = 50)\nDEFENDER: dado 1-10, escudo = dado x 5 (10 = segura 50)\nCURAR: dado 1-5, cura = dado x 6 (5 = 30)", inline=False)
    embed.set_footer(text="Ninguem ve a escolha do outro ate rolar!")
    view = EscolhaSimultaneaView(jogo, canal)
    msg = await canal.send(embed=embed, view=view)
    jogo["painel_msg"] = msg

class AceitarView(discord.ui.View):
    def __init__(self, desafiante, canal):
        super().__init__(timeout=60)
        self.desafiante = desafiante
        self.canal = canal
        self.aceito = False

    @discord.ui.button(label="ACEITAR X1", style=discord.ButtonStyle.green)
    async def aceitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        global x1_ativo, x1_jogo
        if interaction.user.id == self.desafiante.id:
            await interaction.response.send_message("Tu nao pode aceitar teu proprio X1", ephemeral=True)
            return
        if self.aceito:
            return
        self.aceito = True
        jogador2 = interaction.user
        await interaction.response.send_message(f"{jogador2.mention} ACEITOU! O X1 vai comecar!")
        try:
            await interaction.message.delete()
        except:
            pass
        x1_jogo = {
            "jogadores": [self.desafiante, jogador2],
            "vida": [100, 100],
            "escolhas": {},
            "dados": {},
            "round": 1,
            "painel_msg": None,
        }
        await self.canal.send(f"X1 COMECOU!\n{self.desafiante.mention} VS {jogador2.mention}\nCada um com 100 de vida. Quem zerar a vida do outro primeiro ganha!")
        await enviar_painel_escolha(self.canal, x1_jogo)

    async def on_timeout(self):
        global x1_ativo
        if not self.aceito:
            await self.canal.send("Ninguem aceitou o X1. Cancelado")
            x1_ativo = False

class EscolhaSimultaneaView(discord.ui.View):
    def __init__(self, jogo, canal):
        super().__init__(timeout=90)
        self.jogo = jogo
        self.canal = canal

    async def escolher(self, interaction, escolha):
        ids = [p.id for p in self.jogo["jogadores"]]
        if interaction.user.id not in ids:
            await interaction.response.send_message("So quem ta no X1 pode clicar!", ephemeral=True)
            return
        idx = ids.index(interaction.user.id)
        if idx in self.jogo["escolhas"]:
            await interaction.response.send_message("Tu ja escolheu! Espera o outro.", ephemeral=True)
            return
        self.jogo["escolhas"][idx] = escolha
        nomes = {"atacar": "ATACAR", "defender": "DEFENDER", "curar": "CURAR"}
        await interaction.response.send_message(f"Voce escolheu {nomes[escolha]}... ninguem viu. Espera o outro escolher.", ephemeral=True)
        if len(self.jogo["escolhas"]) == 2:
            await apagar_painel_antigo(self.jogo)
            embed = discord.Embed(title="HORA DE ROLAR O DADO! - TODO MUNDO JUNTO", description="Os 2 ja escolheram! Agora os 2 rolam o dado.", color=0xFFD700)
            embed.add_field(name="Jogadores", value=f"{self.jogo['jogadores'][0].mention} e {self.jogo['jogadores'][1].mention} - cliquem em ROLAR!", inline=False)
            msg = await self.canal.send(embed=embed, view=RolarSimultaneoView(self.jogo, self.canal))
            self.jogo["painel_msg"] = msg

    @discord.ui.button(label="ATACAR", style=discord.ButtonStyle.red)
    async def atacar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.escolher(interaction, "atacar")

    @discord.ui.button(label="DEFENDER", style=discord.ButtonStyle.blurple)
    async def defender(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.escolher(interaction, "defender")

    @discord.ui.button(label="CURAR", style=discord.ButtonStyle.green)
    async def curar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.escolher(interaction, "curar")

class RolarSimultaneoView(discord.ui.View):
    def __init__(self, jogo, canal):
        super().__init__(timeout=90)
        self.jogo = jogo
        self.canal = canal

    @discord.ui.button(label="ROLAR", style=discord.ButtonStyle.green)
    async def rolar(self, interaction: discord.Interaction, button: discord.ui.Button):
        global x1_ativo
        ids = [p.id for p in self.jogo["jogadores"]]
        if interaction.user.id not in ids:
            await interaction.response.send_message("So quem ta no X1 pode rolar!", ephemeral=True)
            return
        idx = ids.index(interaction.user.id)
        if idx in self.jogo["dados"]:
            await interaction.response.send_message("Tu ja rolou! Espera o outro.", ephemeral=True)
            return
        escolha = self.jogo["escolhas"].get(idx, "atacar")
        if escolha == "curar":
            dado = random.randint(1, 5)
        else:
            dado = random.randint(1, 10)
        self.jogo["dados"][idx] = dado
        await interaction.response.send_message(f"Voce rolou **{dado}**! Espera o outro rolar.", ephemeral=True)
        if len(self.jogo["dados"]) == 2:
            await self.resolver_round()

    async def resolver_round(self):
        global x1_ativo
        jogo = self.jogo
        canal = self.canal
        await apagar_painel_antigo(jogo)
        p0, p1 = jogo["jogadores"]
        e0, e1 = jogo["escolhas"].get(0, "atacar"), jogo["escolhas"].get(1, "atacar")
        d0, d1 = jogo["dados"].get(0, 1), jogo["dados"].get(1, 1)
        escudo = [0, 0]
        cura = [0, 0]
        dano_bruto = [0, 0]
        for i, (esc, dad) in enumerate([(e0, d0), (e1, d1)]):
            if esc == "defender":
                escudo[i] = dad * 5
            elif esc == "curar":
                cura[i] = dad * 6
            elif esc == "atacar":
                dano_bruto[i] = dad * 5
        dano_final = [0, 0]
        dano_final[0] = max(0, dano_bruto[1] - escudo[0])
        dano_final[1] = max(0, dano_bruto[0] - escudo[1])
        escudo_usado = [min(escudo[0], dano_bruto[1]), min(escudo[1], dano_bruto[0])]
        jogo["vida"][0] = max(0, min(100, jogo["vida"][0] - dano_final[0] + cura[0]))
        jogo["vida"][1] = max(0, min(100, jogo["vida"][1] - dano_final[1] + cura[1]))
        nomes = {"atacar": "ATACOU", "defender": "DEFENDEU", "curar": "CUROU"}
        embed = discord.Embed(title=f"RESULTADO DO ROUND {jogo['round']}!", color=0xFF0000)
        embed.add_field(name=f"{p0.display_name} - {nomes[e0]}", value=f"Dado: **{d0}**\nEscudo: {escudo[0]}\nCura: +{cura[0]}\nDano que deu: {dano_bruto[0]} (segurado: {escudo_usado[1]})\nDano que tomou: {dano_final[0]}", inline=False)
        embed.add_field(name=f"{p1.display_name} - {nomes[e1]}", value=f"Dado: **{d1}**\nEscudo: {escudo[1]}\nCura: +{cura[1]}\nDano que deu: {dano_bruto[1]} (segurado: {escudo_usado[0]})\nDano que tomou: {dano_final[1]}", inline=False)
        embed.add_field(name="Vida agora", value=f"{p0.display_name}: {barra_vida(jogo['vida'][0])}\n{p1.display_name}: {barra_vida(jogo['vida'][1])}", inline=False)
        await canal.send(embed=embed)
        v0_morto = jogo["vida"][0] <= 0
        v1_morto = jogo["vida"][1] <= 0
        if v0_morto and v1_morto:
            await canal.send("EMPATE! Os 2 cairam ao mesmo tempo! Que X1 foi esse?!")
            x1_ativo = False
            return
        if v0_morto:
            v_stats, d_stats = registrar_resultado(p1, p0)
            await canal.send(embed=discord.Embed(title="FIM DO X1!", description=f"{p1.mention} VENCEU O X1!!!\n\n**{p1.display_name}**\nVitorias: {v_stats['vitorias']} | Derrotas: {v_stats['derrotas']}\n\n**{p0.display_name}**\nVitorias: {d_stats['vitorias']} | Derrotas: {d_stats['derrotas']}", color=0xFFD700))
            x1_ativo = False
            return
        if v1_morto:
            v_stats, d_stats = registrar_resultado(p0, p1)
            await canal.send(embed=discord.Embed(title="FIM DO X1!", description=f"{p0.mention} VENCEU O X1!!!\n\n**{p0.display_name}**\nVitorias: {v_stats['vitorias']} | Derrotas: {v_stats['derrotas']}\n\n**{p1.display_name}**\nVitorias: {d_stats['vitorias']} | Derrotas: {d_stats['derrotas']}", color=0xFFD700))
            x1_ativo = False
            return
        jogo["round"] += 1
        await asyncio.sleep(1)
        await enviar_painel_escolha(canal, jogo)

@bot.command(name="placarx1")
async def placarx1(ctx, member: discord.Member = None):
    placar = carregar_placar()
    # Se marcou alguem, mostra so essa pessoa
    if member:
        dados = pegar_stats(placar, member)
        embed = discord.Embed(title=f"PLACAR X1 - {member.display_name}", color=0xFF8000)
        embed.add_field(name="Vitorias", value=f"🏆 {dados['vitorias']}", inline=True)
        embed.add_field(name="Derrotas", value=f"💀 {dados['derrotas']}", inline=True)
        total = dados['vitorias'] + dados['derrotas']
        aproveitamento = round(dados['vitorias'] / total * 100) if total > 0 else 0
        embed.add_field(name="Aproveitamento", value=f"{aproveitamento}% ({total} jogos)", inline=False)
        await ctx.send(embed=embed)
        return
    # Sem marcar ninguem, mostra o ranking
    if not placar:
        await ctx.send("Ninguem jogou X1 ainda! Manda um `!x1` pra começar!")
        return
    ranking = sorted(placar.values(), key=lambda x: (x["vitorias"], -x["derrotas"]), reverse=True)[:10]
    embed = discord.Embed(title="🏆 PLACAR X1 - RANKING", description="Top 10 do X1:", color=0xFFD700)
    texto = ""
    medalhas = ["🥇", "🥈", "🥉"]
    for i, dados in enumerate(ranking):
        medalha = medalhas[i] if i < 3 else f"{i+1}."
        texto += f"{medalha} **{dados['nome']}** - Vitorias: {dados['vitorias']} | Derrotas: {dados['derrotas']}\n"
    embed.add_field(name="Ranking", value=texto, inline=False)
    embed.set_footer(text="Pra ver o teu placar: !placarx1 @tu mesmo")
    await ctx.send(embed=embed)

@bot.command(name="x1")
async def x1(ctx):
    global x1_ativo
    if x1_ativo:
        await ctx.send("Ja tem um X1 rolando! Espera acabar pra comecar outro", delete_after=5)
        return
    x1_ativo = True
    embed = discord.Embed(
        title="ALGUEM ACEITA UM X1?",
        description=f"{ctx.author.mention} ta chamando pro X1!\n\nRegras:\n100 de vida cada um\nATACAR: dado 1-10, dano = dado x 5 (10 = 50)\nDEFENDER: dado 1-10, escudo = dado x 5 (10 = segura 50)\nCURAR: dado 1-5, cura = dado x 6 (5 = 30)\n\nOs 2 escolhem juntos, os 2 rolam juntos. Quem zerar a vida do outro primeiro ganha!",
        color=0xFF8000
    )
    embed.set_footer(text="A primeira pessoa que clicar em ACEITAR entra no X1!")
    view = AceitarView(ctx.author, ctx.channel)
    await ctx.send(embed=embed, view=view)

keep_alive()
bot.run(TOKEN)
