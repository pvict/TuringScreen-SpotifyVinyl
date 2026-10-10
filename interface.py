"""Janela de controle do Turing Vinyl. Execute: python interface.py.

Tkinter + Pillow, sem navegador embutido. Prévia pequena com alvo de 60 FPS.
O script original roda em um processo separado, com comandos em pipes locais.
"""
import base64
import ctypes
import io
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from aparencia_windows import preparar_janela
from fundo_usuario import ConversorFundo
from controle_interface import (PREFIXO, brilho_horario, carregar, salvar,
                                reservar_execucao, liberar_execucao)
from estilo_interface import (CanvasSuave, FonteInterface, Dica, configurar_dpi,
                               superficie, icone, limitar_linhas, texto_suave,
                               RotacaoPreview, RelogioAnimacaoWindows)

RAIZ = Path(__file__).resolve().parent
FUNDO = "#e9e9e5"
CARTAO = FUNDO
TEXTO = "#303238"
SECUNDARIO = "#696c73"
PRATA = "#707b89"
MODOS = [
    ("dinamico", "Dinâmico", "Spotify durante a música; vídeo durante a pausa.", PRATA),
    ("spotify", "Spotify", "Só Spotify. O vinil permanece durante a pausa.", "#717b87"),
    ("video", "Vídeo", "Só o vídeo de fundo, sem informações da música.", "#737c87"),
]
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UI_FPS = 60


def proximo_quadro(widget, inicio, callback):
    """Agenda no relógio: desenhar não acrescenta atraso a cada quadro."""
    agora = time.monotonic()
    indice = math.floor((agora - inicio) * UI_FPS) + 1
    espera = math.ceil((inicio + indice / UI_FPS - agora) * 1000)
    return widget.after(max(1, espera), callback)


def precisao_animacao(widget, tipo, ativo):
    relogio = getattr(widget.winfo_toplevel(), "relogio_animacao", None)
    if relogio is not None:
        relogio.marcar((id(widget), tipo), ativo)


def rgb(cor):
    return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))


def misturar(a, b, t):
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(rgb(a), rgb(b)))


def cor_album(cor):
    """Mantém o matiz do álbum, com contraste sobre a superfície clara."""
    canais = tuple(max(0, min(255, round(c))) for c in cor[:3])
    ganho = min(1.0, 150 / max(max(canais), 1))
    acento = "#%02x%02x%02x" % tuple(min(255, round(c * ganho)) for c in canais)
    return misturar(acento, "#59616e", 0.18)


def animar_hover(widget, valor):
    """Um timer curto por entrada/saída; não mantém um loop ocioso."""
    if getattr(widget, "hover_job", None):
        widget.after_cancel(widget.hover_job)
    widget.hover_alvo = bool(valor)
    origem = widget.hover_t
    inicio = time.monotonic()
    precisao_animacao(widget, "hover", True)

    def passo():
        t = min(1.0, (time.monotonic() - inicio) / 0.26)
        s = t * t * (3 - 2 * t)
        widget.hover_t = origem + (float(valor) - origem) * s
        widget.desenhar()
        widget.hover_job = proximo_quadro(widget, inicio, passo) if t < 1 else None
        if t >= 1:
            precisao_animacao(widget, "hover", False)
    passo()


def halo(cor, tamanho=(330, 180), intensidade=75):
    img = Image.new("RGBA", tamanho)
    d = ImageDraw.Draw(img)
    d.ellipse((50, 44, tamanho[0] - 50, tamanho[1] - 44), fill=(*rgb(cor), intensidade))
    return img.filter(ImageFilter.GaussianBlur(24))


_BASES_FUNDO = {}
_MASCARA_ACENTO = None


def fundo_janela(cor=PRATA):
    global _MASCARA_ACENTO
    if "solido" not in _BASES_FUNDO:
        img = Image.new("RGBA", (1000, 720), FUNDO)
        img.alpha_composite(superficie((348, 348), "#e4e5e1", raio=174, pressionado=True), (111, 89))
        _BASES_FUNDO["solido"] = img
    if _MASCARA_ACENTO is None:
        mask = Image.new("L", (1000, 720))
        ImageDraw.Draw(mask).ellipse((164, 142, 406, 384), fill=25)
        _MASCARA_ACENTO = mask.filter(ImageFilter.GaussianBlur(37))
    if cor is None:
        return _BASES_FUNDO["solido"].copy()
    acento = Image.new("RGBA", (1000, 720), cor)
    acento.putalpha(_MASCARA_ACENTO)
    return Image.alpha_composite(_BASES_FUNDO["solido"], acento)


def acento_vinil(cor):
    # A transição atualiza apenas esta região, não um bitmap de toda a janela.
    img = Image.new("RGBA", (388, 388), cor)
    img.putalpha(_MASCARA_ACENTO.crop((91, 69, 479, 457)))
    return img


def disco_base():
    # O desenho fixo é suavizado uma vez; a rotação continua trabalhando em 270 px.
    s = 3
    img = Image.new("RGBA", (270 * s, 270 * s))
    d = ImageDraw.Draw(img)
    d.ellipse((8 * s, 8 * s, 262 * s, 262 * s), fill="#141516", outline="#545b64", width=s)
    for r in range(121, 59, -2):
        cor = (26, 27, 29, 255)
        d.ellipse(tuple(n * s for n in (135 - r, 135 - r, 135 + r, 135 + r)), outline=cor, width=s)
    reflexo = Image.new("RGBA", img.size)
    rd = ImageDraw.Draw(reflexo)
    for desloc in range(38):
        alfa = round(30 * (1 - desloc / 38))
        rd.pieslice((14 * s, 14 * s, 256 * s, 256 * s), 210 + desloc, 226 + desloc,
                    fill=(218, 220, 218, alfa))
        rd.pieslice((14 * s, 14 * s, 256 * s, 256 * s), 30 + desloc, 46 + desloc,
                    fill=(218, 220, 218, alfa))
    img = Image.alpha_composite(img, reflexo.filter(ImageFilter.GaussianBlur(3 * s)))
    return img.resize((270, 270), Image.Resampling.LANCZOS)


