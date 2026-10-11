"""Sincronização opcional com a ponte BLE do Lotus Lantern para Windows.

DDP local, independente do SDK OpenRGB e da transmissão USB. Só inicia o
adaptador Bluetooth quando o usuário ativa a opção; não executa os .cmd.
"""
import datetime
import json
import math
import re
import shutil
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
INTERVALO = 0.2
FADE = 1.2
ENDERECO = ("127.0.0.1", 4048)


def pasta_valida(pasta):
    if not pasta:
        return False
    pasta = Path(pasta)
    return (pasta / "src/ble-device.cjs").is_file() and (pasta / "config.cmd").is_file()


def _config_ponte(pasta):
    if not pasta_valida(pasta):
        raise ValueError("Escolha a pasta do Lotus Lantern no botão Fita RGB.")
    pasta = Path(pasta).resolve()
    config = (pasta / "config.cmd").read_text(encoding="utf-8-sig")
    # Lê somente o endereço: nunca executa comandos do arquivo de configuração.
    match = re.search(r'^\s*set\s+"?LED_DEVICE_UUID=([0-9a-fA-F:-]+)"?\s*$', config, re.M | re.I)
    uuid = re.sub(r"[:-]", "", match[1]) if match else ""
    if not re.fullmatch(r"[0-9a-fA-F]{12}", uuid):
        uuid = ""  # A descoberta automática também atende instalações novas.
    node = shutil.which("node")
    if node is None:
        raise ValueError("Node.js não encontrado. Instale as dependências do Lotus Lantern.")
    if not (pasta / "node_modules/noble-winrt").is_dir():
        raise ValueError("Faltam as dependências do Lotus Lantern (noble-winrt).")
    return pasta, uuid, node


