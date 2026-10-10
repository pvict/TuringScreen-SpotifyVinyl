"""Moldura clara e identidade do Turing Vinyl no Windows, sem transparência."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import uuid


APP_ID = "TuringScreen.SpotifyVinyl.Interface"
APP_NOME = "Turing Vinyl"


def preparar_identidade_processo():
    """Precisa acontecer antes de criar qualquer janela Tk."""
    if os.name != "nt":
        return
    try:
        shell = ctypes.WinDLL("shell32")
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        shell.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (OSError, AttributeError):
        pass


def preparar_janela(janela, fundo, texto, caminho_icone, caminho_app):
    janela.overrideredirect(False)
    if os.name != "nt":
        return None
    try:
        return MolduraWindows(janela, fundo, texto, caminho_icone, caminho_app)
    except (OSError, AttributeError) as erro:
        print(f"interface: decoração nativa indisponível ({erro})", flush=True)
        return None


class _GUID(ctypes.Structure):
    _fields_ = [("dados", ctypes.c_ubyte * 16)]

    @classmethod
    def criar(cls, texto):
        return cls.from_buffer_copy(uuid.UUID(texto).bytes_le)


class _Chave(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", wintypes.DWORD)]


class _Valor(ctypes.Union):
    _fields_ = [("ponteiro", ctypes.c_void_p), ("espaco", ctypes.c_void_p * 2)]


class _PropVariant(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("reservados", ctypes.c_ushort * 3),
                ("valor", _Valor)]


class MolduraWindows:
    def __init__(self, janela, fundo, texto, caminho_icone, caminho_app):
        self.janela = janela
        self._store = ctypes.c_void_p()
        self._chaves = []
        self._icones = []
        self._com_iniciado = False
        self._fechado = False
        self._user = ctypes.WinDLL("user32", use_last_error=True)
        self._user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self._user.GetAncestor.restype = wintypes.HWND
        # Tk fornece o HWND interno; a barra e o botão da taskbar pertencem ao wrapper.
        self.hwnd = self._user.GetAncestor(janela.winfo_id(), 2)
        self._fundo, self._texto = fundo, texto
        self.aplicar_cores()
        self._foco = janela.bind("<FocusIn>", self._ativar, add="+")
        self._map = janela.bind("<Map>", self._ativar, add="+")
        try:
            self._definir_icones(caminho_icone)
            self._definir_identidade(caminho_icone, caminho_app)
        except (OSError, AttributeError) as erro:
            print(f"interface: identidade da barra de tarefas incompleta ({erro})", flush=True)

    def _ativar(self, evento):
        if evento.widget is self.janela and not self._fechado:
            self.aplicar_cores()

    def aplicar_cores(self):
        try:
            dwm = ctypes.WinDLL("dwmapi")
            dwm.DwmSetWindowAttribute.argtypes = [
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            dwm.DwmSetWindowAttribute.restype = ctypes.c_long

            def cor(hexadecimal):
                r, g, b = (int(hexadecimal[i:i + 2], 16) for i in (1, 3, 5))
                return r | (g << 8) | (b << 16)

            # Somente cores da moldura; nenhum efeito de vidro, alpha ou blur.
            for atributo, valor in ((20, 0), (35, cor(self._fundo)),
                                     (36, cor(self._texto)), (34, 0xFFFFFFFE)):
                dado = wintypes.DWORD(valor)
                dwm.DwmSetWindowAttribute(self.hwnd, atributo, ctypes.byref(dado), ctypes.sizeof(dado))
        except (OSError, AttributeError):
            pass  # Windows anteriores mantêm a barra de título nativa.

    def _definir_icones(self, caminho):
        self._user.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                         wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self._user.LoadImageW.restype = wintypes.HANDLE
        self._user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                           wintypes.WPARAM, wintypes.LPARAM]
        self._user.SendMessageW.restype = ctypes.c_ssize_t
        self._user.GetSystemMetrics.argtypes = [ctypes.c_int]
        self._user.GetSystemMetrics.restype = ctypes.c_int
        for tipo, metrica in ((0, 49), (1, 11)):
            lado = self._user.GetSystemMetrics(metrica)
            handle = self._user.LoadImageW(None, str(caminho), 1, lado, lado, 0x10)
            if handle:
                self._icones.append(handle)
                self._user.SendMessageW(self.hwnd, 0x0080, tipo, handle)  # WM_SETICON

    def _definir_identidade(self, caminho_icone, caminho_app):
        self._ole = ctypes.WinDLL("ole32")
        self._ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        self._ole.CoInitializeEx.restype = ctypes.c_long
        self._ole.CoUninitialize.argtypes = []
        self._ole.CoUninitialize.restype = None
        hr = self._ole.CoInitializeEx(None, 2)
        self._com_iniciado = hr >= 0
        if hr < 0 and hr != -2147417850:  # RPC_E_CHANGED_MODE: COM já está inicializado.
            raise OSError(f"CoInitializeEx: {hr:#x}")
        shell = ctypes.WinDLL("shell32")
        shell.SHGetPropertyStoreForWindow.argtypes = [
            wintypes.HWND, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        shell.SHGetPropertyStoreForWindow.restype = ctypes.c_long
        iid = _GUID.criar("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")
        hr = shell.SHGetPropertyStoreForWindow(self.hwnd, ctypes.byref(iid), ctypes.byref(self._store))
        if hr < 0:
            raise OSError(f"SHGetPropertyStoreForWindow: {hr:#x}")
        tabela = ctypes.cast(self._store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        self._set = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                      ctypes.POINTER(_Chave), ctypes.POINTER(_PropVariant))(tabela[6])
        self._release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(tabela[2])
        python = Path(sys.executable)
        pythonw = python.with_name("pythonw.exe")
        if pythonw.is_file():
            python = pythonw
        comando = subprocess.list2cmdline([str(python), str(caminho_app)])
        # Nome, ícone e comando são definidos antes da identidade explícita da janela.
        for pid, texto in ((2, comando), (3, f"{caminho_icone},0"), (4, APP_NOME), (5, APP_ID)):
            chave = _Chave(_GUID.criar("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"), pid)
            buffer = ctypes.create_unicode_buffer(texto)
            valor = _PropVariant()
            valor.vt = 31  # VT_LPWSTR; SetValue copia o texto antes de retornar.
            valor.valor.ponteiro = ctypes.cast(buffer, ctypes.c_void_p).value
            hr = self._set(self._store, ctypes.byref(chave), ctypes.byref(valor))
            if hr < 0:
                raise OSError(f"IPropertyStore.SetValue: {hr:#x}")
            self._chaves.append(chave)

    def fechar(self):
        if self._fechado:
            return
        self._fechado = True
        self.janela.unbind("<FocusIn>", self._foco)
        self.janela.unbind("<Map>", self._map)
        if self._store and hasattr(self, "_release"):
            vazio = _PropVariant()  # VT_EMPTY devolve os recursos das propriedades.
            for chave in self._chaves:
                self._set(self._store, ctypes.byref(chave), ctypes.byref(vazio))
            self._release(self._store)
        self._user.DestroyIcon.argtypes = [wintypes.HANDLE]
        self._user.DestroyIcon.restype = wintypes.BOOL
        for handle in self._icones:
            self._user.DestroyIcon(handle)
        if self._com_iniciado:
            self._ole.CoUninitialize()