class Botao(CanvasSuave):
    def __init__(self, master, texto, comando, largura=150, altura=40,
                 primario=False, fundo=FUNDO, simbolo=None, dica=""):
        super().__init__(master, width=largura, height=altura, bg=fundo,
                         highlightthickness=0, bd=0, takefocus=True, cursor="hand2")
        self.texto, self.comando, self.primario = texto, comando, primario
        self.cor = PRATA
        self.simbolo, self.selecionado = simbolo, False
        self.ativo, self.hover = True, False
        self.hover_t, self.hover_job = 0.0, None
        self.fonte = master.f_sans if hasattr(master, "f_sans") else FonteInterface()
        self._ultima_pintura = None
        self.bind("<Button-1>", lambda e: self.acionar())
        self.bind("<Return>", lambda e: self.acionar())
        self.bind("<space>", lambda e: self.acionar())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<FocusIn>", lambda e: self.desenhar())
        self.bind("<FocusOut>", lambda e: self.desenhar())
        self.dica = Dica(self, dica)
        self.desenhar()

    def _hover(self, valor):
        self.hover = valor
        animar_hover(self, valor)

    def acionar(self):
        if self.ativo:
            self.focus_set()
            self.comando()
        return "break"

    def atualizar(self, texto=None, ativo=None, cor=None, selecionado=None, simbolo=None, dica=None):
        if texto is not None:
            self.texto = texto
        if ativo is not None:
            self.ativo = ativo
        if cor is not None:
            self.cor = cor
        if selecionado is not None:
            self.selecionado = selecionado
        if simbolo is not None:
            self.simbolo = simbolo
        if dica is not None:
            self.dica.texto = dica
        chave = (self.texto, self.ativo, self.cor, self.selecionado, self.simbolo, self.primario)
        if chave != self._ultima_pintura:
            self.desenhar()

    def desenhar(self):
        w, h = int(self["width"]), int(self["height"])
        preenchimento = (misturar("#33373e", self.cor, 0.28) if self.primario else
                         misturar(FUNDO, self.cor, 0.11) if self.selecionado else
                         misturar(FUNDO, "#ffffff", self.hover_t * 0.25))
        if not self.ativo:
            preenchimento = FUNDO
        # Mantém os itens do Canvas. Mover o mouse não destrói imagens ou letras.
        if not hasattr(self, "face_item"):
            vazio = Image.new("RGBA", (1, 1))
            self.face_item = self.imagem(0, 0, vazio, anchor="nw")
            self.icone_item = self.imagem(w / 2, h / 2, vazio)
            self.rotulo_item = self.create_text(0, h / 2, text="", font=self.fonte, anchor="w")
            self.ponto_item = self.create_oval(w - 22, h / 2 - 2, w - 18, h / 2 + 2,
                                               outline="", state="hidden")
            self.foco_item = self.create_line(w / 2 - 7, h - 12, w / 2 + 7, h - 12,
                                               width=2, capstyle=tk.ROUND, state="hidden")
        if self.ativo:
            preenchimento = misturar(preenchimento, "#ffffff", round(self.hover_t * 12) / 12 * 0.12)
        self.alterar_imagem(self.face_item, superficie((w, h), preenchimento,
                                raio=(w / 2 if not self.texto else 16), pressionado=self.selecionado))
        tinta = ("#ffffff" if self.primario else TEXTO) if self.ativo else SECUNDARIO
        total = self.fonte.measure(self.texto) + (29 if self.simbolo and self.texto else 0)
        x = (w - total) / 2
        if self.simbolo:
            self.coords(self.icone_item, x + 10 if self.texto else w / 2, h / 2)
            self.alterar_imagem(self.icone_item, icone(self.simbolo, tinta, 20))
            self.itemconfigure(self.icone_item, state="normal")
            x += 29
        else:
            self.itemconfigure(self.icone_item, state="hidden")
        if self.texto:
            self.coords(self.rotulo_item, x, h / 2)
        self.itemconfigure(self.rotulo_item, text=self.texto, font=self.fonte, fill=tinta)
        self.itemconfigure(self.ponto_item, fill=self.cor, state="normal" if self.selecionado else "hidden")
        self.itemconfigure(self.foco_item, fill=self.cor,
                            state="normal" if not self.selecionado and self.focus_get() is self else "hidden")
        self._ultima_pintura = (self.texto, self.ativo, self.cor, self.selecionado, self.simbolo, self.primario)


class Seletor(CanvasSuave):
    def __init__(self, master, selecionado, comando, fonte, fonte_pequena):
        super().__init__(master, width=912, height=92, bg=FUNDO,
                         highlightthickness=0, takefocus=True, cursor="hand2")
        self.comando, self.fonte, self.fonte_pequena = comando, fonte, fonte_pequena
        self.indice = next(i for i, m in enumerate(MODOS) if m[0] == selecionado)
        self.x = self.indice * 296 + 12
        self.cor = MODOS[self.indice][3]
        self.hover_indice, self.hover_t, self.hover_job = None, 0.0, None
        self.hover_alvo = False
        self.hover_valores = [0.0, 0.0, 0.0]
        self.job = None
        self.bind("<Button-1>", self.clicar)
        self.bind("<Motion>", self.mover_mouse)
        self.bind("<Leave>", lambda e: self.animar_realce(None))
        self.bind("<Left>", lambda e: self.escolher(max(0, self.indice - 1)))
        self.bind("<Right>", lambda e: self.escolher(min(2, self.indice + 1)))
        self.bind("<Home>", lambda e: self.escolher(0))
        self.bind("<End>", lambda e: self.escolher(2))
        self.bind("<FocusIn>", lambda e: self.desenhar())
        self.bind("<FocusOut>", lambda e: self.desenhar())
        self.dica = Dica(self, MODOS[self.indice][2])
        self.desenhar()

    def clicar(self, e):
        self.focus_set()
        self.escolher(max(0, min(2, int((e.x - 12) / 296))))

    def mover_mouse(self, e):
        indice = max(0, min(2, int((e.x - 12) / 296)))
        if indice != self.hover_indice or not self.hover_alvo:
            self.dica.texto = ("Modo retomado ao sair de Gaming." if
                               self.master.config_usuario.get("gaming") else MODOS[indice][2])
            self.dica.agendar()
            self.animar_realce(indice)

    def animar_realce(self, indice):
        if self.hover_job is not None:
            self.after_cancel(self.hover_job)
        self.hover_indice, self.hover_alvo = indice, indice is not None
        origem = list(self.hover_valores)
        inicio = time.monotonic()
        precisao_animacao(self, "hover", True)

        def passo():
            t = min(1.0, (time.monotonic() - inicio) / 0.26)
            s = t * t * (3 - 2 * t)
            self.hover_valores = [v + (float(i == indice) - v) * s for i, v in enumerate(origem)]
            self.desenhar()
            self.hover_job = proximo_quadro(self, inicio, passo) if t < 1 else None
            if t >= 1:
                precisao_animacao(self, "hover", False)
        passo()

    def atualizar_cor(self, cor):
        if cor != self.cor:
            self.cor = cor
            self.desenhar()

    def escolher(self, indice):
        if indice == self.indice:
            return "break"
        if self.job is not None:
            self.after_cancel(self.job)
            self.job = None
        origem_x = self.x
        self.indice = indice
        inicio, destino = time.monotonic(), indice * 296 + 12
        precisao_animacao(self, "selecao", True)
        self.comando(MODOS[indice][0])

        def passo():
            t = min(1.0, (time.monotonic() - inicio) / 0.38)
            s = t * t * (3 - 2 * t)
            self.x = origem_x + (destino - origem_x) * s
            self.desenhar()
            self.job = proximo_quadro(self, inicio, passo) if t < 1 else None
            if t >= 1:
                precisao_animacao(self, "selecao", False)
        passo()
        return "break"

    def desenhar(self):
        if not hasattr(self, "face_item"):
            self.imagem(0, 0, superficie((912, 92), FUNDO, raio=30, pressionado=True), anchor="nw")
            self.face_item = self.imagem(self.x, 5, superficie((296, 82), raio=24), anchor="nw")
            self.rotulos, self.icones = [], []
            for i, (_, titulo, _, _) in enumerate(MODOS):
                total = self.fonte.measure(titulo) + 38
                x = 160 + i * 296 - total / 2
                self.icones.append(self.imagem(x + 12, 46, icone(("onda", "spotify", "video")[i], SECUNDARIO)))
                self.rotulos.append(self.create_text(x + 38, 46, text=titulo, anchor="w",
                                                      font=self.fonte, fill=SECUNDARIO))
            self.foco_item = self.create_oval(0, 72, 6, 75, outline="", state="hidden")
        face = misturar("#f8f8f5", self.cor, 0.035)
        self.coords(self.face_item, self.x, 5)
        self.alterar_imagem(self.face_item, superficie((296, 82), face, raio=24))
        for i, (_, titulo, _, _) in enumerate(MODOS):
            selecionado = i == self.indice
            sobre = self.hover_valores[i]
            tinta = self.cor if selecionado else SECUNDARIO
            self.alterar_imagem(self.icones[i], icone(("onda", "spotify", "video")[i], tinta, 24))
            self.itemconfigure(self.rotulos[i], fill=misturar(TEXTO if selecionado else SECUNDARIO, self.cor, sobre))
        self.coords(self.foco_item, 157 + 296 * self.indice, 72, 163 + 296 * self.indice, 75)
        self.itemconfigure(self.foco_item, fill=self.cor, state="normal" if self.focus_get() is self else "hidden")


