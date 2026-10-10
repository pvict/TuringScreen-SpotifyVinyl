"""Desenho da janela: superfícies suaves e tipografia FreeType com cache.

Não importa o motor da tela nem acessa USB, áudio ou OpenRGB.
"""
import ctypes
import math
import os
import queue
import threading
import tkinter as tk
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageTk

RAIZ = Path(__file__).resolve().parent
ESCALA_TEXTO = 3
FUNDO = "#e9e9e5"
TEXTO = "#303238"
SECUNDARIO = "#696c73"


def configurar_dpi():
    """Evita que o Windows amplie uma imagem de baixa resolução da janela."""
    if os.name != "nt":
        return
    try:
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        if user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (OSError, AttributeError):
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(1)
    except (OSError, AttributeError):
        pass


class RelogioAnimacaoWindows:
    """Precisão de 1 ms só enquanto a janela possui uma animação ativa."""
    def __init__(self):
        self.tokens = set()
        self.ativo = self.solicitado = self.fechado = False
        self.winmm = None
        if os.name == "nt":
            try:
                self.winmm = ctypes.WinDLL("winmm")
                for nome in ("timeBeginPeriod", "timeEndPeriod"):
                    funcao = getattr(self.winmm, nome)
                    funcao.argtypes = [ctypes.c_uint]
                    funcao.restype = ctypes.c_uint
            except (OSError, AttributeError):
                self.winmm = None

    def marcar(self, chave, ativo):
        if self.fechado:
            return
        if ativo:
            self.tokens.add(chave)
        else:
            self.tokens.discard(chave)
        solicitado = bool(self.tokens)
        if solicitado == self.solicitado:
            return
        self.solicitado = solicitado
        if self.winmm:
            if solicitado:
                self.ativo = self.winmm.timeBeginPeriod(1) == 0
            elif self.ativo:
                self.winmm.timeEndPeriod(1)
                self.ativo = False

    def fechar(self):
        self.fechado = True
        self.tokens.clear()
        if self.ativo and self.winmm:
            self.winmm.timeEndPeriod(1)
        self.ativo = self.solicitado = False


@lru_cache(maxsize=48)
def fonte_freetype(tamanho, peso=450, serif=False, escala=ESCALA_TEXTO):
    caminho = RAIZ / "assets" / "fonts" / ("fraunces.ttf" if serif else "dmsans.ttf")
    try:
        fonte = ImageFont.truetype(str(caminho), round(tamanho * escala))
        try:
            eixos = fonte.get_variation_axes()
            valores = []
            for eixo in eixos:
                nome = eixo["name"].decode("ascii", errors="ignore").lower()
                valor = (peso if "weight" in nome else tamanho if "optical" in nome
                         else 18 if "softness" in nome else eixo["default"])
                valores.append(min(eixo["maximum"], max(eixo["minimum"], valor)))
            fonte.set_variation_by_axes(valores)
        except (OSError, AttributeError):
            pass
        return fonte
    except OSError:
        # Continua legível mesmo se a pasta de fontes não for copiada.
        caminho = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        try:
            return ImageFont.truetype(str(caminho), round(tamanho * escala))
        except OSError:
            return ImageFont.load_default(size=round(tamanho * escala))


class FonteInterface:
    def __init__(self, tamanho=14, peso=450, serif=False):
        self.tamanho, self.peso, self.serif = tamanho, peso, serif

    @property
    def chave(self):
        return self.tamanho, self.peso, self.serif

    def measure(self, texto):
        fonte = fonte_freetype(*self.chave)
        return math.ceil(fonte.getlength(str(texto)) / ESCALA_TEXTO)