class LotusLantern:
    def __init__(self, controles, estado, brilho_para, parar, log):
        self.controles, self.estado = controles, estado
        self.brilho_para, self.parar, self.log = brilho_para, parar, log
        self.proc = None
        self._socket = None
        self._sequencia = 0
        self._status = "Desligada"
        self._chave_cor = None
        self._base_cor = (142, 0, 218)
        self._cor_idle = (142, 0, 218)
        self._cor_original = None
        self._cor_pc = None
        self._calibrar_pc = None
        try:
            perfil = json.loads((RAIZ / "perfil_ocioso.json").read_text(encoding="utf-8"))
            for nome, cores in perfil.get("cores", {}).items():
                if "Addressable Header" in nome and cores:
                    cor = tuple(max(0, min(255, int(c))) for c in cores[0][:3])
                    if len(cor) == 3:
                        self._cor_idle = cor
                        break
        except (OSError, ValueError, TypeError, IndexError):
            pass

    def status(self, texto, erro="", **detalhes):
        self._status = texto
        anterior = self.estado.get("lotus") or {}
        self.estado["lotus"] = {**anterior, "status": texto, "erro": erro, **detalhes}

    def iniciar(self):
        self._thread = threading.Thread(target=self._executar, name="LotusCores", daemon=True)
        self._thread.start()
        return self

    def _abrir(self, pasta):
        pasta, uuid, node = _config_ponte(pasta)
        # Não assume que uma porta ocupada pertence ao Lotus: evita disputar
        # a fita com Audio Party ou outra ponte que esteja em execução.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as verificar:
            verificar.bind(ENDERECO)
        self.status("Conectando…")
        proc = subprocess.Popen(
            [node, str(RAIZ / "tools/lotus_bridge.cjs"), str(pasta), uuid],
            cwd=str(RAIZ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.proc = proc
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._chave_cor = None
        self._endereco_selecionado = None
        self._ultimo_envio = 0.0
        self.log(f"lotus: ponte BLE iniciada; endereço={uuid}; OpenRGB preservado")

        def ler():
            try:
                for linha in proc.stdout:
                    if self.proc is not proc:
                        return
                    if linha.startswith("@LOTUS@"):
                        try:
                            dados = json.loads(linha[len("@LOTUS@"):])
                            anterior = self._status
                            self.status(dados["status"], dados.get("erro", ""),
                                        **{k: dados[k] for k in ("endereco", "nome", "candidatos") if k in dados})
                            if dados.get("erro"):
                                self.log("lotus: " + dados["erro"][:240])
                            elif dados["status"] != anterior:
                                self.log("lotus: " + dados["status"])
                        except (ValueError, KeyError, TypeError):
                            pass
            except (OSError, ValueError):
                pass  # o encerramento da ponte fecha o pipe
            finally:
                if self.proc is proc:
                    self.status("Desconectada", "A ponte Bluetooth encerrou; verifique o Lotus Lantern.")
        threading.Thread(target=ler, name="LotusEstado", daemon=True).start()

    def _fechar(self, apagar=False):
        proc, self.proc = self.proc, None
        if proc is not None:
            try:
                if apagar and proc.poll() is None:
                    # Comando privado para desligar fisicamente a fita antes
                    # de liberar a conexão; nunca passa pelo OpenRGB.
                    proc.stdin.write(json.dumps({"desligar": True}) + "\n")
                    proc.stdin.flush()
                proc.stdin.close()  # encerramento solicitado pelo pipe privado
                proc.wait(timeout=2)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                if proc.poll() is None:
                    proc.terminate()  # somente o processo criado por esta instância
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            finally:
                if proc.stdin is not None:
                    try:
                        proc.stdin.close()
                    except (OSError, ValueError):
                        pass
            if proc.stdout is not None:
                proc.stdout.close()
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def _cor_alvo(self):
        config = self.controles.config
        if not config["tela_ligada"]:
            # O controle principal prevalece também sobre o brilho manual
            # da fita. As preferências dela ficam preservadas para a volta.
            return (0, 0, 0)
        if config.get("lotus_modo") == "manual":
            cor = config.get("lotus_cor", [255, 255, 255])
            brilho = config.get("lotus_brilho")
            if brilho is None:
                brilho = self.brilho_para(datetime.datetime.now())
            return tuple(round(c * brilho / 100) for c in cor)
        snap = dict(self.estado)
        midia = snap
        if snap.get("modo_exibicao") == "spotify" and snap.get("musica") is None:
            midia = snap.get("ultima_midia") or snap
        album_ativo = (
            snap.get("modo_exibicao") != "video" and midia.get("musica") is not None
        )
        cor = (midia.get("cor_viva") or midia.get("cor_capa")) if album_ativo else self._cor_idle
        cor = tuple((cor or self._cor_idle)[:3])
        if album_ativo:
            if self._calibrar_pc is None:
                try:
                    # Reutiliza somente a função de cor; não conecta ao SDK
                    # nem envia comandos para a placa-mãe.
                    from leds_openrgb import realcar
                    self._calibrar_pc = realcar
                except ImportError:
                    self._calibrar_pc = lambda valor: valor
                    self.log("lotus: calibração de referência indisponível; usando cor original")
            if cor != self._cor_original:
                self._cor_original = cor
                self._cor_pc = self._calibrar_pc(cor)
                self.log(f"lotus: cor da capa={cor}; referência do PC={self._cor_pc}")
            cor = self._cor_pc
        brilho = config.get("lotus_brilho")
        if brilho is None:
            brilho = self.brilho_para(datetime.datetime.now())
        brilho = max(0, min(100, brilho)) / 100
        return tuple(int(max(0, min(255, c)) * brilho) for c in cor)

    def _enviar(self, cor):
        self._sequencia = self._sequencia % 15 + 1
        # DDP v1, PUSH, RGB de 8 bits, destino display, offset 0, um pixel.
        pacote = struct.pack("!BBBBIH", 0x41, self._sequencia, 1, 1, 0, 3) + bytes(cor)
        self._socket.sendto(pacote, ENDERECO)

    def _executar(self):
        pasta_ativa = None
        proxima_tentativa = 0.0
        ultima_falha = ""
        self.status("Desligada")
        try:
            while not self.parar.is_set():
                config = self.controles.config
                ativa = config.get("lotus_ativo", False)
                pasta = config.get("lotus_pasta")
                agora = time.monotonic()
                try:
                    if not ativa:
                        if self.proc is not None:
                            self._fechar(apagar=True)
                        self.status("Desligada")
                        pasta_ativa, proxima_tentativa = None, 0.0
                    else:
                        if pasta != pasta_ativa:
                            self._fechar()
                            pasta_ativa, proxima_tentativa = pasta, 0.0
                        if self.proc is not None and self.proc.poll() is not None:
                            self._fechar()
                            proxima_tentativa = agora + 10.0
                        if self.proc is None and agora >= proxima_tentativa:
                            proxima_tentativa = agora + 10.0
                            self._abrir(pasta)
                            ultima_falha = ""
                        if self.proc is not None:
                            endereco = config.get("lotus_endereco")
                            if endereco != self._endereco_selecionado:
                                self.proc.stdin.write(json.dumps({"endereco": endereco}) + "\n")
                                self.proc.stdin.flush()
                                self._endereco_selecionado = endereco
                        if self.proc is not None and (self.estado.get("midia_pronta", False)
                                                      or config.get("lotus_modo") == "manual"
                                                      or not config["tela_ligada"]):
                            alvo = self._cor_alvo()
                            if alvo != self._chave_cor:
                                self._inicio_cor = self._base_cor if self._chave_cor is not None else alvo
                                self._chave_cor, self._inicio_fade = alvo, agora
                            duracao = 0.3 if config.get("lotus_modo") == "manual" else FADE
                            t = min(1.0, (agora - self._inicio_fade) / duracao)
                            peso = (1 - math.cos(t * math.pi)) / 2
                            cor = tuple(round(a + (b - a) * peso) for a, b in zip(self._inicio_cor, alvo))
                            # Keepalive impede que o bridge desconecte por inatividade.
                            if cor != self._base_cor or agora - self._ultimo_envio >= 1.0:
                                self._enviar(cor)
                                self._base_cor, self._ultimo_envio = cor, agora
                except Exception as exc:
                    erro = ("A ponte Lotus já está aberta. Encerre a sincronização dela para usar Fita RGB."
                            if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10048
                            else str(exc))
                    self.status("Indisponível", erro)
                    if erro != ultima_falha:
                        self.log("lotus: " + erro)
                        ultima_falha = erro
                    self._fechar()
                    proxima_tentativa = agora + 10.0
                self.parar.wait(INTERVALO)
        finally:
            self._fechar()
            self.status("Desligada")

    def fechar(self):
        # O sinal é compartilhado com o motor; a thread encerra a própria ponte.
        self.parar.set()
        self._thread.join(timeout=4)
