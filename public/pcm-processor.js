// AudioWorkletProcessor: converte l'audio del microfono (float32, al sample
// rate nativo del browser, spesso 44.1/48kHz) in PCM Int16 mono a 16kHz,
// il formato che Vosk si aspetta in AcceptWaveform().

class PCMProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = options.processorOptions || {};
    this.inputSampleRate = opts.inputSampleRate || 16000;
    this.targetSampleRate = opts.targetSampleRate || 16000;
    this.ratio = this.inputSampleRate / this.targetSampleRate;
    this.buffer = [];
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channelData = input[0]; // Mono: il primo canale

    // Downsampling "nearest neighbour": prende un campione ogni `ratio`.
    // Sufficiente per keyword spotting; niente filtro anti-aliasing,
    // non necessario per questo caso d'uso.
    for (let i = 0; i < channelData.length; i += this.ratio) {
      const idx = Math.floor(i);
      if (idx < channelData.length) this.buffer.push(channelData[idx]);
    }

    // Invia a blocchi (~4096 campioni a 16kHz, ~0.25s) per non
    // sovraccaricare il canale di messaggi verso il main thread.
    if (this.buffer.length >= 4096) {
      const chunk = this.buffer.splice(0, this.buffer.length);
      const int16 = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }

    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);