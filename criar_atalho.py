"""Cria Turing Vinyl.lnk, com nome, ícone e identidade próprios para fixar no dock."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys

from aparencia_windows import APP_ID, APP_NOME, _GUID, _Chave, _PropVariant


def criar_atalho():
    if os.name != "nt":
        raise RuntimeError("Este atalho requer Windows.")
    from comtypes.client import CreateObject
    raiz = Path(__file__).resolve().parent
    caminho = raiz / f"{APP_NOME}.lnk"
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    if pythonw.is_file():
        python = pythonw
    shell = CreateObject("WScript.Shell", dynamic=True)
    atalho = shell.CreateShortcut(str(caminho))
    atalho.TargetPath = str(python)
    atalho.Arguments = subprocess.list2cmdline([str(raiz / "iniciar_interface.pyw")])
    atalho.WorkingDirectory = str(raiz)
    atalho.IconLocation = f"{raiz / 'assets' / 'icons' / 'turing-vinyl.ico'},0"
    atalho.Description = APP_NOME
    atalho.Save()

    api = ctypes.WinDLL("shell32")
    api.SHGetPropertyStoreFromParsingName.argtypes = [
        wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    api.SHGetPropertyStoreFromParsingName.restype = ctypes.c_long
    iid = _GUID.criar("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")
    store = ctypes.c_void_p()
    hr = api.SHGetPropertyStoreFromParsingName(str(caminho), None, 2, ctypes.byref(iid), ctypes.byref(store))
    if hr < 0:
        raise OSError(f"Não foi possível gravar a identidade do atalho ({hr:#x}).")
    tabela = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    set_valor = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                  ctypes.POINTER(_Chave), ctypes.POINTER(_PropVariant))(tabela[6])
    commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(tabela[7])
    release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(tabela[2])
    try:
        chave = _Chave(_GUID.criar("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"), 5)
        buffer = ctypes.create_unicode_buffer(APP_ID)
        valor = _PropVariant()
        valor.vt = 31
        valor.valor.ponteiro = ctypes.cast(buffer, ctypes.c_void_p).value
        hr = set_valor(store, ctypes.byref(chave), ctypes.byref(valor))
        if hr < 0:
            raise OSError(f"Não foi possível definir o AppUserModelID ({hr:#x}).")
        hr = commit(store)
        if hr < 0:
            raise OSError(f"Não foi possível salvar a identidade do atalho ({hr:#x}).")
    finally:
        release(store)
    return caminho


if __name__ == "__main__":
    print(criar_atalho())