class Slider(CanvasSuave):
    def __init__(self, master, valor, comando, largura=620, fundo=CARTAO):
        super().__init__(master, width=largura, height=46, bg=fundo,
                         highlightthickness=0, takefocus=True, cursor="hand2")
        # Reserva o raio máximo do halo (19 px), com folga nas duas pontas.
        self.margem = 24
        self.percurso = largura - 2 * self.margem
        self.valor, self.comando = valor, comando
        self.cor, self.job = PRATA, None
        self.hover_t, self.hover_job = 0.0, None
        self.bind("<Enter>", lambda e: animar_hover(self, True))
        self.bind("<Leave>", lambda e: animar_hover(self, False))
        self.bind("<Button-1>", self.arrastar)
        self.bind("<B1-Motion>", self.arrastar)
        self.bind("<ButtonRelease-1>", self.soltar)
        self.bind("<Left>", lambda e: self.tecla(-1))
        self.bind("<Right>", lambda e: self.tecla(1))
        self.bind("<Prior>", lambda e: self.tecla(10))
        self.bind("<Next>", lambda e: self.tecla(-10))
        self.bind("<Home>", lambda e: self.tecla(-100))
        self.bind("<End>", lambda e: self.tecla(100))
        self.bind("<FocusIn>", lambda e: self.desenhar())
        self.bind("<FocusOut>", lambda e: self.desenhar())
        self.desenhar()

    def arrastar(self, e):
        if self["state"] == "disabled":
            return "break"
        self.focus_set()
        self.valor = round(max(0, min(100, (e.x - self.margem) / self.percurso * 100)))
        self.desenhar()
        self.comando(self.valor, False)

    def soltar(self, e):
        if self["state"] != "disabled":
            self.comando(self.valor, True)

    def tecla(self, incremento):
        if self["state"] == "disabled":
            return "break"
        self.valor = max(0, min(100, self.valor + incremento))
        self.desenhar()
        self.comando(self.valor, False)
        if self.job:
            self.after_cancel(self.job)
        self.job = self.after(250, lambda: self.comando(self.valor, True))
        return "break"

    def atualizar(self, valor=None, cor=None):
        anterior = (self.valor, self.cor)
        if valor is not None:
            self.valor = valor
        if cor:
            self.cor = cor
        if (self.valor, self.cor) != anterior:
            self.desenhar()

    def desenhar(self):
        x = self.margem + self.valor / 100 * self.percurso
        w = int(self["width"])
        if not hasattr(self, "trilho_item"):
            vazio = Image.new("RGBA", (1, 1))
            self.trilho_item = self.imagem(0, 0, vazio, anchor="nw")
            self.botao_item = self.imagem(x - 22, 1, superficie((44, 44), "#fbfbf8", raio=22), anchor="nw")
            self.ponto_item = self.create_oval(0, 0, 1, 1, outline="")
            self._trilho_chave = None
        chave = (self.valor, self.cor)
        if chave == self._trilho_chave:
            raio = 3 + self.hover_t
            self.coords(self.ponto_item, x - raio, 23 - raio, x + raio, 23 + raio)
            return
        # O trilho e o botão usam a mesma escala de suavização dos ícones.
        escala = 3
        img = Image.new("RGBA", (w * escala, 46 * escala))
        d = ImageDraw.Draw(img)
        a, b, y = self.margem * escala, (self.margem + self.percurso) * escala, 23 * escala
        d.rounded_rectangle((a, y - 4 * escala, b, y + 4 * escala), radius=4 * escala,
                            fill="#d0d2d0")
        d.line((a + 3 * escala, y - 3 * escala, b - 3 * escala, y - 3 * escala),
                fill="#bdc1c1", width=escala)
        d.line((a + 3 * escala, y + 4 * escala, b - 3 * escala, y + 4 * escala),
                fill="#fafaf7", width=escala)
        if self.valor:
            d.rounded_rectangle((a, y - 3 * escala, max(a + 1, x * escala), y + 3 * escala),
                                radius=3 * escala, fill=misturar("#828995", self.cor, 0.65))
        self.alterar_imagem(self.trilho_item, img.resize((w, 46), Image.Resampling.LANCZOS))
        self.coords(self.botao_item, x - 22, 1)
        raio = 3 + self.hover_t
        self.coords(self.ponto_item, x - raio, 23 - raio, x + raio, 23 + raio)
        self.itemconfigure(self.ponto_item, fill=self.cor)
        self._trilho_chave = chave


