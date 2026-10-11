"""Editor da fita: popup não modal; nenhum acesso a Bluetooth ou USB no Tk."""
import colorsys
import math
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw

from aparencia_windows import preparar_janela
from controle_interface import brilho_horario
from estilo_interface import CanvasSuave, Dica, FonteInterface, fonte_campo, superficie

FUNDO = "#e9e9e5"
TEXTO = "#303238"
SECUNDARIO = "#696c73"


def gerar_roda(lado=300):
    """Bitmap HSV fixo a 2×, calculado em uma thread só ao abrir o painel."""
    tamanho = lado * 2
    centro, raio = tamanho / 2, tamanho / 2 - 12
    pixels = []
    for y in range(tamanho):
        if y % 24 == 0:
            time.sleep(0)  # Cede o GIL ao Tk durante a geração única da roda.
        dy = centro - y - 0.5
        for x in range(tamanho):
            dx = x + 0.5 - centro
            distancia = math.hypot(dx, dy)
            alfa = round(255 * max(0.0, min(1.0, raio - distancia)))
            if not alfa:
                pixels.append((0, 0, 0, 0))
                continue
            h = (math.atan2(dy, dx) / (2 * math.pi)) % 1
            s = min(1.0, distancia / raio)
            cor = colorsys.hsv_to_rgb(h, s, 1)
            pixels.append((*[round(c * 255) for c in cor], alfa))
    imagem = Image.new("RGBA", (tamanho, tamanho))
    imagem.putdata(pixels)
    return imagem.resize((lado, lado), Image.Resampling.LANCZOS)