def _quebrar_texto(texto, fonte, largura):
    if not largura:
        return texto
    linhas = []
    for paragrafo in texto.split("\n"):
        linha = ""
        for palavra in paragrafo.split(" "):
            if fonte.getlength(palavra) > largura:
                if linha:
                    linhas.append(linha)
                    linha = ""
                parte = ""
                for letra in palavra:
                    if parte and fonte.getlength(parte + letra) > largura:
                        linhas.append(parte)
                        parte = ""
                    parte += letra
                linha = parte
                continue
            proposta = f"{linha} {palavra}" if linha else palavra
            if linha and fonte.getlength(proposta) > largura:
                linhas.append(linha)
                linha = palavra
            else:
                linha = proposta
        linhas.append(linha)
    return "\n".join(linhas)


def limitar_linhas(texto, fonte, largura, limite=2):
    ft = fonte_freetype(*fonte.chave)
    linhas = _quebrar_texto(str(texto), ft, largura * ESCALA_TEXTO).split("\n")
    if len(linhas) > limite:
        linhas = linhas[:limite]
        ultima = linhas[-1].rstrip()
        while ultima and fonte.measure(ultima + "…") > largura:
            ultima = ultima[:-1]
        linhas[-1] = ultima + "…"
    return "\n".join(linhas)


@lru_cache(maxsize=256)
def texto_suave(texto, chave=(14, 450, False), cor=TEXTO, largura=0, justificar="left"):
    """Rasteriza uma vez a 3× e reduz com Lanczos; não depende do GDI do Tk."""
    fonte = fonte_freetype(*chave)
    escala = ESCALA_TEXTO
    texto = _quebrar_texto(str(texto), fonte, largura * escala)
    if not texto:
        return Image.new("RGBA", (1, 1))
    desenho = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    espacamento = round(chave[0] * escala * 0.23)
    caixa = desenho.multiline_textbbox((0, 0), texto, font=fonte, spacing=espacamento,
                                       align=justificar)
    w, h = math.ceil(caixa[2] - caixa[0]) + 2 * escala, math.ceil(caixa[3] - caixa[1]) + 2 * escala
    img = Image.new("RGBA", (max(1, w), max(1, h)))
    ImageDraw.Draw(img).multiline_text((escala - caixa[0], escala - caixa[1]), texto,
                                       font=fonte, fill=cor, spacing=espacamento, align=justificar)
    return img.resize((math.ceil(w / escala), math.ceil(h / escala)), Image.Resampling.LANCZOS)


