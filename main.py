import discord
from discord.ext import commands
import os
import random
import asyncio
import threading
import json
import base64
import time
import urllib.request
import urllib.error
from flask import Flask
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

# ===== KEEP-ALIVE =====
app = Flask(__name__)
@app.route("/")
def home():
    return "FILHO DA TROPA BOT ON - TROPA REINA"
def rodar_site():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
def keep_alive():
    threading.Thread(target=rodar_site, daemon=True).start()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

x1_ativo = False
x1_jogo = {}
x1_lock = asyncio.Lock()

# ===== CANAL LIMITADO (SO ADM) =====
ARQUIVO_CONFIG = "config.json"
def carregar_config():
    return carregar_json(ARQUIVO_CONFIG)
def salvar_config(c):
    salvar_json(ARQUIVO_CONFIG, c)
def canal_limitado(guild_id):
    cfg = carregar_config()
    return cfg.get(str(guild_id), {}).get("canal_limitado")
def definir_canal_limitado(guild_id, canal_id):
    cfg = carregar_config()
    cfg[str(guild_id)] = {"canal_limitado": canal_id}
    salvar_config(cfg)

# ============================================================
# ===== PERSONAGENS =====
# ============================================================
PERSONAGENS = {
    "anne": {
        "id": "anne",
        "nome": "Anne bastard Family",
        "ataque": 7,
        "defesa": 9,
        "cura": 4,
        "codigo": "ANNE-BASTARD",
        "especial": "Apos usar CURAR 2 rounds seguidos, a cura aumenta +10% pelos proximos 2 rounds.",
        "imagem": "https://raw.githubusercontent.com/Kamizoka/filho-da-tropa/main/anne.png",
    },
    "minghar": {
        "id": "minghar",
        "nome": "Escudeiro Ming Har",
        "ataque": 3,
        "defesa": 10,
        "cura": 7,
        "codigo": "MING-HAR",
        "especial": "Recebe 15% a menos de dano nos primeiros 2 ataques do oponente.",
        "imagem": "https://raw.githubusercontent.com/Kamizoka/filho-da-tropa/main/minghar.png",
    },
}

CODIGO_PARA_PERSONAGEM = {v["codigo"].upper(): k for k, v in PERSONAGENS.items()}

PERSONAGEM_PADRAO = {
    "id": "padrao",
    "nome": "Personagem Padrao",
    "ataque": 6,
    "defesa": 6,
    "cura": 6,
    "codigo": "",
    "especial": "Sem especial. Personagem basico pra quem ainda nao resgatou nenhum.",
    "imagem": "",
}

MAX_INVENTARIO = 3
ARQUIVO_PLACAR = "placar.json"
ARQUIVO_PERSONAGENS = "inventario.json"
ARQUIVO_PENDENTE = {}

# ============================================================
# ===== SALVAMENTO GITHUB + LOCAL =====
# ============================================================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "Kamizoka/filho-da-tropa")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

_CACHE_GITHUB = {}
_CACHE_TEMPO = {}

def _github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "FilhoDaTropa-Bot",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