class PainelLotus(tk.Toplevel):
    def __init__(self, janela, botao, slider):
        super().__init__(janela)
        self.withdraw()
        self.janela = janela
        self.moldura_windows = None
        self.relogio_animacao = janela.relogio_animacao
        self.title("Fita RGB · Turing Vinyl")
        if getattr(janela, "img_icone_app", None) is not None:
            self.iconphoto(False, janela.img_icone_app)
        self.configure(bg=FUNDO)
        self.resizable(False, False)
        self.transient(janela)
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.bind("<Escape>", lambda e: self.fechar())
        self.f_sans = janela.f_sans
        self.visivel = False
        self.animation_job = self.send_job = self.save_job = self.entry_job = self.wheel_job = None
        self.color_job = None
        self.actualizando = False
        self.formato = "RGB"
        self.cor = tuple(janela.config_usuario.get("lotus_cor", [255, 255, 255]))
        self.h, self.s, self.v = colorsys.rgb_to_hsv(*(c / 255 for c in self.cor))
        self.roda_pronta = False
        self.roda_fila = queue.Queue(maxsize=1)
        self._estado_chave = None
        self.candidatos = []
        self._descricao_selecionada = tk.StringVar()
        self.canvas = CanvasSuave(self, width=540, height=696, bg=FUNDO,
                                  bd=0, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(scrollregion=(0, 0, 540, 696))
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scroll_ativo = False
        self.bind("<MouseWheel>", self.rolar)
        self.canvas.create_text(25, 23, text="Fita RGB", font=FonteInterface(22, 550, serif=True),
                                anchor="nw", fill=TEXTO)
        fechar = botao(self, "", self.fechar, largura=42, altura=42, simbolo="fechar", dica="Fechar")
        self.canvas.create_window(476, 10, window=fechar, anchor="nw")
        self.status_item = self.canvas.create_text(25, 58, text="", font=janela.f_pequena,
                                                 anchor="nw", fill=SECUNDARIO, width=316)
        self.ligar = botao(self, "Desligada", janela.alternar_lotus, largura=160, altura=44,
                           simbolo="power", dica="Ligar fita", mostrar_foco=False)
        self.canvas.create_window(358, 52, window=self.ligar, anchor="nw")
        self.musica = botao(self, "Música", lambda: self.modo("musica"), largura=245, altura=48,
                            dica="Acompanhar a cor do álbum")
        self.manual = botao(self, "Manual", lambda: self.modo("manual"), largura=245, altura=48,
                            dica="Escolher uma cor fixa para a fita")
        self.canvas.create_window(20, 96, window=self.musica, anchor="nw")
        self.canvas.create_window(275, 96, window=self.manual, anchor="nw")
        self.wheel = CanvasSuave(self, width=300, height=300, bg=FUNDO,
                                 bd=0, highlightthickness=0, cursor="crosshair", takefocus=True)
        self.canvas.create_window(120, 150, window=self.wheel, anchor="nw")
        self.wheel.create_text(150, 150, text="Preparando cores…", font=janela.f_pequena,
                               fill=SECUNDARIO, tags="espera")
        self.wheel.bind("<Button-1>", self.arrastar_roda)
        self.wheel.bind("<B1-Motion>", self.arrastar_roda)
        self.wheel.bind("<ButtonRelease-1>", lambda e: self.soltar_cor())
        self.wheel.bind("<Left>", lambda e: self.tecla_roda(-1, 0))
        self.wheel.bind("<Right>", lambda e: self.tecla_roda(1, 0))
        self.wheel.bind("<Up>", lambda e: self.tecla_roda(0, 0.01))
        self.wheel.bind("<Down>", lambda e: self.tecla_roda(0, -0.01))
        self.marker = self.wheel.create_oval(0, 0, 1, 1, width=3, outline="#ffffff", fill="")
        self.marker_shadow = self.wheel.create_oval(0, 0, 1, 1, width=1, outline="#555b64", fill="")
        self.valor_cor = CanvasSuave(self, width=34, height=300, bg=FUNDO,
                                     highlightthickness=0, bd=0, cursor="hand2", takefocus=True)
        self.canvas.create_window(449, 150, window=self.valor_cor, anchor="nw")
        self.valor_imagem = self.valor_cor.imagem(7, 6, Image.new("RGBA", (20, 288)), anchor="nw")
        self.valor_marca = self.valor_cor.create_oval(5, 0, 29, 24, fill="#fbfbf8", outline="#a1a5aa", width=1)
        self.valor_cor.bind("<Button-1>", self.arrastar_valor)
        self.valor_cor.bind("<B1-Motion>", self.arrastar_valor)
        self.valor_cor.bind("<ButtonRelease-1>", lambda e: self.soltar_cor())
        self.valor_cor.bind("<Up>", lambda e: self.tecla_valor(0.01))
        self.valor_cor.bind("<Down>", lambda e: self.tecla_valor(-0.01))
        self.valor_dica = Dica(self.valor_cor, "Luminosidade da cor (V). O brilho da fita fica no slider abaixo.")
        self.valor_cor.dica = self.valor_dica
        self._gradiente_chave = None
        self.preview = self.canvas.create_oval(28, 166, 72, 210, fill="#ffffff", outline="")
        self.hex_item = self.canvas.create_text(25, 223, text="", font=janela.f_pequena,
                                              anchor="nw", fill=SECUNDARIO)
        self.formatos = {}
        for i, formato in enumerate(("RGB", "HSV", "HEX")):
            controle = botao(self, formato, lambda f=formato: self.trocar_formato(f), largura=154, altura=42)
            self.formatos[formato] = controle
            self.canvas.create_window(27 + i * 165, 453, window=controle, anchor="nw")
        self.vars = [tk.StringVar() for _ in range(3)]
        self.fonte_campos = fonte_campo(janela.f_sans)
        self.entries, self.labels, self.entry_windows, self.entry_faces = [], [], [], []
        for i, variavel in enumerate(self.vars):
            x = 37 + i * 165
            label = self.canvas.create_text(x, 505, text="", font=janela.f_pequena,
                                           fill=SECUNDARIO, anchor="nw")
            self.labels.append(label)
            self.entry_faces.append(self.canvas.imagem(x - 10, 521,
                superficie((156, 45), "#f2f2ee", raio=13, pressionado=True), anchor="nw"))
            entry = tk.Entry(self, textvariable=variavel, bg="#f2f2ee", fg=TEXTO,
                             insertbackground=TEXTO, relief="flat", bd=0, highlightthickness=0,
                             font=self.fonte_campos, justify="left", width=12)
            entry.bind("<Return>", lambda e: self.aplicar_campos(True))
            entry.bind("<FocusOut>", lambda e: self.aplicar_campos(False))
            variavel.trace_add("write", self.campos_editados)
            self.entries.append(entry)
            self.entry_windows.append(self.canvas.create_window(x + 4, 533, window=entry, anchor="nw", width=124, height=23))
        self.erro_item = self.canvas.create_text(32, 568, text="", font=FonteInterface(11), fill="#966022", anchor="nw")
        self.canvas.create_text(32, 592, text="Brilho da fita", font=janela.f_sans, fill=TEXTO, anchor="nw")
        self.brilho_item = self.canvas.create_text(508, 592, text="", font=janela.f_sans, fill=TEXTO, anchor="ne")
        self.brilho = slider(self, 100, self.mudar_brilho, largura=400, fundo=FUNDO)
        self.canvas.create_window(12, 616, window=self.brilho, anchor="nw")
        self.auto = botao(self, "Tela", self.brilho_tela, largura=108, altura=46,
                          dica="Acompanhar o brilho dos LEDs do PC")
        self.canvas.create_window(410, 616, window=self.auto, anchor="nw")
        self.pasta = botao(self, "Pasta Lotus", self.trocar_pasta, largura=142, altura=38,
                           mostrar_foco=False)
        self.canvas.create_window(20, 658, window=self.pasta, anchor="nw")
        self.address_item = self.canvas.create_text(180, 673, text="", font=FonteInterface(11),
                                                   fill=SECUNDARIO, anchor="w")
        self.dispositivos = ttk.Combobox(self, state="readonly", textvariable=self._descricao_selecionada,
                                         font=("Segoe UI", 10))
        self.dispositivos.bind("<<ComboboxSelected>>", self.escolher_dispositivo)
        self.device_window = self.canvas.create_window(180, 663, window=self.dispositivos, anchor="nw",
                                                       width=334, height=25, state="hidden")
        self.atualizar_campos()
        self.atualizar()

        def preparar():
            self.roda_fila.put(gerar_roda())
        threading.Thread(target=preparar, name="RodaCorFita", daemon=True).start()

    def abrir(self):
        if self.visivel:
            self.lift()
            return
        self.visivel = True
        self.atualizar()
        self.janela.update_idletasks()
        x = self.janela.winfo_rootx() + max(12, self.janela.winfo_width() - 560)
        y = self.janela.winfo_rooty() + 12
        altura = min(696, max(350, self.winfo_vrootheight() - 90))
        self.scroll_ativo = altura < 696
        largura = 556 if self.scroll_ativo else 540
        if self.scroll_ativo:
            self.scrollbar.pack(side="right", fill="y")
        else:
            self.scrollbar.pack_forget()
        self.canvas.yview_moveto(0)
        # Mantém o popup na área do monitor; a janela principal segue interativa.
        x = max(self.winfo_vrootx(), min(x, self.winfo_vrootx() + self.winfo_vrootwidth() - largura))
        y = max(self.winfo_vrooty(), min(y, self.winfo_vrooty() + self.winfo_vrootheight() - altura - 60))
        self.geometry(f"{largura}x{altura}{x:+d}{y + 12:+d}")
        try: self.attributes("-alpha", 0.0)
        except tk.TclError: pass
        self.deiconify()
        # Reutiliza a decoração nativa clara da janela principal, incluindo
        # o ícone correto. O objeto permanece vivo entre aberturas do painel.
        self.update_idletasks()
        if self.moldura_windows is None:
            raiz = Path(__file__).resolve().parent
            self.moldura_windows = preparar_janela(
                self, FUNDO, TEXTO, raiz / "assets" / "icons" / "turing-vinyl.ico",
                raiz / "iniciar_interface.pyw")
        else:
            self.moldura_windows.aplicar_cores()
        self.lift()
        self._animar(True, x, y)
        self.receber_roda()

    def rolar(self, evento):
        if self.scroll_ativo:
            self.canvas.yview_scroll(-int(evento.delta / 120), "units")
            return "break"

    def _animar(self, abrindo, x=None, y=None):
        if self.animation_job:
            self.after_cancel(self.animation_job)
        inicio = time.monotonic()
        if x is None:
            x, y = self.winfo_x(), self.winfo_y()
        try: origem = float(self.attributes("-alpha"))
        except tk.TclError: origem = 1.0
        destino = 1.0 if abrindo else 0.0
        relogio = self.janela.relogio_animacao
        relogio.marcar((id(self), "popup"), True)

        def quadro():
            t = min(1.0, (time.monotonic() - inicio) / 0.2)
            peso = t * t * (3 - 2 * t)
            try:
                self.attributes("-alpha", origem + (destino - origem) * peso)
                deslocamento = round(12 * (1 - peso) if abrindo else 8 * peso)
                self.geometry(f"+{x}+{y + deslocamento}" if x >= 0 and y >= 0 else f"{x:+d}{y + deslocamento:+d}")
            except tk.TclError: pass
            if t < 1:
                self.animation_job = self.after(16, quadro)
            else:
                self.animation_job = None
                relogio.marcar((id(self), "popup"), False)
                if not abrindo:
                    self.withdraw()
        quadro()

    def receber_roda(self):
        self.wheel_job = None
        if not self.visivel or self.roda_pronta:
            return
        try:
            imagem = self.roda_fila.get_nowait()
        except queue.Empty:
            self.wheel_job = self.after(40, self.receber_roda)
            return
        self.wheel.delete("espera")
        item = self.wheel.imagem(0, 0, imagem, anchor="nw")
        self.wheel.tag_lower(item)
        self.roda_pronta = True
        self.indicador()

    def indicador(self):
        angulo = self.h * 2 * math.pi
        x, y = 150 + 144 * self.s * math.cos(angulo), 150 - 144 * self.s * math.sin(angulo)
        self.wheel.coords(self.marker, x - 7, y - 7, x + 7, y + 7)
        self.wheel.coords(self.marker_shadow, x - 9, y - 9, x + 9, y + 9)
        hexa = "#%02X%02X%02X" % self.cor
        self.canvas.itemconfigure(self.preview, fill=hexa)
        self.canvas.itemconfigure(self.hex_item, text=hexa)
        y_valor = 12 + (1 - self.v) * 276
        self.valor_cor.coords(self.valor_marca, 5, y_valor - 12, 29, y_valor + 12)
        chave = (round(self.h * 360), round(self.s * 100))
        if chave != self._gradiente_chave:
            imagem = Image.new("RGBA", (20, 288))
            desenho = ImageDraw.Draw(imagem)
            for y in range(288):
                cor = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(self.h, self.s, 1 - y / 287))
                desenho.line((0, y, 19, y), fill=(*cor, 255))
            mascara = Image.new("L", (20, 288))
            ImageDraw.Draw(mascara).rounded_rectangle((0, 0, 19, 287), radius=9, fill=255)
            imagem.putalpha(mascara)
            self.valor_cor.alterar_imagem(self.valor_imagem, imagem)
            self._gradiente_chave = chave

    def arrastar_roda(self, evento):
        if not self.roda_pronta:
            return
        self.wheel.focus_set()
        dx, dy = evento.x - 150, 150 - evento.y
        self.h = (math.atan2(dy, dx) / (2 * math.pi)) % 1
        self.s = min(1.0, math.hypot(dx, dy) / 144)
        if self.v <= 0:
            self.v = 1.0
        self.agendar_cor()

    def arrastar_valor(self, evento):
        self.valor_cor.focus_set()
        self.v = max(0.0, min(1.0, 1 - (evento.y - 12) / 276))
        self.agendar_cor()

    def tecla_valor(self, delta):
        self.v = max(0.0, min(1.0, self.v + delta))
        self.usar_hsv()
        return "break"

    def agendar_cor(self):
        if self.color_job is None:
            self.color_job = self.after(16, self.usar_hsv)

    def soltar_cor(self):
        self.usar_hsv()
        self.persistir()

    def tecla_roda(self, matiz, saturacao):
        self.h = (self.h + matiz / 360) % 1
        self.s = max(0.0, min(1.0, self.s + saturacao))
        self.usar_hsv()
        return "break"

    def usar_hsv(self):
        if self.color_job:
            self.after_cancel(self.color_job)
            self.color_job = None
        self.cor = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(self.h, self.s, self.v))
        self.definir_cor()

    def definir_cor(self):
        config = self.janela.config_usuario
        config["lotus_modo"], config["lotus_cor"] = "manual", list(self.cor)
        self.indicador()
        self.atualizar_campos()
        self.atualizar()
        self.agendar_envio()

    def atualizar_campos(self):
        self.actualizando = True
        valores = (list(map(str, self.cor)) if self.formato == "RGB" else
                   [f"{self.h * 360:.1f}", f"{self.s * 100:.1f}", f"{self.v * 100:.1f}"] if self.formato == "HSV" else
                   ["#%02X%02X%02X" % self.cor, "", ""])
        nomes = ("R · 0–255", "G · 0–255", "B · 0–255") if self.formato == "RGB" else (
            ("H · 0–360°", "S · 0–100%", "V · 0–100%") if self.formato == "HSV" else ("HEX", "", ""))
        for i, (variavel, valor) in enumerate(zip(self.vars, valores)):
            variavel.set(valor)
            self.canvas.itemconfigure(self.labels[i], text=nomes[i])
            self.canvas.itemconfigure(self.entry_windows[i], state="normal" if self.formato != "HEX" or i == 0 else "hidden")
            self.canvas.itemconfigure(self.entry_faces[i], state="normal" if self.formato != "HEX" or i == 0 else "hidden")
        hexa = self.formato == "HEX"
        self.canvas.alterar_imagem(self.entry_faces[0], superficie((486 if hexa else 156, 45),
                                   "#f2f2ee", raio=13, pressionado=True))
        self.canvas.itemconfigure(self.entry_windows[0], width=454 if hexa else 124)
        self.actualizando = False
        self.canvas.itemconfigure(self.erro_item, text="")
        self.indicador()

    def trocar_formato(self, formato):
        if self.entry_job:
            self.after_cancel(self.entry_job)
            self.entry_job = None
        self.aplicar_campos(False)
        self.formato = formato
        self.atualizar_campos()
        self.atualizar()

    def campos_editados(self, *_):
        if self.actualizando:
            return
        if self.entry_job:
            self.after_cancel(self.entry_job)
        self.entry_job = self.after(350, lambda: self.aplicar_campos(False))

    def aplicar_campos(self, avisar):
        if self.actualizando or not self.visivel:
            return
        if self.entry_job:
            self.after_cancel(self.entry_job)
            self.entry_job = None
        try:
            textos = [v.get().strip() for v in self.vars]
            if self.formato == "RGB":
                cor = tuple(int(v) for v in textos)
                if not all(0 <= c <= 255 for c in cor): raise ValueError()
                h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in cor))
            elif self.formato == "HSV":
                h, s, v = (float(c.replace(",", ".")) for c in textos)
                if not (0 <= h <= 360 and 0 <= s <= 100 and 0 <= v <= 100): raise ValueError()
                h, s, v = h / 360 % 1, s / 100, v / 100
                cor = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))
            else:
                hexa = textos[0].lstrip("#")
                if len(hexa) == 3: hexa = "".join(c * 2 for c in hexa)
                if len(hexa) != 6: raise ValueError()
                cor = tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))
                h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in cor))
            if cor != self.cor:
                self.cor, self.h, self.s, self.v = cor, h, s, v
                self.definir_cor()
            elif self.formato == "HSV":
                self.h, self.s, self.v = h, s, v
                self.indicador()
        except (ValueError, OverflowError):
            if avisar:
                self.canvas.itemconfigure(self.erro_item, text="Confira os valores e os limites dos campos.")
        return "break"

    def agendar_envio(self):
        # O arraste pinta no Tk; só o último valor atravessa o pipe a cada 100 ms.
        if self.send_job is None:
            self.send_job = self.after(100, self.enviar)
        if self.save_job:
            self.after_cancel(self.save_job)
        self.save_job = self.after(700, self.persistir)

    def enviar(self):
        self.send_job = None
        self.janela.motor.enviar({"acao": "configurar", "config": self.janela.config_usuario})

    def persistir(self):
        for atributo in ("send_job", "save_job"):
            job = getattr(self, atributo)
            if job: self.after_cancel(job)
            setattr(self, atributo, None)
        self.janela.guardar()

    def modo(self, modo):
        if self.color_job:
            self.usar_hsv()
        self.aplicar_campos(False)
        self.janela.config_usuario["lotus_modo"] = modo
        self.atualizar()
        self.persistir()

    def mudar_brilho(self, valor, soltar):
        self.janela.config_usuario["lotus_brilho"] = valor
        self.atualizar()
        self.persistir() if soltar else self.agendar_envio()

    def brilho_tela(self):
        config = self.janela.config_usuario
        config["lotus_brilho"] = None if config.get("lotus_brilho") is not None else self.brilho.valor
        self.atualizar()
        self.persistir()

    def trocar_pasta(self):
        self.janela.escolher_lotus()
        self.atualizar()

    def escolher_dispositivo(self, _=None):
        i = self.dispositivos.current()
        if 0 <= i < len(self.candidatos):
            self.janela.config_usuario["lotus_endereco"] = self.candidatos[i]["endereco"]
            self.persistir()

    def atualizar(self):
        config = self.janela.config_usuario
        ligada = config.get("lotus_ativo", False)
        cor = self.janela.cor_modo
        valor = config.get("lotus_brilho")
        automatico = valor is None
        if automatico:
            valor = (config["brilho"] if config["brilho"] is not None else brilho_horario()) if config["tela_ligada"] else 0
        iluminada = (ligada and config["tela_ligada"] and valor > 0
                      and (config.get("lotus_modo") != "manual" or any(config["lotus_cor"])))
        rotulo = "Ligada" if iluminada else "Em espera" if ligada else "Desligada"
        self.ligar.atualizar(texto=rotulo, selecionado=ligada, cor=cor, mostrar_ponto=iluminada,
                             dica="Desativar fita" if ligada else "Ligar fita")
        self.musica.atualizar(selecionado=config.get("lotus_modo") == "musica", cor=cor)
        self.manual.atualizar(selecionado=config.get("lotus_modo") == "manual", cor=cor)
        for formato, botao in self.formatos.items():
            botao.atualizar(selecionado=self.formato == formato, cor=cor)
        self.brilho.atualizar(valor=valor, cor=cor)
        self.auto.atualizar(selecionado=automatico, cor=cor)
        self.canvas.itemconfigure(self.brilho_item, text=f"{valor}%")
        estado = (self.janela.midia or {}).get("lotus") or {}
        if not ligada:
            texto = "Desligada"
        elif not self.janela.rodando:
            texto = "Conecta ao iniciar a exibição"
        elif not config["tela_ligada"]:
            texto = "Apagada pelo controle principal"
        else:
            texto = estado.get("status", "Conectando…")
        self.canvas.itemconfigure(self.status_item, text=texto)
        candidatos = (estado.get("candidatos") or []) if ligada else []
        if candidatos != self.candidatos:
            self.candidatos = candidatos
            self.dispositivos["values"] = [f"{c['nome']} · {c['endereco'].upper()}" for c in candidatos]
            self._descricao_selecionada.set("Escolher fita…")
        varios = len(candidatos) > 1
        self.canvas.itemconfigure(self.device_window, state="normal" if varios else "hidden")
        self.canvas.itemconfigure(self.address_item, state="hidden" if varios else "normal",
            text=(estado.get("nome", "") + " · " + estado.get("endereco", "").upper()).strip(" ·"))

    def fechar(self):
        if not self.visivel:
            return
        if self.color_job:
            self.usar_hsv()
        self.aplicar_campos(False)
        self.persistir()
        self.visivel = False
        self.parar_interacoes()
        for atributo in ("entry_job", "wheel_job", "color_job"):
            job = getattr(self, atributo)
            if job: self.after_cancel(job)
            setattr(self, atributo, None)
        self._animar(False)

    def encerrar(self):
        if self.color_job:
            self.usar_hsv()
        self.aplicar_campos(False)
        self.persistir()
        self.visivel = False
        self.parar_interacoes()
        for atributo in ("animation_job", "send_job", "save_job", "entry_job", "wheel_job", "color_job"):
            job = getattr(self, atributo)
            if job: self.after_cancel(job)
            setattr(self, atributo, None)
        self.janela.relogio_animacao.marcar((id(self), "popup"), False)
        if self.moldura_windows is not None:
            self.moldura_windows.fechar()
            self.moldura_windows = None
        self.destroy()

    def parar_interacoes(self):
        # Cancelar hover, dicas e teclas evita timers de widgets escondidos.
        for widget in self.winfo_children():
            dica = getattr(widget, "dica", None)
            if dica is not None:
                dica.fechar()
            for atributo in ("hover_job", "job"):
                job = getattr(widget, atributo, None)
                if job:
                    widget.after_cancel(job)
                    setattr(widget, atributo, None)
            self.relogio_animacao.marcar((id(widget), "hover"), False)
            if hasattr(widget, "hover_t"):
                widget.hover_t = 0.0
                widget.desenhar()
