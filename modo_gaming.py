"""Gaming: prepara o fundo uma vez e transmite H.264 sem renderização ao vivo."""
import hashlib
import json
import mmap
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import ao_vivo
from controle_interface import ARQUIVO

FPS_GAMING = 30
VERSAO_CACHE = 1
PASTA_GAMING = ARQUIVO.parent / "gaming"
FLAGS = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
         | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
AUD = re.compile(b"\x00\x00\x00?\x01\x09")


class _Cancelado(Exception):
    pass


def ler_indice(caminho):
    """Valida a lista de quadros sem decodificar imagens nem abrir FFmpeg."""
    caminho = Path(caminho)
    dados = json.loads(caminho.with_suffix(".json").read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or not isinstance(dados.get("offsets"), list):
        raise ValueError("O índice Gaming precisa ser preparado novamente.")
    offsets = dados.get("offsets", [])
    if (dados.get("versao") != VERSAO_CACHE or dados.get("fps") != FPS_GAMING
            or len(offsets) < 2 or offsets[0] != 0
            or any(type(n) is not int for n in offsets)
            or any(b <= a for a, b in zip(offsets, offsets[1:]))
            or offsets[-1] != caminho.stat().st_size):
        raise ValueError("O arquivo Gaming precisa ser preparado novamente.")
    return offsets


class PreparadorGaming:
    """Conversão cancelável, com duas threads e prioridade reduzida no Windows."""
    def __init__(self, controles, estado, parar, padrao, log):
        self.controles, self.estado, self.parar = controles, estado, parar
        self.padrao, self.log = padrao, log
        self.pronto = None
        self.encerrar = threading.Event()
        self.thread = threading.Thread(target=self._vigiar, name="PrepararGaming", daemon=True)

    def iniciar(self):
        self.thread.start()

    def _solicitacao(self):
        config = self.controles.config
        return (config.get("video_ocioso") or self.padrao) if config.get("gaming") else None

    def destino(self):
        # Durante a preparação de outro fundo, mantém o anterior se já estiver ativo.
        solicitacao, pronto = self._solicitacao(), self.pronto
        if solicitacao is None or pronto is None:
            return None
        if pronto[0] != solicitacao and not self.controles.gaming_ativo:
            return None
        return pronto[1]

    def origem_do(self, arquivo):
        pronto = self.pronto
        return (pronto[0] if pronto and pronto[1] == arquivo and pronto[0] != self.padrao
                else None)

    def _conferir_cancelamento(self, solicitacao):
        if (self.parar.is_set() or self.encerrar.is_set()
                or self._solicitacao() != solicitacao):
            raise _Cancelado()

    def _preparar(self, solicitacao):
        self._conferir_cancelamento(solicitacao)
        origem = Path(solicitacao).resolve()
        stat = origem.stat()
        chave = hashlib.sha256(
            f"{VERSAO_CACHE}|{origem}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
        ).hexdigest()[:24]
        PASTA_GAMING.mkdir(parents=True, exist_ok=True)
        destino = PASTA_GAMING / f"{chave}.h264"
        try:
            ler_indice(destino)
            return str(destino)
        except (OSError, ValueError, TypeError, KeyError):
            pass

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg não encontrado para preparar Gaming.")
        temporario = PASTA_GAMING / f".preparando-{uuid.uuid4().hex}.h264"
        arquivo_erros = temporario.with_suffix(".erro.tmp")
        indice_tmp = temporario.with_suffix(".json")
        proc = None
        self.log("Gaming: preparando fundo a 30 FPS; o arquivo original será preservado")
        try:
            with arquivo_erros.open("wb") as erros:
                proc = subprocess.Popen([
                    ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-filter_threads", "1", "-threads", "2", "-i", str(origem),
                    "-map", "0:v:0", "-vf",
                    "scale=480:480:force_original_aspect_ratio=increase,crop=480:480,setsar=1",
                    "-r", str(FPS_GAMING), "-an", "-sn", "-dn", "-c:v", "libx264",
                    "-threads", "2", "-preset", "fast", "-tune", "zerolatency",
                    "-crf", "18", "-maxrate", "5000k", "-bufsize", "2500k",
                    "-profile:v", "baseline", "-pix_fmt", "yuv420p", "-bf", "0",
                    "-g", "15", "-keyint_min", "15", "-sc_threshold", "0",
                    "-x264-params", "aud=1:repeat-headers=1:open-gop=0",
                    "-f", "h264", "-n", str(temporario),
                ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=erros, creationflags=FLAGS)
                while proc.poll() is None:
                    self._conferir_cancelamento(solicitacao)
                    self.encerrar.wait(0.2)
            self._conferir_cancelamento(solicitacao)
            if proc.returncode or not temporario.is_file() or temporario.stat().st_size == 0:
                with arquivo_erros.open("rb") as erros:
                    erros.seek(max(0, arquivo_erros.stat().st_size - 1000))
                    detalhe = erros.read().decode("utf-8", errors="replace").strip()[-250:]
                raise RuntimeError("Não foi possível preparar Gaming. " + detalhe)

            # AUD separa os quadros completos. O índice é criado uma vez, fora da reprodução.
            with temporario.open("rb") as arquivo:
                with mmap.mmap(arquivo.fileno(), 0, access=mmap.ACCESS_READ) as video:
                    offsets = [m.start() for m in AUD.finditer(video)]
                    if not offsets:
                        raise RuntimeError("O vídeo preparado não contém os quadros esperados.")
                    offsets[0] = 0  # inclui qualquer cabeçalho anterior ao primeiro AUD
                    offsets.append(len(video))
                    nals_iniciais = {
                        video[m.end()] & 31
                        for m in re.finditer(b"\x00\x00\x00?\x01", video[:offsets[1]])
                        if m.end() < offsets[1]
                    }
                    if not {5, 7, 8}.issubset(nals_iniciais):
                        raise RuntimeError("O vídeo não começa com um quadro independente e seus cabeçalhos.")
            self._conferir_cancelamento(solicitacao)
            stat_atual = origem.stat()
            if (stat_atual.st_size, stat_atual.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                raise RuntimeError("O vídeo mudou durante a preparação. Desligue e ligue Gaming para repetir.")
            indice_tmp.write_text(json.dumps({"versao": VERSAO_CACHE, "fps": FPS_GAMING,
                                               "offsets": offsets}), encoding="utf-8")
            os.replace(temporario, destino)
            os.replace(indice_tmp, destino.with_suffix(".json"))
            self.log("Gaming: fundo preparado e salvo no cache local")
            return str(destino)
        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            for arquivo in (temporario, arquivo_erros, indice_tmp):
                arquivo.unlink(missing_ok=True)

    def _vigiar(self):
        tentado = None
        while not self.parar.is_set() and not self.encerrar.is_set():
            solicitacao = self._solicitacao()
            if solicitacao is None:
                tentado = None
                self.estado.update(gaming_preparando=False, erro_gaming="")
            elif solicitacao != tentado:
                tentado = solicitacao
                self.estado.update(gaming_preparando=True, erro_gaming="")
                try:
                    pronto = self._preparar(solicitacao)
                    self._conferir_cancelamento(solicitacao)
                    # A origem e o cache são publicados juntos, sem um arquivo incompleto.
                    self.pronto = (solicitacao, pronto)
                except _Cancelado:
                    tentado = None
                except Exception as exc:
                    self.estado["erro_gaming"] = str(exc)
                    self.log(f"Gaming: {exc}; mantendo a exibição anterior")
                finally:
                    self.estado["gaming_preparando"] = False
            self.encerrar.wait(0.25)

    def fechar(self):
        self.encerrar.set()
        self.thread.join(timeout=5)


class _FontePreparada:
    """A mesma fila de bytes do fluxo normal, sem codificador ou captura em disco."""
    def __init__(self):
        self.saida = ao_vivo.FilaVideo()
        self.captura = None


class PipelinePreparado:
    """Lê quadros completos do arquivo em loop; só a thread USB fala com a tela."""
    def __init__(self, dev, caminho, parar, log):
        self.caminho = Path(caminho)
        self.offsets = ler_indice(self.caminho)
        self.parar, self.log = parar, log
        self.cod = _FontePreparada()
        self.env = ao_vivo.EnviadorUSB(dev, self.cod, parar, log=log)

    def rodar(self):
        self.env.start()
        try:
            with self.caminho.open("rb") as video:
                quadro = 0
                proximo = time.monotonic()
                while not self.parar.is_set():
                    if self.env.erro:
                        raise self.env.erro
                    fim = self.offsets[quadro + 1]
                    restante = fim - self.offsets[quadro]
                    while restante and not self.parar.is_set():
                        tamanho = min(restante, ao_vivo.LIMITE_FILA_BYTES)
                        if self.cod.saida.bytes_pendentes() + tamanho > ao_vivo.LIMITE_FILA_BYTES:
                            if self.env.erro:
                                raise self.env.erro
                            self.parar.wait(0.005)
                            continue
                        dados = video.read(tamanho)
                        if len(dados) != tamanho:
                            raise RuntimeError("O arquivo Gaming foi removido ou ficou incompleto.")
                        self.cod.saida.put((time.monotonic(), dados))
                        restante -= tamanho
                    quadro += 1
                    if quadro == len(self.offsets) - 1:
                        video.seek(0)
                        quadro = 0
                    proximo += 1.0 / FPS_GAMING
                    espera = proximo - time.monotonic()
                    if espera > 0:
                        self.parar.wait(espera)
                    elif espera < -0.25:
                        proximo = time.monotonic()
        finally:
            self.parar.set()
            self.env.join(timeout=8)
            if self.env.is_alive():
                raise RuntimeError("O envio USB ainda está encerrando; não é seguro iniciar outro fluxo.")