class CanvasSuave(tk.Canvas):
    """Mantém as operações de texto usadas pelo app, trocando só sua pintura."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._textos = {}
        self._imagens = {}
        self._fotos = OrderedDict()
        self._fundo_pil = None
        self._fundo_item = None

    def _foto(self, imagem):
        chave = id(imagem)
        if chave not in self._fotos:
            self._fotos[chave] = (imagem, ImageTk.PhotoImage(imagem, master=self))
        self._fotos.move_to_end(chave)
        while len(self._fotos) > 48:
            self._fotos.popitem(last=False)
        return self._fotos[chave][1]

    def imagem(self, x, y, imagem, **opcoes):
        foto = self._foto(imagem)
        item = super().create_image(x, y, image=foto, **opcoes)
        self._imagens[item] = foto
        return item

    def alterar_imagem(self, item, imagem):
        foto = self._foto(imagem)
        if self._imagens.get(item) is not foto:
            super().itemconfigure(item, image=foto)
            self._imagens[item] = foto

    def definir_fundo(self, imagem):
        """Reproduz o trecho do painel sob o controle, sem blocos retangulares."""
        self._fundo_pil = imagem
        if self._fundo_item is None:
            self._fundo_item = self.imagem(0, 0, imagem, anchor="nw")
            self.tag_lower(self._fundo_item)
        else:
            self.alterar_imagem(self._fundo_item, imagem)

    def create_window(self, x, y, **opcoes):
        janela = opcoes.get("window")
        if isinstance(janela, CanvasSuave) and self._fundo_pil is not None:
            w, h = int(janela["width"]), int(janela["height"])
            janela.configure(bg=self["bg"])
            janela.definir_fundo(self._fundo_pil.crop((int(x), int(y), int(x) + w, int(y) + h)))
        return super().create_window(x, y, **opcoes)

    def create_text(self, x, y, **opcoes):
        fonte = opcoes.pop("font", None)
        if not isinstance(fonte, FonteInterface):
            fonte = FonteInterface()
        atributos = {"text": opcoes.pop("text", ""), "font": fonte,
                     "fill": opcoes.pop("fill", TEXTO), "width": opcoes.pop("width", 0),
                     "justify": opcoes.pop("justify", "left")}
        imagem = texto_suave(atributos["text"], fonte.chave, atributos["fill"],
                            atributos["width"], atributos["justify"])
        item = self.imagem(x, y, imagem, **opcoes)
        self._textos[item] = atributos
        return item

    def itemconfigure(self, item, cnf=None, **opcoes):
        opcoes = {**(cnf or {}), **opcoes}
        ids = (item,) if isinstance(item, int) else self.find_withtag(item)
        if opcoes and any(i in self._textos for i in ids):
            resultado = None
            for i in ids:
                restantes = dict(opcoes)
                if i in self._textos:
                    atributos = self._textos[i]
                    alterado = False
                    for chave in ("text", "font", "fill", "width", "justify"):
                        if chave in restantes:
                            valor = restantes.pop(chave)
                            if atributos[chave] != valor:
                                atributos[chave] = valor
                                alterado = True
                    if alterado:
                        imagem = texto_suave(atributos["text"], atributos["font"].chave,
                                            atributos["fill"], atributos["width"], atributos["justify"])
                        foto = self._foto(imagem)
                        self._imagens[i] = foto
                        restantes["image"] = foto
                if restantes:
                    resultado = super().itemconfigure(i, **restantes)
            return resultado
        return super().itemconfigure(item, cnf, **opcoes)

    itemconfig = itemconfigure

    def delete(self, *itens):
        for item in itens:
            for i in self.find_withtag(item):
                self._textos.pop(i, None)
                self._imagens.pop(i, None)
        return super().delete(*itens)


@lru_cache(maxsize=32)
def _mascaras_superficie(tamanho, raio, pressionado):
    escala = 3
    w, h = tamanho
    mascara = Image.new("L", (w * escala, h * escala))
    ImageDraw.Draw(mascara).rounded_rectangle(
        (8 * escala, 8 * escala, (w - 8) * escala, (h - 8) * escala),
        radius=raio * escala, fill=255)
    mascara = mascara.resize(tamanho, Image.Resampling.LANCZOS)

    def deslocar(dx, dy):
        img = Image.new("L", tamanho)
        img.paste(mascara, (dx, dy))
        return img

    if pressionado:
        escuro = ImageChops.subtract(mascara, deslocar(4, 4)).filter(ImageFilter.GaussianBlur(4))
        claro = ImageChops.subtract(mascara, deslocar(-4, -4)).filter(ImageFilter.GaussianBlur(4))
        escuro = ImageChops.multiply(escuro, mascara)
        claro = ImageChops.multiply(claro, mascara)
    else:
        escuro = deslocar(4, 5).filter(ImageFilter.GaussianBlur(6))
        claro = deslocar(-4, -5).filter(ImageFilter.GaussianBlur(6))
        # Dissolve as sombras antes dos limites do widget, evitando retângulos cortados.
        borda = Image.new("L", tamanho, 255)
        desenho = ImageDraw.Draw(borda)
        for margem in range(8):
            desenho.rectangle((margem, margem, w - margem - 1, h - margem - 1),
                               outline=round(255 * margem / 8))
        escuro = ImageChops.multiply(escuro, borda)
        claro = ImageChops.multiply(claro, borda)
    return mascara, escuro.point(lambda a: round(a * 0.18)), claro.point(lambda a: round(a * 0.76))


@lru_cache(maxsize=96)
def superficie(tamanho, cor=FUNDO, raio=16, pressionado=False):
    """Sombras opostas, sem stroke. As máscaras de blur são compartilhadas."""
    mascara, escuro, claro = _mascaras_superficie(tamanho, raio, pressionado)
    img = Image.new("RGBA", tamanho)
    face = Image.new("RGBA", tamanho, cor)
    face.putalpha(mascara)
    sombra = Image.new("RGBA", tamanho, "#414750")
    sombra.putalpha(escuro)
    luz = Image.new("RGBA", tamanho, "#ffffff")
    luz.putalpha(claro)
    if pressionado:
        return Image.alpha_composite(Image.alpha_composite(face, sombra), luz)
    return Image.alpha_composite(Image.alpha_composite(sombra, luz), face)


@lru_cache(maxsize=1)
def _mascara_spotify():
    with Image.open(RAIZ / "assets" / "icons" / "spotify-white.png") as imagem:
        return imagem.convert("RGBA").getchannel("A")


@lru_cache(maxsize=160)
def icone(nome, cor=TEXTO, lado=24):
    s = 3
    img = Image.new("RGBA", (lado * s, lado * s))
    if nome == "spotify":
        img.paste(cor, (0, 0, lado * s, lado * s))
        img.putalpha(_mascara_spotify().resize(img.size, Image.Resampling.LANCZOS))
        return img.resize((lado, lado), Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(img)
    k = lado * s / 24

    def linha(pontos, largura=1.7):
        xy = [(round(x * k), round(y * k)) for x, y in pontos]
        espessura = max(1, round(largura * k))
        d.line(xy, fill=cor, width=espessura, joint="curve")
        r = espessura / 2
        for x, y in (xy[0], xy[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill=cor)

    def oval(caixa, fill=None, largura=1.6):
        d.ellipse(tuple(round(n * k) for n in caixa), fill=fill,
                  outline=cor if fill is None else None, width=max(1, round(largura * k)))

    if nome == "onda":
        linha([(2 + 20 * i / 48, 12 - 5 * math.sin(2 * math.pi * i / 48)) for i in range(49)])
    elif nome == "video":
        d.rounded_rectangle((2 * k, 4 * k, 22 * k, 20 * k), radius=4 * k,
                            outline=cor, width=round(1.6 * k))
        d.polygon([(10 * k, 8 * k), (16 * k, 12 * k), (10 * k, 16 * k)], fill=cor)
    elif nome == "play":
        d.polygon([(8 * k, 4 * k), (21 * k, 12 * k), (8 * k, 20 * k)], fill=cor)
    elif nome == "stop":
        d.rounded_rectangle((6 * k, 6 * k, 18 * k, 18 * k), radius=3 * k, fill=cor)
    elif nome == "power":
        d.arc((4 * k, 4 * k, 20 * k, 20 * k), 310, 230, fill=cor, width=round(1.8 * k))
        linha([(12, 2), (12, 11)], 1.8)
    elif nome == "fechar":
        linha([(6, 6), (18, 18)])
        linha([(18, 6), (6, 18)])
    elif nome == "gaming":
        linha([(4, 8), (8, 6), (16, 6), (20, 8), (22, 17), (19, 19),
               (15, 15), (9, 15), (5, 19), (2, 17), (4, 8)])
        linha([(6, 10), (6, 14)], 1.4)
        linha([(4, 12), (8, 12)], 1.4)
        oval((15, 9, 17, 11), cor)
        oval((18, 12, 20, 14), cor)
    elif nome == "ajustes":
        for i in range(8):
            a = 2 * math.pi * i / 8
            linha([(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)),
                   (12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a))], 2.4)
        oval((5, 5, 19, 19), largura=2)
        oval((9, 9, 15, 15), largura=1.6)
    return img.resize((lado, lado), Image.Resampling.LANCZOS)


class RotacaoPreview:
    """Só Pillow fora da janela; um pedido e um resultado recentes, sem fila acumulada."""
    def __init__(self, disco):
        self.disco = disco
        self.pedidos = queue.Queue(maxsize=1)
        self.resultados = queue.Queue(maxsize=1)
        self.fechar_evento = threading.Event()
        self.em_render = False
        self.chave = None
        self._recebida = None
        threading.Thread(target=self._executar, name="VinilInterface", daemon=True).start()

    @staticmethod
    def _mais_recente(fila, dado):
        try:
            fila.put_nowait(dado)
        except queue.Full:
            try:
                fila.get_nowait()
            except queue.Empty:
                pass
            try:
                fila.put_nowait(dado)
            except queue.Full:
                pass

    def solicitar(self, chave, capa, angulo, angulo_externo, lado, cor):
        if chave == self.chave:
            return
        self.chave = chave
        self._mais_recente(self.pedidos, (chave, capa, angulo, angulo_externo, lado, cor))

    def receber(self):
        try:
            resultado = self.resultados.get_nowait()
            self._recebida = resultado[0]
            return resultado
        except queue.Empty:
            return None

    def pendente(self):
        return self.chave != self._recebida

    def _executar(self):
        while not self.fechar_evento.is_set():
            pedido = self.pedidos.get()
            if pedido is None:
                return
            self.em_render = True
            try:
                chave, capa, angulo, externo, lado, cor = pedido
                disco = self.disco.rotate(-externo, resample=Image.Resampling.BICUBIC)
                if capa is not None:
                    imagem = capa.rotate(-angulo, resample=Image.Resampling.BICUBIC)
                    if lado != imagem.width:
                        imagem = imagem.resize((lado, lado), Image.Resampling.BICUBIC)
                    disco.alpha_composite(imagem, ((270 - lado) // 2, (270 - lado) // 2))
                else:
                    d = ImageDraw.Draw(disco)
                    d.ellipse((78, 78, 192, 192), fill=cor)
                    d.ellipse((116, 116, 154, 154), fill="#292f39", outline=cor, width=2)
                    d.ellipse((132, 132, 138, 138), fill="#d0d3d7")
                self._mais_recente(self.resultados, (chave, disco))
            finally:
                self.em_render = False

    def fechar(self):
        self.fechar_evento.set()
        self._mais_recente(self.pedidos, None)


class Dica:
    """Explicações sob demanda, em vez de frases permanentes na interface."""
    def __init__(self, widget, texto):
        self.widget, self.texto = widget, texto
        self.job = self.janela = None
        widget.bind("<Enter>", self.agendar, add="+")
        widget.bind("<Leave>", self.fechar, add="+")
        widget.bind("<Button-1>", self.fechar, add="+")
        widget.bind("<Destroy>", self.fechar, add="+")

    def agendar(self, _evento=None):
        self.fechar()
        if self.texto:
            self.job = self.widget.after(650, self.mostrar)

    def mostrar(self):
        self.job = None
        if not self.widget.winfo_exists():
            return
        imagem = texto_suave(self.texto, (12, 450, False), TEXTO, 290)
        w, h = imagem.width + 24, imagem.height + 22
        self.janela = tk.Toplevel(self.widget)
        self.janela.overrideredirect(True)
        self.janela.attributes("-topmost", True)
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth() - w - 12)
        y = min(self.widget.winfo_rooty() + self.widget.winfo_height() + 5,
                self.widget.winfo_screenheight() - h - 12)
        self.janela.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        canvas = CanvasSuave(self.janela, width=w, height=h, bg=FUNDO,
                             highlightthickness=0, bd=0)
        canvas.pack()
        canvas.imagem(12, 11, imagem, anchor="nw")

    def fechar(self, _evento=None):
        if self.job is not None:
            try:
                self.widget.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.janela is not None:
            try:
                self.janela.destroy()
            except tk.TclError:
                pass
            self.janela = None
