// Descoberta e endereço persistido só para a fita; executa no processo BLE.
const { join, resolve, dirname } = require('node:path');
const { mkdirSync, readFileSync, writeFileSync, renameSync } = require('node:fs');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const runFile = promisify(execFile);

const addressOf = value => String(value || '').replace(/[:-]/g, '').toLowerCase();
const validAddress = value => /^[0-9a-f]{12}$/.test(value);
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

class LotusDevices {
  constructor(noble, device, Peripheral, folder, configured, publish, record) {
    Object.assign(this, { noble, device, Peripheral, publish, record });
    this.folder = resolve(folder).toLowerCase();
    this.file = join(process.env.LOCALAPPDATA || process.env.USERPROFILE || folder,
      'TuringScreen', 'lotus-dispositivos.json');
    this.configured = addressOf(configured);
    this.entries = {};
    try {
      const entries = JSON.parse(readFileSync(this.file, 'utf8'));
      if (entries && typeof entries === 'object' && !Array.isArray(entries)) this.entries = entries;
    } catch {}
    const saved = this.entries[this.folder];
    this.address = saved && saved.configured === this.configured && validAddress(saved.address)
      ? saved.address : this.configured;
    this.name = (saved && saved.configured === this.configured && saved.name) || 'ELK-BLEDDM';
    this.device.uuid = this.address || 'discovery';
    this.scanFirst = !!(saved && saved.configured === this.configured && saved.rediscover);
    this.candidates = [];
    this.selection = null;
    this.closed = false;
  }

  info() {
    return { endereco: this.address, nome: this.name,
      candidatos: this.candidates.map(({ address, name }) => ({ endereco: address, nome: name })) };
  }

  select(address) {
    const id = addressOf(address);
    if (validAddress(id) && id !== this.address) this.selection = id;
  }

  peripheral(id) {
    const n = this.noble;
    if (!n._peripherals[id]) {
      n._peripherals[id] = new this.Peripheral(n, id, id.match(/.{2}/g).join(':'), 'public', true, {}, 0);
      n._services[id] = {};
      n._characteristics[id] = {};
      n._descriptors[id] = {};
    }
    return n._peripherals[id];
  }

  async attempt(id, peripheral) {
    if (this.closed || !validAddress(id)) return false;
    this.noble.stopScanning();
    this.device.uuid = id;
    this.device.peripheral = peripheral || this.peripheral(id);
    this.device.connected = this.device.connecting = false;
    let timer;
    try {
      // Uma chamada nativa que não responda encerra a ponte; o motor pode
      // reiniciá-la sem bloquear a interface nem a transmissão da tela.
      await Promise.race([
        this.device.connect(0),
        new Promise((_, reject) => {
          timer = setTimeout(() => {
            const error = new Error('Tempo de conexão Bluetooth esgotado');
            error.code = 'BLE_TIMEOUT';
            reject(error);
          }, 14000);
        }),
      ]);
      if (this.closed) return false;
      return this.device.connected && !!this.device.write;
    } catch (error) {
      if (error.code === 'BLE_TIMEOUT') this.rediscover();
      throw error;
    } finally { clearTimeout(timer); }
  }

  remember(id, name) {
    this.address = id;
    this.name = name || this.name || 'ELK-BLEDDM';
    this.candidates = [];
    this.scanFirst = false;
    this.entries[this.folder] = { configured: this.configured, address: id, name: this.name };
    this.save();
    this.publish('Conectada');
  }

  save() {
    try {
      mkdirSync(dirname(this.file), { recursive: true });
      const temporary = this.file + '.tmp';
      writeFileSync(temporary, JSON.stringify(this.entries, null, 2), 'utf8');
      renameSync(temporary, this.file);
    } catch (error) { this.record('Endereço em memória; não foi possível salvar: ' + error.message); }
  }

  rediscover() {
    this.scanFirst = true;
    this.entries[this.folder] = { configured: this.configured, address: this.address,
      name: this.name, rediscover: true };
    this.save();
  }

  async windowsDevices() {
    const command = '[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); ' +
      'Get-PnpDevice -Class Bluetooth -PresentOnly -ErrorAction SilentlyContinue | ' +
      'Where-Object { $_.FriendlyName -like "ELK*" -and $_.InstanceId -like "BTHLE\\DEV_*" } | ' +
      'Select-Object FriendlyName,InstanceId | ConvertTo-Json -Compress';
    try {
      const { stdout } = await runFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', command],
        { windowsHide: true, timeout: 6000, maxBuffer: 65536, encoding: 'utf8' });
      const data = JSON.parse(stdout.replace(/^\uFEFF/, '').trim() || '[]');
      return (Array.isArray(data) ? data : [data]).filter(Boolean).map(entry => ({
        address: addressOf((entry.InstanceId.match(/DEV_([0-9a-f]{12})/i) || [])[1]),
        name: entry.FriendlyName,
      })).filter(entry => validAddress(entry.address));
    } catch { return []; }
  }

  async discover() {
    const found = new Map();
    // Suspende a conexão automática do Device enquanto escolhemos um alvo.
    this.device.uuid = 'discovery';
    const listener = peripheral => {
      const id = addressOf(peripheral.uuid);
      const name = (peripheral.advertisement.localName || '').trim();
      if (validAddress(id) && /^ELK/i.test(name)) found.set(id, { address: id, name, peripheral });
    };
    this.noble.on('discover', listener);
    try {
      this.noble.startScanning([], true);
      const windows = this.windowsDevices();
      await wait(5000);
      for (const entry of await windows) {
        if (!found.has(entry.address)) found.set(entry.address, entry);
      }
    } finally {
      this.noble.removeListener('discover', listener);
      this.noble.stopScanning();
      this.device.uuid = this.address || 'discovery';
    }
    return [...found.values()].filter(entry =>
      entry.address !== this.address && entry.name.toUpperCase() === String(this.name).toUpperCase()).slice(0, 8);
  }

  async connect() {
    if (this.closed) return false;
    if (this.selection) {
      const chosen = this.selection;
      this.selection = null;
      if (await this.attempt(chosen)) {
        this.remember(chosen, this.candidates.find(c => c.address === chosen)?.name);
        return true;
      }
      this.rediscover();
    }
    if (!this.scanFirst && validAddress(this.address) && await this.attempt(this.address)) {
      this.remember(this.address, this.device.peripheral?.advertisement?.localName);
      return true;
    }
    this.rediscover();
    this.publish('Procurando fita…');
    this.candidates = await this.discover();
    if (this.closed) return false;
    if (this.candidates.length > 1) {
      this.publish('Escolha a fita', 'Há mais de uma fita compatível. Escolha no painel Fita RGB.');
      return false;
    }
    const candidate = this.candidates[0];
    if (candidate && await this.attempt(candidate.address, candidate.peripheral)) {
      this.record('Novo endereço validado por FFF3: ' + candidate.address);
      this.remember(candidate.address, candidate.name);
      return true;
    }
    // Se nada mudou, tenta também o endereço conhecido após a busca.
    if (!candidate && validAddress(this.address) && await this.attempt(this.address)) {
      this.remember(this.address, this.device.peripheral?.advertisement?.localName);
      return true;
    }
    this.publish('Desconectada', 'Fita não encontrada. Confira Bluetooth, alimentação e feche o app do celular.');
    return false;
  }

  invalidate() {
    try { this.device.peripheral?.disconnect(); } catch {}
    this.device._resetState();
    if (!this.closed) this.rediscover();
  }

  close() {
    this.closed = true;
    this.invalidate();
  }
}

module.exports = { LotusDevices };
