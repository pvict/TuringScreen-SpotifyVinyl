"""Controles da sessão local do Spotify, acionados por eventos do Windows.

Não consulta a Web API, não lê capas e não controla a tela ou o OpenRGB.
Toda operação WinRT acontece na mesma thread, fora do loop gráfico do Tk.
"""
import asyncio
import contextlib
import queue
import threading


ACOES = {"anterior", "play_pause", "proxima", "aleatorio", "repetir"}


class ControlesSpotify:
    def __init__(self):
        self.eventos = queue.Queue(maxsize=8)
        self._pedidos = queue.Queue(maxsize=8)
        self._parar = threading.Event()
        self._loop = self._aviso = None
        self._sessao = None
        self._token_sessao = None
        self._renovar = True
        self._ultimo_estado = None
        threading.Thread(target=self._rodar, name="SpotifyControles", daemon=True).start()

    def enviar(self, acao):
        if acao not in ACOES or self._parar.is_set():
            return False
        try:
            self._pedidos.put_nowait(acao)
        except queue.Full:
            return False
        self._acordar()
        return True

    def _acordar(self, renovar=False):
        loop, aviso = self._loop, self._aviso
        if loop is None or aviso is None:
            return
        def avisar():
            self._renovar |= renovar
            aviso.set()
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(avisar)

    def _publicar(self, estado, forcar=False):
        if not forcar and estado == self._ultimo_estado:
            return
        self._ultimo_estado = estado
        try:
            self.eventos.put_nowait(estado)
        except queue.Full:
            with contextlib.suppress(queue.Empty):
                self.eventos.get_nowait()
            self.eventos.put_nowait(estado)

    def _rodar(self):
        try:
            from winrt.runtime import init_apartment, uninit_apartment, ApartmentType
            init_apartment(ApartmentType.MULTI_THREADED)
            try:
                asyncio.run(self._executar())
            finally:
                uninit_apartment()
        except Exception as erro:
            self._publicar({"disponivel": False,
                            "erro": f"Controles do Spotify indisponíveis: {erro}"})
        finally:
            self._parar.set()
            self._loop = self._aviso = None

    def _observar(self, sessao):
        if self._sessao is not None and self._token_sessao is not None:
            with contextlib.suppress(Exception):
                self._sessao.remove_playback_info_changed(self._token_sessao)
        self._sessao, self._token_sessao = sessao, None
        if sessao is not None:
            self._token_sessao = sessao.add_playback_info_changed(
                lambda _s, _e: self._acordar())

    def _selecionar(self, manager):
        sessoes = [s for s in manager.get_sessions()
                   if "spotify" in s.source_app_user_model_id.lower()]
        # Dá prioridade ao Spotify que está tocando; nunca usa outro player.
        sessao = next((s for s in sessoes if int(s.get_playback_info().playback_status) == 4),
                       sessoes[0] if sessoes else None)
        self._observar(sessao)
        self._renovar = False

    def _estado(self):
        sessao = self._sessao
        if sessao is None:
            return {"disponivel": False, "erro": ""}
        info = sessao.get_playback_info()
        controles = info.controls
        tocando = int(info.playback_status) == 4
        return {
            "disponivel": True, "tocando": tocando,
            "anterior": controles.is_previous_enabled,
            "proxima": controles.is_next_enabled,
            "play_pause": (controles.is_play_pause_toggle_enabled or
                           (controles.is_pause_enabled if tocando else controles.is_play_enabled)),
            "aleatorio": controles.is_shuffle_enabled and info.is_shuffle_active is not None,
            "repetir": controles.is_repeat_enabled and info.auto_repeat_mode is not None,
            "aleatorio_ativo": bool(info.is_shuffle_active),
            "repeticao": int(info.auto_repeat_mode) if info.auto_repeat_mode is not None else 0,
            "erro": "",
        }

    async def _comandar(self, acao):
        from winrt.windows.media import MediaPlaybackAutoRepeatMode
        estado = self._estado()
        if not estado.get(acao):
            return "Abra o Spotify para usar este controle." if not estado["disponivel"] else (
                "O Spotify não disponibilizou esse controle ao Windows.")
        sessao = self._sessao
        if acao == "anterior":
            pedido = sessao.try_skip_previous_async()
        elif acao == "proxima":
            pedido = sessao.try_skip_next_async()
        elif acao == "play_pause":
            info = sessao.get_playback_info()
            pedido = (sessao.try_toggle_play_pause_async() if info.controls.is_play_pause_toggle_enabled
                      else sessao.try_pause_async() if estado["tocando"] else sessao.try_play_async())
        elif acao == "aleatorio":
            pedido = sessao.try_change_shuffle_active_async(not estado["aleatorio_ativo"])
        else:
            # Desligado → repetir fila → repetir faixa → desligado.
            proximo = {0: 2, 2: 1, 1: 0}[estado["repeticao"]]
            pedido = sessao.try_change_auto_repeat_mode_async(MediaPlaybackAutoRepeatMode(proximo))
        aceito = await asyncio.wait_for(pedido, timeout=4)
        return "" if aceito else "O Spotify não aceitou esse comando."

    async def _executar(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        self._loop = asyncio.get_running_loop()
        self._aviso = asyncio.Event()
        manager = await asyncio.wait_for(GlobalSystemMediaTransportControlsSessionManager.request_async(), 5)
        tokens = []
        try:
            for adicionar, remover in (
                    (manager.add_sessions_changed, manager.remove_sessions_changed),
                    (manager.add_current_session_changed, manager.remove_current_session_changed)):
                token = adicionar(lambda _s, _e: self._acordar(renovar=True))
                tokens.append((remover, token))
            self._aviso.set()
            while not self._parar.is_set():
                await self._aviso.wait()
                self._aviso.clear()
                if self._parar.is_set():
                    break
                try:
                    if self._renovar:
                        self._selecionar(manager)
                    erro, comandou = "", False
                    while not self._pedidos.empty() and not self._parar.is_set():
                        acao = self._pedidos.get_nowait()
                        comandou = True
                        # Revalida a sessão a cada ação para não comandar uma sessão encerrada.
                        self._selecionar(manager)
                        erro = await self._comandar(acao)
                    estado = self._estado()
                    estado["erro"] = erro
                    self._publicar(estado, forcar=comandou)
                except Exception as erro:
                    self._renovar = True
                    self._publicar({"disponivel": False,
                                    "erro": f"Não foi possível controlar o Spotify: {erro}"})
        finally:
            self._observar(None)
            for remover, token in tokens:
                with contextlib.suppress(Exception):
                    remover(token)

    def fechar(self):
        self._parar.set()
        self._acordar()
