<p align="center">
  <img src="docs/images/turzx-480x480-spotify-vinyl.jpg" alt="Capa do Spotify como vinil na tela LCD redonda TURZX 480x480 instalada no water cooler" height="280">
  <img src="docs/images/turzx-480x480-openrgb-setup.jpg" alt="Turing Vinyl funcionando no PC com iluminação OpenRGB sincronizada" height="280">
  <img src="docs/images/turzx-spotify-true-colors.png" alt="True Colors de Cyndi Lauper na tela USB com iluminação RGB rosa acompanhando o álbum" height="280">
</p>

https://github.com/user-attachments/assets/f876053e-42a8-4e0f-b7f9-6a048da14437

<p align="center"><sub>24 segundos: pausa, retomada, animação da playlist e RGB sincronizado.</sub></p>

<h1 align="center">Turing Vinyl · Spotify para TURZX</h1>

<p align="center">Português · <a href="README.md">English</a></p>

Transforme uma tela compatível **TURZX / Turing Smart Screen redonda de 2,1″ (480 × 480)** em um **vinil animado do Spotify**. Um app para Windows com capa do álbum girando, informações da música, progresso e sincronização opcional com **OpenRGB** ou **fita RGB Bluetooth pelo Lotus Lantern**.

O disco desacelera ao pausar e a capa vira nas trocas de música. Escolha um vídeo de fundo, ajuste o brilho e controle o Spotify pela interface.

<p align="center"><a href="#instalação">Instalação</a> · <a href="#usando-o-app">Usando o app</a> · <a href="#tela-compatível">Tela compatível</a> · <a href="#integrações-opcionais">RGB e Spotify</a> · <a href="#ajuda">Ajuda</a></p>

## Instalação

### 1. Prepare o PC