class PainelFundo(CanvasSuave):
    def __init__(self, master):
        super().__init__(master, width=452, height=248, bg=CARTAO,
                         highlightthickness=0, bd=0)
        self.janela, self.f_sans = master, master.f_sans
        self.definir_fundo(superficie((452, 248), "#f1f1ed", raio=22))
        self.create_text(24, 24, text="Fundo", anchor="nw", font=master.f_modo, fill=TEXTO)
        self.fechar = Botao(self, "", master.alternar_painel_fundo, simbolo="fechar",
                            largura=40, altura=40, fundo=CARTAO, dica="Fechar")
        self.create_window(395, 11, window=self.fechar, anchor="nw")
        self.nome = self.create_text(24, 64, anchor="nw", font=master.f_sans, fill=SECUNDARIO)
        self.escolher = Botao(self, "Escolher vídeo", master.escolher_fundo,
                              largura=238, altura=48, primario=True, fundo=CARTAO)
        self.create_window(16, 98, window=self.escolher, anchor="nw")
        self.padrao = Botao(self, "Padrão", master.acao_fundo,
                            largura=162, altura=48, fundo=CARTAO)
        self.create_window(264, 98, window=self.padrao, anchor="nw")
        self.percentual = self.create_text(428, 159, anchor="ne", font=master.f_pequena,
                                           fill=SECUNDARIO)
        self.barra = self.create_line(25, 183, 428, 183, fill="#d0d2d0", width=5,
                                      capstyle=tk.ROUND)
        self.preenchimento = self.create_line(25, 183, 25, 183, width=5, capstyle=tk.ROUND)
        self.status = self.create_text(24, 202, anchor="nw", font=master.f_pequena,
                                       fill=SECUNDARIO, width=405)

    def atualizar(self):
        janela = self.janela
        ocupado = janela.fundo_convertendo
        nome = (janela.fundo_nome_em_preparo if ocupado else
                janela.config_usuario["video_ocioso_nome"] or "Fundo padrão")
        self.itemconfigure(self.nome, text=janela.encurtar(nome, 394, janela.f_sans))
        self.escolher.atualizar(texto="Preparando…" if ocupado else "Escolher vídeo",
                                ativo=not ocupado, cor=janela.cor_modo)
        self.padrao.atualizar(texto="Cancelar" if ocupado else "Padrão",
                              ativo=ocupado or janela.config_usuario["video_ocioso"] is not None,
                              cor=janela.cor_modo)
        self.fechar.atualizar(cor=janela.cor_modo)
        progresso = janela.fundo_progresso
        valor = 0 if progresso is None else progresso
        self.coords(self.preenchimento, 25, 183, 25 + 403 * valor / 100, 183)
        self.itemconfigure(self.preenchimento, fill=janela.cor_modo,
                            state="normal" if valor > 0 else "hidden")
        self.itemconfigure(self.percentual, text=f"{valor}%" if ocupado and progresso is not None else "")
        texto, cor = janela.fundo_status
        self.itemconfigure(self.status, text=texto if len(texto) <= 140 else texto[:137] + "…", fill=cor)


