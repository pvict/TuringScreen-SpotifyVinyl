"""Registro passivo do app/SDK. Não confirma escritas SMBus ou cores físicas."""
import datetime
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import threading
import time
import uuid


class _ArquivoRotativo(RotatingFileHandler):
    def handleError(self, record):
        # Uma falha do registro desativa somente o registro, sem imprimir pilhas
        # de erros no terminal ou interromper o controle da tela/LEDs.
        raise OSError("não foi possível gravar o registro de LEDs")


class RegistroLEDs:
    def __init__(self, log):
        self.log = log
        self.sessao = uuid.uuid4().hex[:12]
        self.arquivo = Path(__file__).with_name("diagnostico_leds") / "eventos.jsonl"
        self._fila = queue.Queue(maxsize=128)
        self._parar = threading.Event()
        self._ativo = True
        self._descartados = 0
        self._thread = threading.Thread(target=self._gravar, name="RegistroLEDs", daemon=True)
        self._thread.start()
        self.registrar("inicio_registro", processo=os.getpid(),
                       limite="retornos do SDK; sem confirmação física/SMBus")

    def registrar(self, evento, **dados):
        if not self._ativo:
            return
        try:
            agora = datetime.datetime.now(datetime.timezone.utc)
            registro = {"utc": agora.isoformat(timespec="milliseconds"),
                        "utc_ms": round(agora.timestamp() * 1000),
                        "monotonic_ns": time.monotonic_ns(),
                        "sessao": self.sessao, "evento": evento, **dados}
            self._fila.put_nowait(registro)
        except queue.Full:
            # Nunca bloqueia um envio para esperar o disco.
            self._descartados += 1
        except Exception:
            self._ativo = False

    def _gravar(self):
        arquivo = None
        try:
            self.arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo = _ArquivoRotativo(self.arquivo, maxBytes=5 * 1024 * 1024,
                                      backupCount=2, encoding="utf-8", delay=True)
            arquivo.setFormatter(logging.Formatter("%(message)s"))
            while True:
                try:
                    dados = self._fila.get(timeout=0.5)
                except queue.Empty:
                    if self._parar.is_set():
                        break
                    continue
                if self._descartados:
                    dados["registros_descartados_por_fila_cheia"] = self._descartados
                    self._descartados = 0
                texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
                arquivo.emit(logging.LogRecord("leds", logging.INFO, "", 0, texto, (), None))
        except Exception as exc:
            self._ativo = False
            try:
                self.log(f"openrgb registro: indisponível ({exc}); LEDs continuam normalmente")
            except Exception:
                pass
        finally:
            if arquivo is not None:
                arquivo.close()

    def fechar(self):
        self.registrar("fim_registro")
        self._parar.set()
        self._thread.join(timeout=1.0)