| Você precisa de | Como preparar |
| --- | --- |
| **Windows 10/11** | Uma tela USB compatível; veja [o modelo usado](#tela-compatível). |
| **Python 3.13, 64 bits** | Instale pelo [python.org](https://www.python.org/downloads/windows/), incluindo o Python Launcher e Tcl/Tk. |
| **GPU NVIDIA com NVENC** | Instale o driver. A renderização do vinil ao vivo depende atualmente do codificador NVIDIA. |
| **FFmpeg + FFprobe** | Baixe uma versão para Windows pelos links do [ffmpeg.org](https://ffmpeg.org/download.html), com `h264_nvenc` e `libx264`. Adicione a pasta `bin` ao **Path** do Windows. |
| **Spotify para Windows** | Necessário para os modos com música. Capa e controles básicos funcionam sem criar um app no Spotify Developer. |

<details>
<summary>Como adicionar o FFmpeg ao Path</summary>

1. Extraia o FFmpeg para uma pasta permanente, por exemplo `C:\ffmpeg`.
2. Localize a pasta com **ffmpeg.exe** e **ffprobe.exe**, normalmente `C:\ffmpeg\bin`.
3. Pesquise no Windows por **Editar as variáveis de ambiente da sua conta**. Em **Variáveis de usuário**, selecione **Path → Editar → Novo** e cole o caminho completo dessa pasta.
4. Confirme em **OK** e reabra o PowerShell e o Turing Vinyl após alterar o Path.

</details>

### 2. Baixe e instale uma vez

[Baixe o ZIP do projeto](https://github.com/pvict/TuringScreen-SpotifyVinyl/archive/refs/heads/master.zip) e extraia para uma pasta permanente. Abra a pasta extraída que contém **README.md**. Digite `powershell` na barra de endereço do Explorador de Arquivos e pressione **Enter**.

Cole este bloco na janela do PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe criar_atalho.py
```

### 3. Abra o Turing Vinyl

Dê dois cliques em **Turing Vinyl.lnk**, na pasta do projeto. Use esse atalho no dia a dia; você pode fixá-lo na barra de tarefas. Mantenha a pasta do projeto no lugar para que o atalho e os vídeos incluídos continuem disponíveis.

## Usando o app

<p align="center">
  <img src="docs/images/turing-vinyl-interface.png" alt="Interface do Turing Vinyl no Windows: disco girando, controles do Spotify, modos de exibição e slider de brilho" width="860">
</p>

1. Conecte a tela por USB e coloque uma música no **Spotify para Windows**.
2. Abra o **Turing Vinyl**, escolha um modo e clique em **Iniciar**.
3. Clique em **Parar** quando terminar.

| Modo | O que aparece na tela |
| --- | --- |
| **Dinâmico** | Vinil enquanto a música toca; vídeo de fundo durante a pausa ou ociosidade. |
| **Spotify** | O vinil permanece visível; para suavemente e a capa encolhe ao pausar. |
| **Vídeo** | Apenas o vídeo de fundo. |
| **Gaming** | Repete um fundo preparado a 30 FPS, com menos processamento e sem informações da música. Desative para voltar ao modo escolhido. |

| Controle | Para que serve |
| --- | --- |
| **Brilho / Auto** | Ajusta o brilho da tela ou o define pelo horário. **0%** e o botão de energia apagam a tela. |
| **Botões de música** | Aleatório, anterior, play/pause, próxima e repetição, quando o Spotify disponibiliza esses controles ao Windows. |
| **Fundo → Escolher vídeo** | Escolha seu fundo; o app converte e salva a seleção. **Padrão** restaura o vídeo incluído. |

<details>
<summary>Ver o painel de vídeo de fundo</summary>

<img src="docs/images/turing-vinyl-background.png" alt="Painel de escolha do vídeo de fundo no Turing Vinyl com progresso da conversão" width="860">

</details>

## Tela compatível

As fotos mostram a **tela IPS USB redonda de 2,1″, 480 × 480**, vendida como *“2.1 Inch IPS Secondary Screen Water-Cooled Round Screen”*, com **TURZX** como aplicativo de customização indicado pelo vendedor. [Veja o anúncio no AliExpress](https://pt.aliexpress.com/item/1005006523861753.html).

O Turing Vinyl se comunica diretamente por USB usando o identificador **`1CBE:0021`**. Feche o TURZX durante o uso. Telas visualmente iguais podem usar outro protocolo; **modelos de 2,8″ e outras telas ainda não foram validados**.

## Integrações opcionais

| Integração | O que adiciona | Como configurar |
| --- | --- | --- |
| **Spotify Web API** | Capa da playlist e aviso de **A seguir**. | [Ativar playlist e A seguir](docs/integrations.pt-BR.md#playlist-e-a-seguir) |
| **OpenRGB** | LEDs do PC acompanham o álbum. Preset atual: **ASRock B450M Steel Legend**. | [Conectar o OpenRGB](docs/integrations.pt-BR.md#leds-do-pc-com-openrgb) |
| **Lotus Lantern** | Fita Bluetooth acompanha o álbum; validada na **ELK-BLEDDM**. | [Conectar a fita RGB](docs/integrations.pt-BR.md#fita-bluetooth-com-lotus-lantern) |

Essas integrações são opcionais. O guia também explica a calibração da fita e os registros de conexão.

## Ajuda

| Problema | O que fazer |
| --- | --- |
| O comando `py` não é reconhecido | Instale o Python 3.13 com o Launcher e reabra o PowerShell. |
| Nada aparece após **Iniciar** | Confira USB, [compatibilidade da tela](#tela-compatível), FFmpeg no Path e suporte a NVENC. Feche outros apps que usam a tela. |
| Botões de música desativados | Coloque uma faixa no Spotify para Windows para disponibilizar a sessão de mídia. |
| Playlist / A seguir não aparece | Siga a [configuração do Spotify](docs/integrations.pt-BR.md#playlist-e-a-seguir), incluindo autorização e requisitos do modo de desenvolvimento. |
| LEDs do PC ou fita não respondem | Siga o [guia de configuração RGB](docs/integrations.pt-BR.md) correspondente. |

Ainda precisa de ajuda? [Abra uma issue](https://github.com/pvict/TuringScreen-SpotifyVinyl/issues) com o horário, o que você clicou e as linhas relevantes de **tela.log**, na pasta do projeto. Remova dados pessoais antes de compartilhar os registros.

## Créditos e licença

Comunicação USB: [Turing Smart Screen CLI](https://github.com/phstudy/turing-smart-screen-cli) ([MIT](turing-smart-screen-cli-main/LICENSE)). Fontes: Fraunces e DM Sans ([OFL](assets/fonts/fraunces-OFL.txt), [OFL](assets/fonts/dmsans-OFL.txt)). Integração Bluetooth: [Lotus Lantern para Windows](https://github.com/razibit/Lotus-Lantern-for-Windows-PC). Projeto relacionado para essas telas: [turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python).

Projeto não oficial de [Paulo](https://github.com/pvict). Uma licença para o código e as mídias próprios ainda não foi declarada.