class Motor:
    """A janela nunca acessa o hardware; acompanha somente o processo que iniciou."""
    def __init__(self):
        self.proc = None
        self.eventos = queue.Queue(maxsize=24)
        self.erros = deque(maxlen=12)
        self.lock = threading.Lock()
        self._config_pendente = None
        self.iniciando = False

    def evento(self, tipo, dados):
        try:
            self.eventos.put_nowait((tipo, dados))
        except queue.Full:
            try:
                self.eventos.get_nowait()
            except queue.Empty:
                pass
            self.eventos.put_nowait((tipo, dados))

    def iniciar(self, config):
        if self.iniciando or (self.proc and self.proc.poll() is None):
            return
        self.iniciando = True
        with self.lock:
            self._config_pendente = dict(config)

        def executar():
            try:
                # Detecta também scripts anteriores que ainda não usam o mutex.
                if os.name == "nt":
                    consulta = ("Get-CimInstance Win32_Process -Filter \"Name = 'python.exe' OR Name = 'pythonw.exe'\" "
                                "| Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
                    resultado = subprocess.run(["powershell", "-NoProfile", "-Command", consulta],
                                               capture_output=True, text=True, timeout=12,
                                               creationflags=SEM_JANELA)
                    if resultado.returncode != 0:
                        raise RuntimeError("Não foi possível conferir se a tela já está em uso.")
                    processos = json.loads(resultado.stdout or "[]")
                    if isinstance(processos, dict):
                        processos = [processos]
                    if any("tela_completa.py" in (p.get("CommandLine") or "").lower() for p in (processos or [])):
                        raise RuntimeError("O script já está aberto no terminal. Encerre-o com Ctrl+C antes de iniciar aqui.")
                self.erros.clear()
                ambiente = dict(os.environ, PYTHONIOENCODING="utf-8")
                python = Path(sys.executable)
                if python.name.lower() == "pythonw.exe":
                    python = python.with_name("python.exe")
                self.proc = subprocess.Popen(
                    [str(python), "-u", str(RAIZ / "tela_completa.py"), "--interface"],
                    cwd=RAIZ, env=ambiente, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                    creationflags=SEM_JANELA)
                self.enviar({"acao": "configurar"})
                self.evento("iniciado", None)
                for linha in self.proc.stdout:
                    pos = linha.find(PREFIXO)
                    if pos >= 0:
                        try:
                            self.evento("estado", json.loads(linha[pos + len(PREFIXO):]))
                        except ValueError:
                            pass
                    elif any(palavra in linha.lower() for palavra in ("error", "erro", "exception", "traceback")):
                        self.erros.append(linha.strip())
                codigo = self.proc.wait()
                self.evento("parado", "\n".join(self.erros) if codigo else "")
            except Exception as exc:
                self.evento("erro", str(exc))
            finally:
                self.iniciando = False
        threading.Thread(target=executar, name="JanelaMotor", daemon=True).start()

    def enviar(self, dados):
        with self.lock:
            if dados.get("acao") == "configurar":
                if isinstance(dados.get("config"), dict):
                    self._config_pendente = dict(dados["config"])
                dados = {"acao": "configurar", "config": self._config_pendente}
            if self.proc is not None and self.proc.poll() is None:
                try:
                    self.proc.stdin.write(json.dumps(dados, ensure_ascii=True) + "\n")
                    self.proc.stdin.flush()
                except (OSError, ValueError):
                    pass

    def parar(self):
        self.enviar({"acao": "parar"})


class Janela(tk.Tk):
    def __init__(self):
        configurar_dpi()
        super().__init__()
        self.relogio_animacao = RelogioAnimacaoWindows()
        self.title("Turing Vinyl")
        self.geometry("1000x720")
        self.minsize(1000, 720)
        self.resizable(True, True)
        self.configure(bg=FUNDO)
        self.img_icone_header = None
        self.carregar_icone()
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.config_usuario = carregar()
        preparar_janela(self)
        self.conversor_fundo = ConversorFundo()
        self.fundo_painel_aberto, self.fundo_convertendo = False, False
        self.fundo_nome_em_preparo = ""
        self.fundo_progresso, self.fundo_pendente = 0, False
        self.fundo_status = ("Escolha um vídeo. A preparação acontece aqui no app.", SECUNDARIO)
        self.motor = Motor()
        self.encerrando, self.iniciando, self.rodando = False, False, False
        self.config_job = None
        self.midia, self.capa = None, None
        self.capa_preview = None
        self.capa_base = disco_base()
        self.rotacao_preview = RotacaoPreview(self.capa_base)
        self._apresentar_job = None
        self.cor_modo = PRATA if self.config_usuario.get("gaming") else next(
            m[3] for m in MODOS if m[0] == self.config_usuario["modo"])
        self.cor_destino, self.tema_job = self.cor_modo, None
        self.disco_job = None
        self._visual = {}
        self._angulo_gui, self._escala_gui = 0.0, 1.0
        self._angulo_externo = 0.0
        self._velocidade_gui = self._velocidade_externa_gui = 0.0
        self._tempo_preview = time.monotonic()
        self._relogio_preview = self._tempo_preview
        self._preview_chave = None
        self.f_sans = FonteInterface(14, 500)
        self.f_pequena = FonteInterface(12, 450)
        self.f_modo = FonteInterface(16, 550)
        self.f_logo = FonteInterface(25, 550, serif=True)
        self.f_faixa = FonteInterface(32, 500, serif=True)
        self.f_valor = FonteInterface(17, 550)
        self.canvas = CanvasSuave(self, width=1000, height=720, bg=FUNDO, bd=0, highlightthickness=0)
        self.canvas.pack(expand=True)
        self.fundo_atual = fundo_janela(None)
        self.img_fundo = ImageTk.PhotoImage(self.fundo_atual)
        self.fundo_item = self.canvas.create_image(0, 0, image=self.img_fundo, anchor="nw")
        self.img_acento = ImageTk.PhotoImage(acento_vinil(self.cor_modo))
        self.acento_item = self.canvas.create_image(91, 69, image=self.img_acento, anchor="nw")
        self.desenhar()
        self.after(50, self.eventos)
        self.bind("<Escape>", lambda e: self.fechar_paineis())

    def texto(self, x, y, texto, fonte=None, cor=TEXTO, **opcoes):
        return self.canvas.create_text(x, y, text=texto, font=fonte or self.f_sans,
                                       fill=cor, anchor="nw", **opcoes)

    def carregar_icone(self):
        """PNG no cabeçalho e ícone de várias resoluções na janela do Windows."""
        try:
            with Image.open(RAIZ / "assets" / "icons" / "turing-vinyl.png") as arquivo:
                imagem = arquivo.convert("RGBA")
                self.img_icone_app = ImageTk.PhotoImage(
                    imagem.resize((256, 256), Image.Resampling.LANCZOS))
                self.img_icone_header = ImageTk.PhotoImage(
                    imagem.resize((40, 40), Image.Resampling.LANCZOS))
            self.iconphoto(True, self.img_icone_app)
            if os.name == "nt":
                self.iconbitmap(str(RAIZ / "assets" / "icons" / "turing-vinyl.ico"))
        except (OSError, tk.TclError):
            # O controle da tela continua disponível se o recurso não for copiado.
            pass

    def desenhar(self):
        c = self.canvas
        if self.img_icone_header is not None:
            c.create_image(64, 42, image=self.img_icone_header)
        c.create_text(100, 42, text="Turing Vinyl", font=self.f_logo, fill=TEXTO, anchor="w")
        self.status_ponto = c.create_oval(102, 67, 108, 73, fill=SECUNDARIO, outline="")
        self.status_texto = c.create_text(116, 70, text="Pronto", font=self.f_pequena,
                                          fill=SECUNDARIO, anchor="w")
        self.fundo_botao = Botao(self, "Fundo", self.alternar_painel_fundo,
                                 largura=130, altura=48, simbolo="video", dica="Escolher o vídeo de fundo")
        c.create_window(822, 19, window=self.fundo_botao, anchor="nw")

        self.disco_item = c.create_image(285, 263)
        self.hero_rotulo = self.texto(529, 171, "", self.f_pequena, SECUNDARIO)
        self.faixa_texto = self.texto(526, 209, "Turing Vinyl", self.f_faixa, width=408)
        self.artista_texto = self.texto(529, 304, "", self.f_sans, SECUNDARIO)
        self.playlist_texto = self.texto(529, 333, "", self.f_pequena, SECUNDARIO)
        self.atualizar_disco()
        self.modo_dica = self.texto(944, 422, "", self.f_pequena, SECUNDARIO)
        c.itemconfigure(self.modo_dica, anchor="ne")
        self.seletor = Seletor(self, self.config_usuario["modo"], self.mudar_modo, self.f_modo, self.f_pequena)
        c.create_window(44, 441, window=self.seletor, anchor="nw")

        self.texto(64, 569, "Brilho", self.f_sans)
        self.valor_texto = self.texto(712, 569, "", self.f_valor)
        c.itemconfigure(self.valor_texto, anchor="ne")
        self.slider = Slider(self, self.valor_brilho(), self.mudar_brilho, largura=694, fundo=FUNDO)
        c.create_window(42, 590, window=self.slider, anchor="nw")
        self.slider.dica = Dica(self.slider, "Ajustar brilho. 0% apaga a tela.")
        self.auto = Botao(self, "Auto", self.automatico, largura=94, altura=48,
                          dica="Brilho automático por horário")
        c.create_window(750, 586, window=self.auto, anchor="nw")
        self.power = Botao(self, "", self.alternar_tela, largura=48, altura=48,
                           simbolo="power", dica="Desligar tela")
        c.create_window(904, 586, window=self.power, anchor="nw")
        self.brilho_dica = self.texto(64, 640, "", self.f_pequena, SECUNDARIO)

        self.iniciar = Botao(self, "Iniciar", self.alternar_motor, largura=150, altura=48,
                             primario=True, simbolo="play", dica="Iniciar exibição")
        c.create_window(802, 656, window=self.iniciar, anchor="nw")
        self.gaming_botao = Botao(self, "Gaming", self.alternar_gaming, largura=154,
                                  altura=48, simbolo="gaming", dica="Usar só o fundo e reduzir o processamento")
        c.create_window(636, 656, window=self.gaming_botao, anchor="nw")
        self.aviso = self.texto(64, 673, "", self.f_pequena, SECUNDARIO, width=530)
        self.fundo_painel = PainelFundo(self)
        self.fundo_painel_item = c.create_window(504, 77, window=self.fundo_painel,
                                                 anchor="nw", state="hidden")
        self.atualizar_controles()
        self.fundo_painel.atualizar()

    def alternar_painel_fundo(self):
        self.fundo_painel_aberto = not self.fundo_painel_aberto
        self.fundo_painel.atualizar()
        self.canvas.itemconfigure(self.fundo_painel_item,
                                   state="normal" if self.fundo_painel_aberto else "hidden")
        if self.fundo_painel_aberto:
            self.canvas.tag_raise(self.fundo_painel_item)

    def escolher_fundo(self):
        if self.fundo_convertendo or self.conversor_fundo.ocupado:
            return
        caminho = filedialog.askopenfilename(
            parent=self, title="Escolher vídeo de fundo",
            filetypes=[("Vídeos", "*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.wmv *.gif"),
                       ("Todos os arquivos", "*.*")])
        if not caminho or self.encerrando:
            return
        if self.conversor_fundo.iniciar(caminho):
            self.fundo_convertendo = True
            self.fundo_nome_em_preparo = Path(caminho).name
            self.fundo_progresso = 0
            self.fundo_status = ("Abrindo o vídeo…", SECUNDARIO)
            self.fundo_botao.atualizar(texto="Preparando…")
            self.fundo_painel.atualizar()

    def acao_fundo(self):
        if self.fundo_convertendo:
            self.conversor_fundo.cancelar()
            self.fundo_status = ("Cancelando a preparação…", SECUNDARIO)
            self.fundo_painel.atualizar()
        else:
            self.definir_fundo(None, "")

    def definir_fundo(self, caminho, nome):
        anterior = (self.config_usuario["video_ocioso"], self.config_usuario["video_ocioso_nome"])
        self.config_usuario.update(video_ocioso=caminho, video_ocioso_nome=nome)
        try:
            salvar(self.config_usuario)
        except OSError:
            self.config_usuario.update(video_ocioso=anterior[0], video_ocioso_nome=anterior[1])
            self.fundo_status = ("Não foi possível salvar o novo fundo. O anterior foi mantido.", "#966022")
            self.fundo_painel.atualizar()
            return
        self.motor.enviar({"acao": "configurar", "config": self.config_usuario})
        self.fundo_progresso = 100 if caminho else 0
        self.fundo_pendente = self.rodando or self.iniciando
        texto = ("Fundo pronto. Será usado no modo ocioso." if self.fundo_pendente else
                 "Fundo salvo. Ele será usado ao iniciar a exibição.")
        self.fundo_status = (texto, SECUNDARIO)
        self.fundo_painel.atualizar()
        self.mensagem("Novo fundo salvo." if caminho else "Fundo padrão selecionado.")

    def eventos_fundo(self):
        try:
            while True:
                tipo, dados = self.conversor_fundo.eventos.get_nowait()
                if tipo == "progresso":
                    self.fundo_progresso, texto = dados
                    self.fundo_status = (texto, SECUNDARIO)
                else:
                    self.fundo_convertendo = False
                    self.fundo_botao.atualizar(texto="Fundo")
                    if self.conversor_fundo.cancelamento.is_set():
                        tipo = "cancelado"
                    if tipo == "pronto":
                        self.definir_fundo(dados["caminho"], dados["nome"])
                    elif tipo == "cancelado":
                        self.fundo_progresso = 0
                        self.fundo_status = ("Preparação cancelada. O fundo anterior foi mantido.", SECUNDARIO)
                    elif tipo == "erro":
                        self.fundo_progresso = 0
                        self.fundo_status = (dados, "#966022")
                self.fundo_painel.atualizar()
        except queue.Empty:
            pass

    def fechar_paineis(self):
        if self.fundo_painel_aberto:
            self.alternar_painel_fundo()

    def valor_brilho(self):
        if not self.config_usuario["tela_ligada"]:
            return 0
        return self.config_usuario["brilho"] or brilho_horario()

    def atualizar_disco(self):
        capa_visivel = (self.capa_preview if self.config_usuario["modo"] != "video"
                        and not self.config_usuario.get("gaming") else None)
        lado = max(1, round(114 * self._escala_gui))
        chave = (id(capa_visivel), round(self._angulo_gui, 3),
                 round(self._angulo_externo, 3), lado,
                 self.cor_modo if capa_visivel is None else None)
        if chave == self._preview_chave:
            return
        self._preview_chave = chave
        self.rotacao_preview.solicitar(chave, capa_visivel, self._angulo_gui,
                                       self._angulo_externo, lado,
                                       misturar("#3b424d", self.cor_modo, 0.22))
        if self._apresentar_job is None:
            self._apresentar_job = self.after(8, self.mostrar_disco_pronto)

    def mostrar_disco_pronto(self):
        self._apresentar_job = None
        if self.encerrando:
            return
        resultado = self.rotacao_preview.receber()
        if resultado is not None:
            chave, disco = resultado
            # Descarta uma capa anterior se o modo ou a música mudou durante o cálculo.
            if (chave[0] == self._preview_chave[0]
                    and chave[4] == self._preview_chave[4]):
                if not hasattr(self, "_buffers_disco"):
                    self._buffers_disco = [ImageTk.PhotoImage(disco), ImageTk.PhotoImage(disco)]
                    self._buffer_disco_indice = 0
                else:
                    self._buffer_disco_indice = 1 - self._buffer_disco_indice
                    # Atualiza a imagem que não está exibida, depois troca os buffers.
                    self._buffers_disco[self._buffer_disco_indice].paste(disco)
                self.img_disco = self._buffers_disco[self._buffer_disco_indice]
                self.canvas.itemconfigure(self.disco_item, image=self.img_disco)
        if self.rotacao_preview.pendente():
            self._apresentar_job = self.after(8, self.mostrar_disco_pronto)

    def cor_desejada(self):
        if self.config_usuario.get("gaming"):
            return PRATA
        cor = (self.midia or {}).get("cor")
        if self.config_usuario["modo"] != "video" and cor:
            return cor_album(cor)
        return next(m[3] for m in MODOS if m[0] == self.config_usuario["modo"])

    def atualizar_tema(self):
        destino = self.cor_desejada()
        if destino == self.cor_destino:
            return
        self.cor_destino = destino
        if self.tema_job:
            self.after_cancel(self.tema_job)
        origem = self.cor_modo
        inicio = time.monotonic()
        precisao_animacao(self, "tema", True)

        def passo():
            if self.encerrando:
                self.tema_job = None
                return
            t = 1.0 if self.state() == "iconic" else min(1.0, (time.monotonic() - inicio) / 0.65)
            s = t * t * (3 - 2 * t)
            self.cor_modo = misturar(origem, destino, s)
            self.img_acento.paste(acento_vinil(self.cor_modo))
            self.canvas.itemconfigure(self.hero_rotulo, fill=SECUNDARIO)
            self.seletor.atualizar_cor(self.cor_modo)
            for botao in (self.auto, self.power, self.iniciar, self.fundo_botao,
                          self.gaming_botao):
                botao.atualizar(cor=self.cor_modo)
            self.slider.atualizar(cor=self.cor_modo)
            if self.fundo_painel_aberto:
                self.fundo_painel.atualizar()
            if (self.midia or {}).get("conectada"):
                self.canvas.itemconfigure(self.status_ponto, fill=self.cor_modo)
                self.canvas.itemconfigure(self.status_texto, fill=SECUNDARIO)
            if (self.capa_preview is None or self.config_usuario["modo"] == "video"
                    or self.config_usuario.get("gaming")):
                self.atualizar_disco()
            self.tema_job = proximo_quadro(self, inicio, passo) if t < 1 else None
            if t >= 1:
                precisao_animacao(self, "tema", False)
        passo()

    def atualizar_visual(self, visual):
        self._visual = {} if self.config_usuario.get("gaming") else visual
        if self.disco_job is None:
            self.animar_disco()

    def animar_disco(self):
        self.disco_job = None
        if self.encerrando:
            return
        agora = time.monotonic()
        dt = min(0.1, max(0.001, agora - self._tempo_preview))
        self._tempo_preview = agora
        visual = self._visual
        visivel = (self.rodando and visual.get("visivel", False)
                   and self.config_usuario["modo"] != "video" and self.config_usuario["tela_ligada"]
                   and not self.config_usuario.get("gaming"))
        velocidade = visual.get("velocidade", 0.0) if visivel else 0.0
        velocidade_externa = visual.get("velocidade_disco", velocidade) if visivel else 0.0
        if visivel:
            fator = -math.expm1(-dt / 0.065)
            self._velocidade_gui += (velocidade - self._velocidade_gui) * fator
            self._velocidade_externa_gui += (velocidade_externa - self._velocidade_externa_gui) * fator
            if abs(self._velocidade_gui - velocidade) < 0.02:
                self._velocidade_gui = velocidade
            if abs(self._velocidade_externa_gui - velocidade_externa) < 0.02:
                self._velocidade_externa_gui = velocidade_externa
        else:
            self._velocidade_gui = self._velocidade_externa_gui = 0.0
        velocidade, velocidade_externa = self._velocidade_gui, self._velocidade_externa_gui
        # Só números atravessam o pipe. O disco 270px é animado localmente a 60 FPS.
        # A correção da fase é amortecida para os pacotes não causarem saltos.
        if visivel:
            idade = max(0.0, agora - visual.get("instante", agora))
            previsto = (self._angulo_gui + velocidade * dt) % 360
            alvo = (visual.get("angulo", 0.0)
                    + visual.get("velocidade", 0.0) * idade) % 360
            erro = (alvo - previsto + 180) % 360 - 180 if idade < 0.4 else 0.0
            self._angulo_gui = (previsto + erro * -math.expm1(-dt / 0.32)) % 360
            previsto_externo = (self._angulo_externo + velocidade_externa * dt) % 360
            alvo_externo = (visual.get("angulo_disco", visual.get("angulo", 0.0))
                            + visual.get("velocidade_disco", visual.get("velocidade", 0.0)) * idade) % 360
            erro_externo = (alvo_externo - previsto_externo + 180) % 360 - 180 if idade < 0.4 else 0.0
            self._angulo_externo = (previsto_externo + erro_externo * -math.expm1(-dt / 0.32)) % 360
        else:
            erro = erro_externo = 0.0
        escala_alvo = visual.get("escala", 1.0) if visivel else self._escala_gui
        self._escala_gui += (escala_alvo - self._escala_gui) * -math.expm1(-dt / 0.06)
        escala_movendo = abs(escala_alvo - self._escala_gui) > 0.001
        if not escala_movendo:
            self._escala_gui = escala_alvo
        if abs(erro) < 0.02 and velocidade == 0 and visivel:
            self._angulo_gui = visual.get("angulo", self._angulo_gui)
        if abs(erro_externo) < 0.02 and velocidade_externa == 0 and visivel:
            self._angulo_externo = visual.get("angulo_disco", self._angulo_externo)
        minimizada = self.state() == "iconic"
        if not minimizada:
            self.atualizar_disco()
        movendo = (abs(velocidade) > 0.001 or abs(velocidade_externa) > 0.001
                    or abs(erro) > 0.02 or abs(erro_externo) > 0.02 or escala_movendo)
        precisao_animacao(self, "vinil", movendo and not minimizada)
        if movendo:
            self.disco_job = (self.after(250, self.animar_disco) if minimizada else
                              proximo_quadro(self, self._relogio_preview, self.animar_disco))

    def atualizar_controles(self):
        valor = self.valor_brilho()
        ligada = self.config_usuario["tela_ligada"]
        self.canvas.itemconfigure(self.valor_texto, text=f"{valor}%" if ligada else "0%")
        automatico = self.config_usuario["brilho"] is None
        self.auto.atualizar(texto="Auto", cor=self.cor_modo, selecionado=automatico)
        self.power.atualizar(cor=self.cor_modo, selecionado=not ligada,
                             dica="Desligar tela" if ligada else "Ligar tela")
        self.iniciar.atualizar(cor=self.cor_modo)
        gaming = self.config_usuario.get("gaming", False)
        self.gaming_botao.atualizar(texto="Gaming", selecionado=gaming, cor=self.cor_modo,
                                    dica="Desligar Gaming" if gaming else "Só o fundo, com menos processamento")
        self.seletor.dica.texto = ("Modo retomado ao sair de Gaming." if gaming
                                   else MODOS[self.seletor.indice][2])
        self.canvas.itemconfigure(self.modo_dica, text="")
        self.slider.atualizar(valor, self.cor_modo)
        self.canvas.itemconfigure(self.brilho_dica, text="")
        # As informações iniciais também respeitam o modo salvo na última sessão.
        if hasattr(self, "artista_texto"):
            self.atualizar_texto_midia()

    def guardar(self):
        try:
            salvar(self.config_usuario)
        except OSError:
            self.mensagem("Não foi possível salvar as preferências.", "#966022")
        self.motor.enviar({"acao": "configurar", "config": self.config_usuario})

    def mudar_modo(self, modo):
        self.config_usuario["modo"] = modo
        self.atualizar_tema()
        self.atualizar_controles()
        self.atualizar_disco()
        self.atualizar_texto_midia()
        self.guardar()

    def alternar_gaming(self):
        self.config_usuario["gaming"] = not self.config_usuario.get("gaming", False)
        if self.config_usuario["gaming"]:
            self._visual = {}
            if self.disco_job is not None:
                self.after_cancel(self.disco_job)
                self.disco_job = None
            precisao_animacao(self, "vinil", False)
        self.atualizar_tema()
        self.atualizar_controles()
        self.atualizar_disco()
        self.guardar()
        self.mensagem("Preparando Gaming…"
                      if self.config_usuario["gaming"] else "Voltando ao modo de exibição selecionado…")

    def mudar_brilho(self, valor, aplicar):
        self.config_usuario["tela_ligada"] = valor > 0
        if valor > 0:
            self.config_usuario["brilho"] = valor
        self.atualizar_controles()
        if aplicar:
            self.guardar()  # um comando ao soltar, sem inundar USB ou OpenRGB

    def automatico(self):
        self.config_usuario["brilho"] = (self.valor_brilho() or brilho_horario()) if self.config_usuario["brilho"] is None else None
        self.atualizar_controles()
        self.guardar()

    def alternar_tela(self):
        self.config_usuario["tela_ligada"] = not self.config_usuario["tela_ligada"]
        self.atualizar_controles()
        self.guardar()

    def alternar_motor(self):
        if self.iniciando:
            return
        if self.rodando:
            self.motor.parar()
            self.iniciar.atualizar(texto="Encerrando…", ativo=False)
        else:
            self.guardar()
            self.iniciando = True
            self.iniciar.atualizar(texto="Conectando…", ativo=False)
            self.mensagem("Preparando a tela…")
            self.motor.iniciar(dict(self.config_usuario))

    def mensagem(self, texto, cor=SECUNDARIO):
        self.canvas.itemconfigure(self.aviso, text=texto[:104], fill=cor)

    def encurtar(self, texto, largura, fonte):
        if fonte.measure(texto) <= largura:
            return texto
        while texto and fonte.measure(texto + "…") > largura:
            texto = texto[:-1]
        return texto + "…"

    def eventos(self):
        if self.encerrando:
            return
        self.eventos_fundo()
        try:
            while True:
                tipo, dados = self.motor.eventos.get_nowait()
                if tipo == "iniciado":
                    self.rodando, self.iniciando = True, False
                    self.iniciar.atualizar(texto="Parar", ativo=True, simbolo="stop", dica="Parar exibição")
                elif tipo in ("parado", "erro"):
                    self.rodando, self.iniciando = False, False
                    self._visual = {}
                    self.iniciar.atualizar(texto="Iniciar", ativo=True, simbolo="play", dica="Iniciar exibição")
                    self.canvas.itemconfigure(self.status_texto, text="Parada", fill=SECUNDARIO)
                    self.canvas.itemconfigure(self.status_ponto, fill="#89929f")
                    self.mensagem(dados or "", "#966022" if dados else SECUNDARIO)
                elif tipo == "estado":
                    self.atualizar_estado(dados)
        except queue.Empty:
            pass
        self.after(50, self.eventos)

    def atualizar_estado(self, dados):
        if "visual" in dados:
            self.atualizar_visual(dados["visual"])
        if "config" not in dados:
            return  # pacote pequeno de movimento, sem repetir metadados/tema/capa
        conectada = dados.get("conectada", False)
        if not conectada:
            self._visual = {}
        self.canvas.itemconfigure(self.status_texto, text="Conectada" if conectada else "Conectando…",
                                  fill=SECUNDARIO)
        self.canvas.itemconfigure(self.status_ponto, fill=self.cor_modo if conectada else "#89929f")
        self.midia = dados
        if not self.fundo_convertendo:
            if dados.get("erro_fundo"):
                self.fundo_status = (dados["erro_fundo"], "#966022")
                self.fundo_painel.atualizar()
            elif conectada and self.fundo_pendente and dados.get("fundo_ocioso_ativo") == self.config_usuario["video_ocioso"]:
                self.fundo_pendente = False
                self.fundo_status = ("Fundo atualizado. Ele aparece nos momentos ociosos.", SECUNDARIO)
                self.fundo_painel.atualizar()
        self.atualizar_tema()
        self.atualizar_texto_midia()
        if "capa" in dados:
            try:
                self.capa = Image.open(io.BytesIO(base64.b64decode(dados["capa"]))).convert("RGBA") if dados["capa"] else None
                self.capa_preview = self.capa.resize((114, 114), Image.Resampling.LANCZOS) if self.capa else None
                self.atualizar_disco()
            except (ValueError, OSError):
                pass
        if dados.get("erro"):
            self.mensagem(dados["erro"], "#966022")
        elif dados.get("erro_gaming"):
            self.mensagem(dados["erro_gaming"], "#966022")
        elif self.config_usuario.get("gaming") and dados.get("gaming_preparando"):
            self.mensagem("Preparando Gaming…")
        elif dados.get("gaming_ativo"):
            self.mensagem("")
        elif conectada:
            self.mensagem("")
        if self.config_usuario["brilho"] is None and self.config_usuario["tela_ligada"]:
            if self.slider.valor != self.valor_brilho():
                self.atualizar_controles()

    def atualizar_texto_midia(self):
        dados = self.midia or {}
        musica = dados.get("musica")
        gaming = self.config_usuario.get("gaming", False)
        self.canvas.itemconfigure(self.playlist_texto, text="")
        if gaming or self.config_usuario["modo"] == "video":
            self.canvas.itemconfigure(self.hero_rotulo, text="Gaming" if gaming else "Vídeo")
            self.canvas.itemconfigure(self.faixa_texto, text="Vídeo de fundo")
            self.canvas.itemconfigure(self.artista_texto, text="Preparando…" if dados.get("gaming_preparando") else
                                      self.encurtar(self.config_usuario["video_ocioso_nome"] or "", 408, self.f_sans))
            self.canvas.coords(self.artista_texto, 529, 267)
            return
        if musica:
            titulo, artista = musica
            # Até duas linhas, sem texto promocional ou estado repetido junto do artista.
            titulo = limitar_linhas(titulo, self.f_faixa, 408, limite=2)
            self.canvas.itemconfigure(self.hero_rotulo, text="Spotify" if dados.get("tocando") else "Em pausa")
            self.canvas.itemconfigure(self.faixa_texto, text=titulo)
            self.canvas.itemconfigure(self.artista_texto, text=self.encurtar(artista, 408, self.f_sans))
            altura = texto_suave(titulo, self.f_faixa.chave, TEXTO, 408).height
            y_artista = 209 + altura + 14
            self.canvas.coords(self.artista_texto, 529, y_artista)
            playlist = dados.get("playlist_nome")
            if playlist:
                self.canvas.coords(self.playlist_texto, 529, y_artista + 28)
                self.canvas.itemconfigure(self.playlist_texto,
                                           text=self.encurtar(playlist, 408, self.f_pequena))
        else:
            self.canvas.itemconfigure(self.hero_rotulo, text="")
            self.canvas.itemconfigure(self.faixa_texto, text="Turing Vinyl")
            self.canvas.itemconfigure(self.artista_texto, text="")

    def fechar(self):
        if self.encerrando:
            return
        self.encerrando = True
        self.relogio_animacao.fechar()
        self.rotacao_preview.fechar()
        self.conversor_fundo.cancelar()
        self.motor.parar()
        self.iniciar.atualizar(texto="Encerrando…", ativo=False)
        inicio = time.monotonic()

        def aguardar():
            proc = self.motor.proc
            if (proc is None or proc.poll() is not None) and not self.conversor_fundo.ocupado:
                self.destroy()
            elif time.monotonic() - inicio >= 10:
                # Fechar o stdin aciona o mesmo encerramento se o comando se perdeu.
                try:
                    if proc is not None:
                        proc.stdin.close()
                except (OSError, ValueError):
                    pass
                self.mensagem("Aguardando a tela encerrar…")
                self.after(500, aguardar)
            else:
                self.after(150, aguardar)
        aguardar()


def main():
    try:
        reserva = reservar_execucao("Local\\TuringVinylInterface")
    except RuntimeError:
        return
    try:
        if os.name == "nt":
            try:
                # Dá à janela sua própria identidade na barra de tarefas.
                shell = ctypes.WinDLL("shell32")
                shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
                shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
                shell.SetCurrentProcessExplicitAppUserModelID("TuringScreen.SpotifyVinyl.Interface")
            except (OSError, AttributeError):
                pass
        Janela().mainloop()
    finally:
        liberar_execucao(reserva)


if __name__ == "__main__":
    main()
