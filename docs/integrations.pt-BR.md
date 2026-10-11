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

### 2. Configure o endereço da fita

Ligue o Bluetooth e a fita. Depois que o Windows detectar a controladora, execute no PowerShell:

```powershell
Get-PnpDevice -Class Bluetooth |
  Where-Object FriendlyName -Like 'ELK*' |
  Select-Object FriendlyName, InstanceId
```

Em um identificador como `BTHLE\DEV_AA11BB22CC33\...`, **AA11BB22CC33** é o endereço. Edite **config.cmd**, na pasta do Lotus, e altere a linha existente para o seu endereço, sem dois-pontos nem hífens:

```bat
set LED_DEVICE_UUID=AA11BB22CC33
```

Use o seu endereço, não o exemplo. Se nenhum dispositivo aparecer, confira as configurações de Bluetooth do Windows. Se o endereço mudar depois, atualize essa linha.

### 3. Conecte pelo Turing Vinyl

1. Feche o Lotus no celular e qualquer outro programa que controle a fita.
2. Abra o **Turing Vinyl** e clique em **Fita RGB**. No primeiro uso, escolha a **pasta do Lotus** que você preparou.
3. Clique em **Iniciar** na janela principal. A fita acompanha as cores do álbum e o brilho usado para os LEDs do PC, com transições suaves.

Clique com o botão direito em **Fita RGB** para trocar a pasta do Lotus. Passe o mouse sobre ele para ver o estado da conexão. Clicar novamente desativa a sincronização; parar o app mantém a última cor na fita.

O Turing Vinyl inicia sua própria ponte Bluetooth. Deixe o iniciador do Lotus fechado; essa integração não exige OpenRGB nem o plugin Effects. Em caso de falha de conexão, a ponte tenta novamente o endereço configurado.

### Calibração das cores e registros

O arquivo incluído [calibracao_lotus.example.json](../calibracao_lotus.example.json) é usado por padrão. Cada fita pode reproduzir as cores de um jeito. Para ajustar a sua:

1. Copie esse arquivo como **calibracao_lotus.json** na pasta do Turing Vinyl.
2. Ajuste **ganhos_rgb** para equilibrar vermelho, verde e azul; **ganhos_quentes** ajusta os tons quentes gradualmente.
3. Cada ganho aceita valores de **0 a 2**. `[1, 1, 1]` deixa o respectivo ajuste neutro. As alterações são lidas enquanto o app está rodando.

Sua calibração local fica fora do Git. Os registros de conexão ficam em **diagnostico_leds/lotus.log**; os horários desse arquivo usam **UTC**.

Se a fita não responder, confira alimentação, Bluetooth, endereço, Node.js e dependências do Lotus. Verifique também se outra ponte Lotus está usando a porta local `4048`.
