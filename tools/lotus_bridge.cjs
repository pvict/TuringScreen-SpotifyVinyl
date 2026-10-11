// Adaptador local para o Device instalado no Lotus Lantern para Windows.
// Não altera arquivos/configuração do Lotus ou do OpenRGB.
const { createSocket } = require('node:dgram');
const { join } = require('node:path');
const { appendFileSync, mkdirSync, readFileSync, statSync } = require('node:fs');
const { createRequire } = require('node:module');
const fromLotus = createRequire(join(process.argv[2], 'src', 'ble-device.cjs'));
const Peripheral = fromLotus('noble/lib/peripheral');
const noble = require(join(process.argv[2], 'node_modules', 'noble-winrt'));
const Device = require(join(process.argv[2], 'src', 'ble-device.cjs'));
const device = new Device(process.argv[3]);
const server = createSocket('udp4');
let pending = null;
let busy = false;
let ready = false;
let lastStatus = '';
let nextConnect = 0;
let closing = false;
let firstColor = true;
let rgbGains = [1, 1, 1];
let warmGains = [1, 1, 1];
let calibrationTime = 0;
let calibrationStamp = '';
let fixedColor = null;
let fixedUntil = 0;
let calibrationWritePending = false;

function calibrate(color) {
  // Preferências locais consultadas uma vez/s, fora da renderização da tela.
  if (Date.now() >= calibrationTime) {
    calibrationTime = Date.now() + 1000;
    try {
      let file = join(__dirname, '..', 'calibracao_lotus.json');
      let modified;
      try {
        modified = statSync(file).mtimeMs;
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
        // A instalação nova recebe a base publicada. Ajustes pessoais
        // ficam no JSON local, que tem prioridade e não entra no Git.
        file = join(__dirname, '..', 'calibracao_lotus.example.json');
        modified = statSync(file).mtimeMs;
      }
      const stamp = `${file}:${modified}`;
      if (stamp !== calibrationStamp) {
        const config = JSON.parse(readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
        const gains = config.ganhos_rgb || config.ganhos_neutros;
        if (!Array.isArray(gains) || gains.length !== 3 ||
            !gains.every(v => Number.isFinite(v) && v >= 0 && v <= 2)) {
          throw new Error('ganhos_rgb deve conter três valores entre 0 e 2');
        }
        const warm = config.ganhos_quentes || [1, 1, 1];
        if (!Array.isArray(warm) || warm.length !== 3 ||
            !warm.every(v => Number.isFinite(v) && v >= 0 && v <= 2)) {
          throw new Error('ganhos_quentes deve conter três valores entre 0 e 2');
        }
        rgbGains = gains;
        warmGains = warm;
        const fixed = config.cor_fixa;
        fixedColor = Array.isArray(fixed) && fixed.length === 3 &&
          fixed.every(v => Number.isInteger(v) && v >= 0 && v <= 255) ? fixed : null;
        fixedUntil = Number.isFinite(config.cor_fixa_ate_utc_ms)
          ? Math.min(config.cor_fixa_ate_utc_ms, Date.now() + 15 * 60 * 1000) : 0;
        calibrationStamp = stamp;
        calibrationWritePending = true;
        record('Equilíbrio da fita R,G,B=' + gains.join(','));
        record('Ajuste dos tons quentes R,G,B=' + warmGains.join(','));
        if (fixedColor && Date.now() < fixedUntil) record('Cor fixa temporária: ' + fixedColor.join(','));
      }
    } catch (error) {
      if (error.code === 'ENOENT') {
        rgbGains = [1, 1, 1];
        warmGains = [1, 1, 1];
        fixedColor = null;
      }
      // Arquivo em edição/inválido conserva a última calibração válida.
    }
  }
  // Comparação manual autorizada: uma cor estática, sem sequência automática.
  // Expira e retorna às cores da música mesmo que a calibração seja interrompida.
  if (fixedColor && Date.now() < fixedUntil) return [...fixedColor];
  // O equilíbrio físico dos canais vale para todas as cores. A referência
  // do álbum já vem calibrada do Python, como nos LEDs do PC.
  // Correção local para bege/âmbar/laranja. O peso é calculado antes do
  // equilíbrio físico: branco, cinza, rosa e cores frias não entram na faixa.
  const [r, g, b] = color;
  const maximum = Math.max(r, g, b);
  const minimum = Math.min(r, g, b);
  const range = maximum - minimum;
  const smooth = value => {
    const t = Math.max(0, Math.min(1, value));
    return t * t * (3 - 2 * t);
  };
  let warmWeight = 0;
  if (range > 0 && r > g && g > b) {
    const hue = (g - b) / range / 6;
    const saturation = range / maximum;
    warmWeight = smooth((hue - 0.015) / 0.025) *
      smooth((0.16 - hue) / 0.045) * smooth((saturation - 0.12) / 0.23);
  }
  const adjusted = color.map((value, i) =>
    value * rgbGains[i] * (1 + (warmGains[i] - 1) * warmWeight));
  // Se um canal ultrapassar 255, reduz todos na mesma proporção para
  // conservar o branco aprovado, inclusive nas capas mais claras.
  const scale = Math.min(1, 255 / Math.max(1, ...adjusted));
  return adjusted.map(value => Math.max(0, Math.min(255, Math.round(value * scale))));
}

function record(message) {
  try {
    const folder = join(__dirname, '..', 'diagnostico_leds');
    mkdirSync(folder, { recursive: true });
    appendFileSync(join(folder, 'lotus.log'), new Date().toISOString() + ' ' + message + '\n');
  } catch {} // indisponibilidade do registro não interrompe o Bluetooth
}
record('Ponte iniciada; endereço=' + process.argv[3]);
const originalLog = console.log.bind(console);
console.log = (...args) => {
  const message = args.join(' ');
  if (message.includes('Connection error:') || message.includes('Characteristic:') ||
      message.includes('Write characteristic assigned:')) record(message);
  originalLog(...args);
};
const seen = new Set();
noble.prependListener('discover', peripheral => {
  // Device compara a propriedade legada uuid em minúsculas. WinRT pode
  // fornecer hexadecimal maiúsculo. id permanece intacto para o transporte.
  peripheral.uuid = peripheral.uuid.replace(/[:-]/g, '').toLowerCase();
  const name = (peripheral.advertisement.localName || '').trim();
  if ((name.startsWith('ELK') || peripheral.uuid === device.uuid) && !seen.has(peripheral.uuid)) {
    seen.add(peripheral.uuid);
    record('Dispositivo encontrado: ' + name + '; endereço=' + peripheral.uuid);
  }
});

function status(value, error = '') {
  const key = `${value}:${error}`;
  if (key === lastStatus) return;
  lastStatus = key;
  record(value + (error ? ': ' + error : ''));
  console.log('@LOTUS@' + JSON.stringify({ status: value, erro: error }));
}

server.on('message', (msg, remote) => {
  if (remote.address !== '127.0.0.1' || msg.length !== 13 ||
      (msg[0] & 0xc0) !== 0x40 || msg[2] !== 1 || msg[3] !== 1 ||
      msg.readUInt32BE(4) !== 0 || msg.readUInt16BE(8) !== 3) return;
  pending = [msg[10], msg[11], msg[12]];
});
server.on('error', (error) => {
  status('Indisponível', error.code === 'EADDRINUSE'
    ? 'Outra ponte já está usando a porta local 4048.' : error.message);
  process.exitCode = 1;
  shutdown();
});
server.on('listening', () => status('Conectando…'));

const timer = setInterval(async () => {
  if (busy || closing) return;
  busy = true;
  try {
    // WinRT inicializa de forma assíncrona. startScanning() lança erro se
    // connect() for chamado enquanto o estado ainda é unknown/poweredOff.
    if (noble.state !== 'poweredOn') {
      ready = false;
      status('Aguardando Bluetooth', noble.state === 'poweredOff'
        ? 'Ligue o Bluetooth do Windows para conectar a fita.' : 'Bluetooth ainda está inicializando.');
      return;
    }
    if (!device.connected) {
      ready = false;
      firstColor = true;
      if (device.connecting) return;
      if (Date.now() < nextConnect) return;
      status('Conectando…');
      nextConnect = Date.now() + 10000;
      // O Windows já conhece o endereço configurado. A fita pode deixar de
      // anunciar durante o pareamento; não exigir um novo anúncio para GATT.
      if (!device.peripheral) {
        noble.stopScanning();
        const id = device.uuid;
        if (!noble._peripherals[id]) {
          const address = id.match(/.{2}/g).join(':');
          noble._peripherals[id] = new Peripheral(noble, id, address, 'public', true, {}, 0);
          noble._services[id] = {};
          noble._characteristics[id] = {};
          noble._descriptors[id] = {};
        }
        device.peripheral = noble._peripherals[id];
        record('Conexão direta ao endereço configurado: ' + id);
      }
      await device.connect(0);
      if (!device.connected) {
        status('Desconectada', 'Fita não encontrada. Confira Bluetooth e feche o Lotus Lantern no celular.');
        return;
      }
    }
    if (!ready) {
      // Liga a fita e remove um brilho previamente reduzido no app do celular;
      // o brilho do Turing Vinyl já está incorporado nos canais RGB enviados.
      await device.set_power(true);
      await new Promise(resolve => setTimeout(resolve, 200));
      if (closing) return;
      await device.set_brightness(100);
      ready = true;
      status('Conectada');
    }
    if (pending) {
      const originalColor = pending;
      const color = calibrate(originalColor);
      pending = null;
      // Usa writeAsync diretamente para conservar rejeições de escrita:
      // set_rgb do Device absorve erros na fila e poderia anunciar sucesso.
      await device.waitForWriteReady();
      if (closing) return;
      await device.writeAsync(Buffer.from([0x7e, 0x07, 0x05, 0x03, ...color, 0x10, 0xef]));
      if (calibrationWritePending) {
        record('Cor enviada após ajuste: origem=' + originalColor.join(',') + '; BLE=' + color.join(','));
        calibrationWritePending = false;
      }
      if (firstColor) {
        record('Primeira cor enviada por BLE: ' + color.join(','));
        firstColor = false;
      }
      device.debounceDisconnect();
      status('Conectada');
    }
  } catch (error) {
    status('Indisponível', 'Falha Bluetooth: ' + error.message);
    ready = false;
  } finally {
    busy = false;
  }
}, 200);

function shutdown() {
  if (closing) return;
  closing = true;
  clearInterval(timer);
  try { server.close(); } catch {}
  try { if (device.peripheral) device.peripheral.disconnect(); } catch {}
  // Mantém a última cor; não apaga a fita ao encerrar a exibição.
  setTimeout(() => process.exit(process.exitCode || 0), 100);
}
process.stdin.resume();
process.stdin.on('end', shutdown);
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
server.bind(4048, '127.0.0.1');