def _github_ler_arquivo(arquivo):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{arquivo}?ref={GITHUB_BRANCH}"
    req = urllib.request.Request(url, headers=_github_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            conteudo = data.get("content", "")
            if not conteudo:
                return {}
            texto = base64.b64decode(conteudo).decode("utf-8")
            return json.loads(texto) if texto.strip() else {}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"[GitHub] Erro ao ler {arquivo}: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"[GitHub] Erro ao ler {arquivo}: {e}")
        return None

def _github_sha_arquivo(arquivo):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{arquivo}?ref={GITHUB_BRANCH}"
    req = urllib.request.Request(url, headers=_github_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("sha")
    except Exception:
        return None

def _github_salvar_arquivo(arquivo, dados):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print(f"[GitHub] Sem GITHUB_TOKEN, salvando so local: {arquivo}")
        return False
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    conteudo_b64 = base64.b64encode(texto.encode("utf-8")).decode("utf-8")
    sha = _github_sha_arquivo(arquivo)
    payload = {
        "message": f"Atualiza {arquivo} pelo bot - nao apagar",
        "content": conteudo_b64,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{arquivo}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**_github_headers(), "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[GitHub] Salvo {arquivo} no GitHub! Status {resp.status}")
            return True
    except Exception as e:
        print(f"[GitHub] Erro ao salvar {arquivo}: {e}")
        return False

def _github_salvar_em_thread(arquivo, dados):
    copia = json.loads(json.dumps(dados, ensure_ascii=False))
    threading.Thread(
        target=_github_salvar_arquivo,
        args=(arquivo, copia),
        daemon=True,
    ).start()

def carregar_json(arquivo):
    if arquivo in _CACHE_GITHUB:
        return json.loads(json.dumps(_CACHE_GITHUB[arquivo], ensure_ascii=False))
    do_github = _github_ler_arquivo(arquivo)
    if do_github is not None:
        _CACHE_GITHUB[arquivo] = do_github
        try:
            with open(arquivo, "w", encoding="utf-8") as f:
                json.dump(do_github, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return json.loads(json.dumps(do_github, ensure_ascii=False))
    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            dados = json.load(f)
            _CACHE_GITHUB[arquivo] = dados
            return dados
    except Exception:
        return {}

def salvar_json(arquivo, dados):
    _CACHE_GITHUB[arquivo] = json.loads(json.dumps(dados, ensure_ascii=False))
    try:
        with open(arquivo, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar local {arquivo}: {e}")
    agora = time.time()
    ultimo = _CACHE_TEMPO.get(arquivo, 0)
    if agora - ultimo >= 5:
        _CACHE_TEMPO[arquivo] = agora
        _github_salvar_em_thread(arquivo, dados)
    else:
        def _salvar_depois():
            time.sleep(6)
            _github_salvar_arquivo(arquivo, dados)
        threading.Thread(target=_salvar_depois, daemon=True).start()

def carregar_placar():
    return carregar_json(ARQUIVO_PLACAR)
def salvar_placar(p):
    salvar_json(ARQUIVO_PLACAR, p)
def carregar_inventario():
    return carregar_json(ARQUIVO_PERSONAGENS)
def salvar_inventario(inv):
    salvar_json(ARQUIVO_PERSONAGENS, inv)

def dados_usuario(user_id):
    inv = carregar_inventario()
    dados = inv.get(str(user_id))
    if not dados:
        dados = {"inventario": [], "equipado": None, "codigos_usados": []}
        inv[str(user_id)] = dados
        salvar_inventario(inv)
    dados.setdefault("inventario", [])
    dados.setdefault("equipado", None)
    dados.setdefault("codigos_usados", [])
    return dados

def salvar_dados_usuario(user_id, dados):
    inv = carregar_inventario()
    inv[str(user_id)] = dados
    salvar_inventario(inv)

def personagem_por_id(pid):
    if not pid or pid == "padrao":
        return PERSONAGEM_PADRAO
    return PERSONAGENS.get(pid, PERSONAGEM_PADRAO)

def personagem_equipado_de(user_id):
    dados = dados_usuario(user_id)
    if dados["equipado"] and dados["equipado"] in dados["inventario"]:
        return personagem_por_id(dados["equipado"])
    return PERSONAGEM_PADRAO

def texto_personagem(p):
    return (
        f"**{p['nome']}**\n"
        f"⚔ Ataque: **{p['ataque']}**  |  🛡 Defesa: **{p['defesa']}**  |  💚 Cura: **{p['cura']}**\n"
        f"✨ Especial: {p['especial']}"
    )

def embed_personagem(p, titulo="PERSONAGEM EQUIPADO"):
    embed = discord.Embed(title=titulo, description=texto_personagem(p), color=0xFF8000)
    embed.add_field(name="Dano maximo", value=f"Ataque {p['ataque']} x dado 10 = **{p['ataque']*10}** de dano", inline=False)
    embed.add_field(name="Escudo maximo", value=f"Defesa {p['defesa']} x dado 10 = **{p['defesa']*10}** de escudo", inline=False)
    embed.add_field(name="Cura maxima", value=f"Cura {p['cura']} x dado 5 = **{p['cura']*5}** de cura", inline=False)
    if p.get("imagem"):
        embed.set_image(url=p["imagem"])
    return embed

# ===== PLACAR =====
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

@bot.command(name="ajudax1")
async def ajudax1(ctx):
    embed = discord.Embed(title="❓ AJUDA DO X1 - FILHO DA TROPA", description="Tudo que tu precisa saber pra jogar:", color=0xFF8000)
    embed.add_field(name="🎮 Como comecar", value="**!x1** - Chama alguem pro X1\nA primeira pessoa que clicar em **ACEITAR X1** entra.\nDepois os 2 escolhem o personagem pra batalhar.", inline=False)
    embed.add_field(name="👤 Personagens", value="**!resgatarpersonagem CODIGO** ou **!rp CODIGO** - Resgata um personagem\n**!personagem** ou **!p** - Mostra o personagem equipado\n**!inventario** ou **!i** - Mostra os personagens que tu tem", inline=False)
    embed.add_field(name="⚔ Como funciona a batalha", value="**Vida: 200**\n**ATACAR:** dado 1-10, dano = **dado x ataque**\n**DEFENDER:** dado 1-10, escudo = **dado x defesa**\n**CURAR:** dado 1-5, cura = **dado x cura**", inline=False)
    embed.add_field(name="✨ Especial da Anne", value="CURAR 2 rounds seguidos = +10% cura por 2 rounds", inline=False)
    embed.add_field(name="✨ Especial do Ming Har", value="-15% de dano nos primeiros 2 ataques do oponente", inline=False)
    embed.add_field(name="🏆 Rank / Perfil", value="**!rank** - Top 10\n**!perfil** - Teu perfil\n**!perfil @pessoa** - Perfil de outro", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="rank")
async def rank(ctx):
    placar = carregar_placar()
    if not placar:
        await ctx.send("Ninguem jogou X1 ainda! Manda um `!x1` pra começar!")
        return
    ranking = sorted(placar.values(), key=lambda x: (x["vitorias"], -x["derrotas"]), reverse=True)[:10]
    embed = discord.Embed(title="🏆 **RANK - TOP 10 DO X1**", description="Quem mais vence no X1:", color=0xFFD700)
    texto = ""
    medalhas = ["🥇", "🥈", "🥉"]
    for i, dados in enumerate(ranking):
        medalha = medalhas[i] if i < 3 else f"{i+1}."
        texto += f"{medalha} **{dados['nome']}** - Vitorias: **{dados['vitorias']}** | Derrotas: {dados['derrotas']}\n"
    embed.add_field(name="Ranking", value=texto, inline=False)
    embed.set_footer(text="Pra ver teu perfil: !perfil")
    await ctx.send(embed=embed)

@bot.command(name="perfil")
async def perfil(ctx, member: discord.Member = None):
    alvo = member or ctx.author
    placar = carregar_placar()
    dados = pegar_stats(placar, alvo)
    p = personagem_equipado_de(alvo.id)
    inv = dados_usuario(alvo.id)
    total = dados['vitorias'] + dados['derrotas']
    aproveitamento = round(dados['vitorias'] / total * 100) if total > 0 else 0
    embed = discord.Embed(title=f"👤 **PERFIL - {alvo.display_name.upper()}**", description=f"**{alvo.mention}**", color=0xFF8000)
    embed.add_field(name="🏆 Vitorias", value=f"**{dados['vitorias']}**", inline=True)
    embed.add_field(name="💀 Derrotas", value=f"**{dados['derrotas']}**", inline=True)
    embed.add_field(name="📊 Aproveitamento", value=f"**{aproveitamento}%** ({total} jogos)", inline=False)
    embed.add_field(name="👤 Personagem equipado", value=f"**{p['nome']}** - ⚔ {p['ataque']} | 🛡 {p['defesa']} | 💚 {p['cura']}", inline=False)
    embed.add_field(name="🎒 Inventario", value=f"**{len(inv['inventario'])}/3** personagens", inline=False)
    embed.set_footer(text="Pra ver o rank: !rank | Pra trocar personagem: !i")
    if p.get("imagem"):
        embed.set_image(url=p["imagem"])
    await ctx.send(embed=embed)

@bot.command(name="limitar")
@commands.has_permissions(administrator=True)
async def limitar(ctx, *, argumento: str = None):
    texto = (argumento or "").strip()
    if not texto:
        atual = canal_limitado(ctx.guild.id) if ctx.guild else None
        if atual:
            await ctx.send(f"ℹ O bot ta limitado so no canal <#{atual}>.\nPra trocar: `!limitar #outro-canal`\nPra tirar o limite: `!limitar off`")
        else:
            await ctx.send(f"ℹ O bot **nao ta limitado** - ele pode mandar mensagem em qualquer canal.\nPra limitar: `!limitar #canal-do-x1`")
        return
    if texto.lower() in ("off", "desligar", "tirar", "liberar", "nenhum", "0", "remover", "desativar"):
        definir_canal_limitado(ctx.guild.id, None)
        salvar_json(ARQUIVO_CONFIG, carregar_json(ARQUIVO_CONFIG))
        await ctx.send(f"✅ **Limite removido!** Agora o bot pode mandar mensagem em **qualquer canal**.")
        return
    canal = None
    if texto.startswith("<#") and texto.endswith(">"):
        try:
            canal_id = int(texto[2:-1])
            canal = ctx.guild.get_channel(canal_id) if ctx.guild else None
        except Exception:
            canal = None
    elif texto.isdigit():
        try:
            canal = ctx.guild.get_channel(int(texto)) if ctx.guild else None
        except Exception:
            canal = None
    elif texto.startswith("#"):
        nome = texto[1:].strip().lower()
        if ctx.guild:
            for c in ctx.guild.text_channels:
                if c.name.lower() == nome:
                    canal = c
                    break
    else:
        if ctx.guild:
            for c in ctx.guild.text_channels:
                if c.name.lower() == texto.lower():
                    canal = c
                    break
    if canal is None:
        await ctx.send(f"{ctx.author.mention} Nao achei esse canal!\nUsa assim: `!limitar #canal-do-x1` ou `!limitar off`")
        return
    definir_canal_limitado(ctx.guild.id, canal.id)
    salvar_json(ARQUIVO_CONFIG, carregar_json(ARQUIVO_CONFIG))
    await ctx.send(f"🔒 **Bot limitado!** Agora o bot so vai mandar mensagem no canal {canal.mention}.\nPra tirar o limite: `!limitar off`")

@bot.command(name="backup")
@commands.has_permissions(administrator=True)
async def backup(ctx):
    cfg = carregar_json(ARQUIVO_CONFIG)
    placar = carregar_json(ARQUIVO_PLACAR)
    inv = carregar_json(ARQUIVO_PERSONAGENS)
    salvar_json(ARQUIVO_CONFIG, cfg)
    salvar_json(ARQUIVO_PLACAR, placar)
    salvar_json(ARQUIVO_PERSONAGENS, inv)
    if not GITHUB_TOKEN:
        await ctx.send("⚠ **Backup salvo so local!** Falta botar o `GITHUB_TOKEN` no Render.")
        return
    await ctx.send("✅ **Backup feito!** Salvo no GitHub.")

@bot.command(name="restaurar")
@commands.has_permissions(administrator=True)
async def restaurar(ctx):
    _CACHE_GITHUB.clear()
    cfg = carregar_json(ARQUIVO_CONFIG)
    placar = carregar_json(ARQUIVO_PLACAR)
    inv = carregar_json(ARQUIVO_PERSONAGENS)
    await ctx.send(f"✅ **Restaurado do GitHub!**\n- Servidores: **{len(cfg)}**\n- Placar: **{len(placar)}**\n- Inventario: **{len(inv)}**")

@limitar.error
async def limitar_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f"{ctx.author.mention} So **ADM** pode usar esse comando! 🔒")

@bot.check
async def so_no_canal_limitado(ctx):
    if ctx.guild is None:
        return True
    if ctx.command and ctx.command.name == "limitar":
        return True
    limite = canal_limitado(ctx.guild.id)
    if limite and ctx.channel.id != limite:
        return False
    return True

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        return
    raise error

# ===== RESGATAR PERSONAGEM =====
async def tentar_resgatar(ctx, user, codigo):
    codigo = codigo.strip().upper()
    pid = CODIGO_PARA_PERSONAGEM.get(codigo)
    if not pid:
        await ctx.send(f"{user.mention} Codigo invalido! Ex: `!rp ANNE-BASTARD`")
        return
    p = personagem_por_id(pid)
    dados = dados_usuario(user.id)
    if codigo in [c.upper() for c in dados["codigos_usados"]]:
        await ctx.send(f"{user.mention} Tu ja usou esse codigo! Ja tem a **{p['nome']}**.")
        return
    if pid in dados["inventario"]:
        await ctx.send(f"{user.mention} Tu ja tem a **{p['nome']}**! Da um `!i` pra ver.")
        return
    if len(dados["inventario"]) >= MAX_INVENTARIO:
        ARQUIVO_PENDENTE[str(user.id)] = codigo
        nomes = [personagem_por_id(x)["nome"] for x in dados["inventario"]]
        embed = discord.Embed(title="⚠ INVENTARIO CHEIO!", description=f"{user.mention} tu ja tem **3 personagens**!\nPra resgatar a **{p['nome']}**, exclui um:\n\n**{', '.join(nomes)}**", color=0xFF0000)
        await ctx.send(embed=embed, view=ExcluirParaResgatarView(user, p))
        return
    dados["inventario"].append(pid)
    dados["codigos_usados"].append(codigo)
    if not dados["equipado"]:
        dados["equipado"] = pid
    salvar_dados_usuario(user.id, dados)
    embed = embed_personagem(p, titulo="🎉 PERSONAGEM RESGATADO!")
    embed.description = f"{user.mention} tu resgatou a **{p['nome']}**!\n\n" + embed.description
    await ctx.send(embed=embed)

class ExcluirParaResgatarView(discord.ui.View):
    def __init__(self, user, personagem_novo):
        super().__init__(timeout=120)
        self.user = user
        self.personagem_novo = personagem_novo
        dados = dados_usuario(user.id)
        for pid in dados["inventario"]:
            p = personagem_por_id(pid)
            btn = discord.ui.Button(label=f"Excluir {p['nome']}", style=discord.ButtonStyle.red)
            async def callback(interaction, pid=pid, p=p):
                if interaction.user.id != self.user.id:
                    await interaction.response.send_message("So o dono pode excluir!", ephemeral=True)
                    return
                await interaction.response.defer()
                dados2 = dados_usuario(self.user.id)
                if pid in dados2["inventario"]:
                    dados2["inventario"].remove(pid)
                if dados2.get("equipado") == pid:
                    dados2["equipado"] = dados2["inventario"][0] if dados2["inventario"] else None
                codigo = ARQUIVO_PENDENTE.pop(str(self.user.id), self.personagem_novo["codigo"])
                dados2["inventario"].append(self.personagem_novo["id"])
                if codigo.upper() not in [c.upper() for c in dados2["codigos_usados"]]:
                    dados2["codigos_usados"].append(codigo.upper())
                if not dados2["equipado"]:
                    dados2["equipado"] = self.personagem_novo["id"]
                salvar_dados_usuario(self.user.id, dados2)
                for child in self.children:
                    child.disabled = True
                try:
                    await interaction.edit_original_response(view=self)
                except:
                    pass
                embed = embed_personagem(self.personagem_novo, titulo="🎉 PERSONAGEM RESGATADO!")
                embed.description = f"{self.user.mention} excluiu a **{p['nome']}** e resgatou a **{self.personagem_novo['nome']}**!\n\n" + embed.description
                await interaction.followup.send(embed=embed)
            btn.callback = callback
            self.add_item(btn)

@bot.command(name="resgatarpersonagem", aliases=["rp"])
async def resgatarpersonagem(ctx, *, codigo: str = None):
    if not codigo:
        await ctx.send(f"{ctx.author.mention} Usa assim: `!rp CODIGO`")
        return
    await tentar_resgatar(ctx, ctx.author, codigo)

@bot.command(name="personagem", aliases=["p"])
async def personagem_cmd(ctx):
    p = personagem_equipado_de(ctx.author.id)
    dados = dados_usuario(ctx.author.id)
    embed = embed_personagem(p, titulo=f"👤 PERSONAGEM DE {ctx.author.display_name.upper()}")
    if dados["equipado"]:
        embed.description += "\n\n✅ **Equipado pra batalhar.**"
    else:
        embed.description += "\n\nℹ Ta jogando com o **Padrao**. Resgata com `!rp CODIGO`"
    embed.set_footer(text="Pra trocar: !i e clica no personagem")
    await ctx.send(embed=embed)

@bot.command(name="inventario", aliases=["i"])
async def inventario_cmd(ctx):
    dados = dados_usuario(ctx.author.id)
    if not dados["inventario"]:
        embed = discord.Embed(title=f"🎒 INVENTARIO DE {ctx.author.display_name.upper()}", description="Tu ainda nao tem nenhum personagem!\n\nTa jogando com o **Padrao: 6 / 6 / 6**.\nPede um codigo e usa `!rp CODIGO`", color=0xFF8000)
        await ctx.send(embed=embed)
        return
    embed = discord.Embed(title=f"🎒 INVENTARIO DE {ctx.author.display_name.upper()} ({len(dados['inventario'])}/3)", description="Teus personagens:\n\n", color=0xFF8000)
    texto = ""
    for pid in dados["inventario"]:
        p = personagem_por_id(pid)
        equipado = " ✅ **EQUIPADO**" if dados["equipado"] == pid else ""
        texto += f"**{p['nome']}** - ⚔ {p['ataque']} | 🛡 {p['defesa']} | 💚 {p['cura']}{equipado}\n✨ {p['especial']}\n\n"
    embed.description += texto
    embed.set_footer(text="Clica no botao pra equipar")
    await ctx.send(embed=embed, view=EquiparView(ctx.author))

class EquiparView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=120)
        self.user = user
        dados = dados_usuario(user.id)
        for pid in dados["inventario"]:
            p = personagem_por_id(pid)
            label = f"{p['nome']}" + (" ✅" if dados["equipado"] == pid else "")
            btn = discord.ui.Button(label=label[:80], style=discord.ButtonStyle.green if dados["equipado"] == pid else discord.ButtonStyle.blurple)
            async def callback(interaction, pid=pid, p=p):
                if interaction.user.id != self.user.id:
                    await interaction.response.send_message("So o dono pode equipar!", ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                dados2 = dados_usuario(self.user.id)
                dados2["equipado"] = pid
                salvar_dados_usuario(self.user.id, dados2)
                await interaction.followup.send(f"✅ Tu equipou a **{p['nome']}**! Da um `!p` pra ver.", ephemeral=True)
            btn.callback = callback
            self.add_item(btn)

# ===== X1 =====
def barra_vida(vida):
    cheio = max(0, min(10, int(vida / 20)))
    return "❤️" * cheio + "🖤" * (10 - cheio) + f" **{vida}/200**"

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
    jogo["resolvendo"] = False
    jogo["painel_rolar_enviado"] = False
    p0, p1 = jogo["jogadores"]
    c0 = jogo["personagens"][0]
    c1 = jogo["personagens"][1]
    embed = discord.Embed(title=f"⚔ **X1 - ROUND {jogo['round']}** ⚔", description="**ESCOLHAM AO MESMO TEMPO!**\nNinguem ve a escolha do outro ate rolar!", color=0xFF8000)
    embed.add_field(name=f"🔥 **{p0.display_name}** - {c0['nome']}", value=f"{barra_vida(jogo['vida'][0])}\n⚔ **Ataque {c0['ataque']}** | 🛡 **Defesa {c0['defesa']}** | 💚 **Cura {c0['cura']}**", inline=False)
    embed.add_field(name=f"🔥 **{p1.display_name}** - {c1['nome']}", value=f"{barra_vida(jogo['vida'][1])}\n⚔ **Ataque {c1['ataque']}** | 🛡 **Defesa {c1['defesa']}** | 💚 **Cura {c1['cura']}**", inline=False)
    embed.add_field(name="📜 **Como funciona**", value="**ATACAR:** dado 1-10, dano = **dado x ataque**\n**DEFENDER:** dado 1-10, escudo = **dado x defesa**\n**CURAR:** dado 1-5, cura = **dado x cura**", inline=False)
    embed.set_footer(text="Escolhe escondido e depois rola junto!")
    view = EscolhaSimultaneaView(jogo, canal)
    msg = await canal.send(embed=embed, view=view)
    jogo["painel_msg"] = msg
    jogo["view_atual"] = view

class AceitarView(discord.ui.View):
    def __init__(self, desafiante, canal):
        super().__init__(timeout=60)
        self.desafiante = desafiante
        self.canal = canal
        self.aceito = False
    @discord.ui.button(label="ACEITAR X1", style=discord.ButtonStyle.green)
    async def aceitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        global x1_ativo, x1_jogo
        # RESPOSTA IMEDIATA PRA NAO DAR TIMEOUT
        await interaction.response.defer()

        async with x1_lock:
            if interaction.user.id == self.desafiante.id:
                await interaction.followup.send("Tu nao pode aceitar teu proprio X1", ephemeral=True)
                return
            if self.aceito:
                return
            self.aceito = True
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except:
                pass
        
        jogador2 = interaction.user
        await interaction.followup.send(f"{jogador2.mention} **ACEITOU!** Agora escolham o personagem!")
        try:
            await interaction.message.delete()
        except:
            pass

        x1_jogo = {"jogadores": [self.desafiante, jogador2], "vida": [200, 200], "escolhas": {}, "dados": {}, "round": 1, "painel_msg": None, "resolvendo": False, "painel_rolar_enviado": False, "rounds_resolvidos": set(), "personagens": [PERSONAGEM_PADRAO, PERSONAGEM_PADRAO], "equip_choices": {}, "cura_consecutiva": [0, 0], "buff_cura": [0, 0], "ataques_recebidos": [0, 0]}
        
        await self.canal.send(f"⚔ **X1 VAI COMECAR!**\n{self.desafiante.mention} VS {jogador2.mention}\nCada um escolhe o personagem no painel dele ai embaixo!")
        for idx, jogador in enumerate([self.desafiante, jogador2]):
            dados = dados_usuario(jogador.id)
            if not dados["inventario"]:
                x1_jogo["equip_choices"][idx] = "padrao"
                x1_jogo["personagens"][idx] = PERSONAGEM_PADRAO
                await self.canal.send(f"{jogador.mention} tu nao tem personagem, vai de **Padrao (6 / 6 / 6)**!")
            else:
                embed = discord.Embed(title=f"👤 **{jogador.display_name}, ESCOLHE TEU PERSONAGEM!**", description="Clica no personagem que tu quer usar nesse X1:", color=0xFF8000)
                texto = ""
                for pid in dados["inventario"]:
                    p = personagem_por_id(pid)
                    texto += f"**{p['nome']}** - ⚔ {p['ataque']} | 🛡 {p['defesa']} | 💚 {p['cura']}\n"
                texto += "\n**Personagem Padrao** - ⚔ 6 | 🛡 6 | 💚 6"
                embed.description += "\n\n" + texto
                view = EquipX1View(x1_jogo, self.canal, idx)
                await self.canal.send(embed=embed, view=view)
        
        if len(x1_jogo["equip_choices"]) == 2:
            await self.canal.send(f"⚔ **X1 COMECOU!**\n{self.desafiante.mention} VS {jogador2.mention}\nCada um com **200 de vida**.")
            await enviar_painel_escolha(self.canal, x1_jogo)

    async def on_timeout(self):
        global x1_ativo
        if not self.aceito:
            await self.canal.send("Ninguem aceitou o X1. Cancelado")
            x1_ativo = False

class EquipX1View(discord.ui.View):
    def __init__(self, jogo, canal, jogador_idx):
        super().__init__(timeout=90)
        self.jogo = jogo
        self.canal = canal
        self.jogador_idx = jogador_idx
        jogador = jogo["jogadores"][jogador_idx]
        dados = dados_usuario(jogador.id)
        for pid in dados["inventario"]:
            p = personagem_por_id(pid)
            btn = discord.ui.Button(label=p["nome"][:80], style=discord.ButtonStyle.blurple)
            async def callback(interaction, pid=pid, p=p):
                await self.equipar(interaction, pid, p)
            btn.callback = callback
            self.add_item(btn)
        btn_padrao = discord.ui.Button(label="Personagem Padrao (6/6/6)", style=discord.ButtonStyle.gray)
        async def callback_padrao(interaction):
            await self.equipar(interaction, "padrao", PERSONAGEM_PADRAO)
        btn_padrao.callback = callback_padrao
        self.add_item(btn_padrao)

    async def equipar(self, interaction, pid, p):
        jogador = self.jogo["jogadores"][self.jogador_idx]
        if interaction.user.id != jogador.id:
            await interaction.response.send_message("Esse painel nao e teu!", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        async with x1_lock:
            if self.jogador_idx in self.jogo["equip_choices"]:
                await interaction.followup.send("Tu ja escolheu!", ephemeral=True)
                return
            self.jogo["equip_choices"][self.jogador_idx] = pid
            self.jogo["personagens"][self.jogador_idx] = personagem_por_id(pid)
            ambos = len(self.jogo["equip_choices"]) == 2
        
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass
        await interaction.followup.send(f"✅ {jogador.mention} equipou a **{p['nome']}**!", ephemeral=True)

        if ambos:
            j0, j1 = self.jogo["jogadores"]
            c0, c1 = self.jogo["personagens"]
            await self.canal.send(f"⚔ **X1 COMECOU!**\n{j0.mention} com **{c0['nome']}** VS {j1.mention} com **{c1['nome']}**\nCada um com **200 de vida**.")
            await enviar_painel_escolha(self.canal, self.jogo)

class EscolhaSimultaneaView(discord.ui.View):
    def __init__(self, jogo, canal):
        super().__init__(timeout=120)
        self.jogo = jogo
        self.canal = canal

    async def escolher(self, interaction, escolha):
        await interaction.response.defer(ephemeral=True)
        
        ids = [p.id for p in self.jogo["jogadores"]]
        if interaction.user.id not in ids:
            await interaction.followup.send("So quem ta no X1 pode clicar!", ephemeral=True)
            return
        idx = ids.index(interaction.user.id)

        msg_extra = ""
        async with x1_lock:
            if idx in self.jogo["escolhas"]:
                await interaction.followup.send("Tu ja escolheu! Espera o outro.", ephemeral=True)
                return
            self.jogo["escolhas"][idx] = escolha
            if escolha == "curar":
                self.jogo["cura_consecutiva"][idx] += 1
                if self.jogo["cura_consecutiva"][idx] >= 2 and self.jogo["buff_cura"][idx] == 0:
                    self.jogo["buff_cura"][idx] = 2
                    self.jogo["cura_consecutiva"][idx] = 0
                    msg_extra = "\n✨ **ESPECIAL ATIVADO!** +10% cura por 2 rounds!"
            else:
                self.jogo["cura_consecutiva"][idx] = 0
            ambos_escolheram = len(self.jogo["escolhas"]) == 2
            if ambos_escolheram and self.jogo.get("painel_rolar_enviado"):
                ambos_escolheram = False
            if ambos_escolheram:
                self.jogo["painel_rolar_enviado"] = True

        nomes = {"atacar": "ATACAR", "defender": "DEFENDER", "curar": "CURAR"}
        await interaction.followup.send(f"Voce escolheu **{nomes[escolha]}**... ninguem viu. Espera o outro.{msg_extra}", ephemeral=True)

        if ambos_escolheram:
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except:
                pass
            await apagar_painel_antigo(self.jogo)
            embed = discord.Embed(title="🎲 **HORA DE ROLAR O DADO!** 🎲", description="**Os 2 ja escolheram!** Agora rolem o dado.", color=0xFFD700)
            embed.add_field(name="Jogadores", value=f"{self.jogo['jogadores'][0].mention} e {self.jogo['jogadores'][1].mention} - cliquem em **ROLAR!**", inline=False)
            msg = await self.canal.send(embed=embed, view=RolarSimultaneoView(self.jogo, self.canal))
            self.jogo["painel_msg"] = msg

    @discord.ui.button(label="⚔ ATACAR", style=discord.ButtonStyle.red)
    async def atacar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.escolher(interaction, "atacar")
    @discord.ui.button(label="🛡 DEFENDER", style=discord.ButtonStyle.blurple)
    async def defender(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.escolher(interaction, "defender")
    @discord.ui.button(label="💚 CURAR", style=discord.ButtonStyle.green)
    async def curar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.escolher(interaction, "curar")

class RolarSimultaneoView(discord.ui.View):
    def __init__(self, jogo, canal):
        super().__init__(timeout=120)
        self.jogo = jogo
        self.canal = canal

    @discord.ui.button(label="🎲 ROLAR", style=discord.ButtonStyle.green)
    async def rolar(self, interaction: discord.Interaction, button: discord.ui.Button):
        global x1_ativo
        await interaction.response.defer(ephemeral=True)

        ids = [p.id for p in self.jogo["jogadores"]]
        if interaction.user.id not in ids:
            await interaction.followup.send("So quem ta no X1 pode rolar!", ephemeral=True)
            return
        idx = ids.index(interaction.user.id)

        async with x1_lock:
            if idx in self.jogo["dados"]:
                await interaction.followup.send("Tu ja rolou! Espera o outro.", ephemeral=True)
                return
            if self.jogo.get("resolvendo"):
                await interaction.followup.send("Calma, ja to resolvendo o round!", ephemeral=True)
                return
            escolha = self.jogo["escolhas"].get(idx, "atacar")
            if escolha == "curar":
                dado = random.randint(1, 5)
            else:
                dado = random.randint(1, 10)
            self.jogo["dados"][idx] = dado
            ambos_rolaram = len(self.jogo["dados"]) == 2
            if ambos_rolaram and self.jogo["round"] in self.jogo.get("rounds_resolvidos", set()):
                ambos_rolaram = False
            if ambos_rolaram:
                self.jogo["resolvendo"] = True
                self.jogo["rounds_resolvidos"].add(self.jogo["round"])

        await interaction.followup.send(f"Voce rolou **{dado}**! Espera o outro rolar.", ephemeral=True)

        if ambos_rolaram:
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except:
                pass
            await self.resolver_round()

    async def resolver_round(self):
        global x1_ativo
        jogo = self.jogo
        canal = self.canal
        await apagar_painel_antigo(jogo)
        p0, p1 = jogo["jogadores"]
        c0, c1 = jogo["personagens"]
        e0, e1 = jogo["escolhas"].get(0, "atacar"), jogo["escolhas"].get(1, "atacar")
        d0, d1 = jogo["dados"].get(0, 1), jogo["dados"].get(1, 1)
        escudo = [0, 0]
        cura = [0, 0]
        dano_bruto = [0, 0]
        buff_usado = [False, False]

        for i, (esc, dad, char) in enumerate([(e0, d0, c0), (e1, d1, c1)]):
            if esc == "defender":
                escudo[i] = dad * char["defesa"]
            elif esc == "curar":
                base = dad * char["cura"]
                if jogo["buff_cura"][i] > 0:
                    base = round(base * 1.10)
                    buff_usado[i] = True
                    jogo["buff_cura"][i] -= 1
                cura[i] = base
            elif esc == "atacar":
                dano_bruto[i] = dad * char["ataque"]

        dano_final = [0, 0]
        dano_final[0] = max(0, dano_bruto[1] - escudo[0])
        dano_final[1] = max(0, dano_bruto[0] - escudo[1])

        especial_ming = [False, False]
        for i, char in enumerate([c0, c1]):
            atacante = 1 - i
            esc_atacante = e0 if atacante == 0 else e1
            if char["id"] == "minghar" and jogo["ataques_recebidos"][i] < 2:
                if esc_atacante == "atacar" and dano_final[i] > 0:
                    dano_final[i] = round(dano_final[i] * 0.85)
                    especial_ming[i] = True
        if e0 == "atacar":
            jogo["ataques_recebidos"][1] += 1
        if e1 == "atacar":
            jogo["ataques_recebidos"][0] += 1

        escudo_usado = [min(escudo[0], dano_bruto[1]), min(escudo[1], dano_bruto[0])]
        jogo["vida"][0] = max(0, min(200, jogo["vida"][0] - dano_final[0] + cura[0]))
        jogo["vida"][1] = max(0, min(200, jogo["vida"][1] - dano_final[1] + cura[1]))

        nomes = {"atacar": "ATACOU ⚔", "defender": "DEFENDEU 🛡", "curar": "CUROU 💚"}
        embed = discord.Embed(title=f"💥 **RESULTADO DO ROUND {jogo['round']}!** 💥", color=0xFF0000)
        txt0 = f"**Dado:** {d0}\n**Escudo:** {escudo[0]}\n**Cura:** +{cura[0]}" + (" ✨ **+10% especial!**" if buff_usado[0] else "") + (" 🛡 **-15% Ming Har!**" if especial_ming[0] else "") + f"\n**Dano que deu:** {dano_bruto[0]} (segurado: {escudo_usado[1]})\n**Dano que tomou:** {dano_final[0]}"
        txt1 = f"**Dado:** {d1}\n**Escudo:** {escudo[1]}\n**Cura:** +{cura[1]}" + (" ✨ **+10% especial!**" if buff_usado[1] else "") + (" 🛡 **-15% Ming Har!**" if especial_ming[1] else "") + f"\n**Dano que deu:** {dano_bruto[1]} (segurado: {escudo_usado[0]})\n**Dano que tomou:** {dano_final[1]}"
        embed.add_field(name=f"**{p0.display_name}** - {nomes[e0]} ({c0['nome']})", value=txt0, inline=False)
        embed.add_field(name=f"**{p1.display_name}** - {nomes[e1]} ({c1['nome']})", value=txt1, inline=False)
        embed.add_field(name="❤ **Vida agora**", value=f"**{p0.display_name}:** {barra_vida(jogo['vida'][0])}\n**{p1.display_name}:** {barra_vida(jogo['vida'][1])}", inline=False)
        await canal.send(embed=embed)

        v0_morto = jogo["vida"][0] <= 0
        v1_morto = jogo["vida"][1] <= 0
        if v0_morto and v1_morto:
            await canal.send("🤝 **EMPATE!** Os 2 cairam ao mesmo tempo!")
            x1_ativo = False
            return
        if v0_morto:
            v_stats, d_stats = registrar_resultado(p1, p0)
            await canal.send(embed=discord.Embed(title="🏆 **FIM DO X1!** 🏆", description=f"{p1.mention} **VENCEU!!!**\n\n**{p1.display_name}** ({c1['nome']}) - V: {v_stats['vitorias']} D: {v_stats['derrotas']}\n**{p0.display_name}** ({c0['nome']}) - V: {d_stats['vitorias']} D: {d_stats['derrotas']}", color=0xFFD700))
            x1_ativo = False
            return
        if v1_morto:
            v_stats, d_stats = registrar_resultado(p0, p1)
            await canal.send(embed=discord.Embed(title="🏆 **FIM DO X1!** 🏆", description=f"{p0.mention} **VENCEU!!!**\n\n**{p0.display_name}** ({c0['nome']}) - V: {v_stats['vitorias']} D: {v_stats['derrotas']}\n**{p1.display_name}** ({c1['nome']}) - V: {d_stats['vitorias']} D: {d_stats['derrotas']}", color=0xFFD700))
            x1_ativo = False
            return
        jogo["round"] += 1
        await asyncio.sleep(1)
        await enviar_painel_escolha(canal, jogo)

@bot.command(name="x1")
async def x1(ctx):
    global x1_ativo
    if x1_ativo:
        await ctx.send("Ja tem um X1 rolando! Espera acabar", delete_after=5)
        return
    x1_ativo = True
    embed = discord.Embed(title="⚔ **ALGUEM ACEITA UM X1?** ⚔", description=f"{ctx.author.mention} ta chamando pro X1!\n\n**Regras:**\n❤ **200 de vida**\n⚔ **ATACAR:** dado 1-10, dano = **dado x ataque**\n🛡 **DEFENDER:** dado 1-10, escudo = **dado x defesa**\n💚 **CURAR:** dado 1-5, cura = **dado x cura**\n\nOs 2 escolhem juntos, os 2 rolam juntos.", color=0xFF8000)
    embed.set_footer(text="A primeira pessoa que clicar em ACEITAR entra no X1!")
    view = AceitarView(ctx.author, ctx.channel)
    await ctx.send(embed=embed, view=view)

keep_alive()
bot.run(TOKEN)
