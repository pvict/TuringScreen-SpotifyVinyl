# Integrações opcionais

[Voltar ao README](../README.pt-BR.md) · [English](integrations.md)

Instale o Turing Vinyl primeiro. Configure apenas as integrações que quiser; a exibição básica da música usa a sessão de mídia do Spotify no Windows.

## Playlist e A seguir

**Adiciona:** capa da playlist, nome da playlist quando disponível e aviso da próxima música.

1. Crie seu próprio app no [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), selecionando **Web API**.
2. Nas configurações dele, adicione esta **Redirect URI** e salve:

   ```text
   http://127.0.0.1:8765/callback
   ```

3. Copie o **Client ID**. Na pasta do Turing Vinyl, crie **spotify_client_id.txt** contendo apenas esse ID. No Bloco de Notas, use **Tipo: Todos os arquivos** para evitar que o nome vire `spotify_client_id.txt.txt`.
4. Abra o Turing Vinyl, clique em **Iniciar** e autorize sua conta do Spotify no navegador quando solicitado.

Não precisa de Client Secret. No modo de desenvolvimento do Spotify, o dono do app precisa de **Premium**. Outras contas devem ser adicionadas em **Settings → Users Management**; caso contrário, as consultas podem falhar com **403**. Veja os [requisitos do modo de desenvolvimento do Spotify](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).

A playlist aparece por **5 segundos**. **A seguir** entra cerca de **22 segundos antes do fim**, durante **7 segundos**, quando o Spotify informa a fila. Esses recursos extras precisam de internet.

## LEDs do PC com OpenRGB

**Adiciona:** sincronização das cores do álbum nos LEDs compatíveis do PC.

1. Instale o [OpenRGB](https://openrgb.org/) e confira se ele detecta sua placa-mãe.
2. Ative o **servidor SDK** em `127.0.0.1:6742`.
3. Deixe o OpenRGB aberto, abra o Turing Vinyl e clique em **Iniciar**.

O preset atual controla as zonas **Addressable Header, PCH e IO Cover** da **ASRock B450M Steel Legend**. A cor no fundo/ociosidade vem do perfil `purple rain` salvo em cache. Outras controladoras precisam de configuração própria; o app ainda não oferece seleção de dispositivos RGB.

Feche outros programas de iluminação que controlem o mesmo dispositivo para evitar comandos conflitantes.

## Fita Bluetooth com Lotus Lantern

**Adiciona:** sincronização das cores do álbum em uma fita RGB Bluetooth, independente do OpenRGB. Experimental; validada na **ELK-BLEDDM**.

### 1. Prepare o Lotus uma vez

Instale o [Node.js](https://nodejs.org/) **18 ou superior**, depois baixe e extraia o [Lotus Lantern para Windows](https://github.com/razibit/Lotus-Lantern-for-Windows-PC). Abra o PowerShell na pasta extraída dele e execute:

```powershell
npm.cmd ci
```

Mantenha a pasta com **config.cmd**, **src/ble-device.cjs** e **node_modules**.

### 2. Conecte pelo Turing Vinyl

1. Ligue o Bluetooth e a fita. Feche o Lotus no celular e outros programas que a controlem.
2. Abra **Turing Vinyl → Fita RGB** para mostrar o painel de controle.
3. Clique em **Desligada** para ativar a fita. No primeiro uso, escolha a **pasta do Lotus** que você preparou.
4. Clique em **Iniciar** na janela principal. O painel mostra o estado da conexão; **Pasta Lotus** troca a pasta usada.

O app procura uma **ELK-BLEDDM** compatível e pode reencontrá-la após uma falha de conexão se o endereço mudar. Se encontrar várias fitas compatíveis, escolha a sua no painel. O endereço confirmado é salvo localmente; o `config.cmd` não é reescrito.

<details>
<summary>Opcional: informar um endereço Bluetooth conhecido</summary>

Você pode fornecer um endereço inicial no **config.cmd** do Lotus. Depois que o Windows detectar a fita, consulte-o no PowerShell:

```powershell
Get-PnpDevice -Class Bluetooth |
  Where-Object FriendlyName -Like 'ELK*' |
  Select-Object FriendlyName, InstanceId
```

Em um identificador como `BTHLE\DEV_AA11BB22CC33\...`, **AA11BB22CC33** é o endereço. Edite **config.cmd**, na pasta do Lotus, e altere a linha existente para o seu endereço, sem dois-pontos nem hífens:

```bat
set LED_DEVICE_UUID=AA11BB22CC33
```

Use o seu endereço, não o exemplo. Se nenhum dispositivo aparecer, confira as configurações de Bluetooth do Windows.

</details>

### 3. Escolha cor e brilho

- **Música:** acompanha a cor do álbum com transições suaves.
- **Manual:** escolha uma cor fixa pela roda ou pelos campos **RGB, HSV ou HEX**.
- **Brilho da fita:** ajusta a fita de forma independente. **Tela** acompanha o brilho dos LEDs do PC.
- **Ligada / Desligada:** controla a fita; fechar o painel mantém os ajustes.

O Turing Vinyl inicia sua própria ponte Bluetooth. Deixe o iniciador do Lotus fechado; essa integração não exige OpenRGB nem o plugin Effects. Parar o app mantém a última cor na fita.

### Calibração das cores e registros

O arquivo incluído [calibracao_lotus.example.json](../calibracao_lotus.example.json) é usado por padrão. Cada fita pode reproduzir as cores de um jeito. Para ajustar a sua:

1. Copie esse arquivo como **calibracao_lotus.json** na pasta do Turing Vinyl.
2. Ajuste **ganhos_rgb** para equilibrar vermelho, verde e azul; **ganhos_quentes** ajusta os tons quentes gradualmente.
3. Cada ganho aceita valores de **0 a 2**. `[1, 1, 1]` deixa o respectivo ajuste neutro. As alterações são lidas enquanto o app está rodando.

Sua calibração local fica fora do Git. Os registros de conexão ficam em **diagnostico_leds/lotus.log**; os horários desse arquivo usam **UTC**.

Se a fita não responder, confira alimentação, Bluetooth, endereço, Node.js e dependências do Lotus. Verifique também se outra ponte Lotus está usando a porta local `4048`.
