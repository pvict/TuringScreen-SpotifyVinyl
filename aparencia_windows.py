"""Decoração nativa; materiais da janela podem ser gerenciados externamente.

Não define Accent Policy, backdrop DWM ou margens de vidro. O Mica For Everyone
pode gerenciar a moldura sem disputa de políticas. O conteúdo do Tk permanece
opaco para preservar contraste, tipografia e controles.
"""


def preparar_janela(janela):
    """Preserva a moldura nativa, sem alterar políticas do compositor."""
    janela.overrideredirect(False)
