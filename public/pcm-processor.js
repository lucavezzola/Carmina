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
    this.voiceThreshold = opts.voiceThreshold || 0.01;
    this.hangoverSamples = Math.floor(this.targetSampleRate * (opts.hangoverMs || 300) / 1000);
    this.remainingHangoverSamples = 0;
    this.buffer = new Float32Array(4096);
    this.bufferLength = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channelData = input[0]; // Mono: il primo canale

    let sumSquares = 0;
    for (let i = 0; i < channelData.length; i++) {
      sumSquares += channelData[i] * channelData[i];
    }
    const rms = Math.sqrt(sumSquares / channelData.length);
    if (rms >= this.voiceThreshold) {
      this.remainingHangoverSamples = this.hangoverSamples;
    }

    // Downsampling "nearest neighbour": prende un campione ogni `ratio`.
    // Sufficiente per keyword spotting; niente filtro anti-aliasing,
    // non necessario per questo caso d'uso.
    for (let i = 0; i < channelData.length; i += this.ratio) {
      const idx = Math.floor(i);
      if (idx >= channelData.length) break;
      const sample = channelData[idx];
      if (this.remainingHangoverSamples <= 0) continue;
      this.buffer[this.bufferLength++] = sample;
      this.remainingHangoverSamples--;

      if (this.bufferLength < this.buffer.length) continue;
      const int16 = new Int16Array(this.bufferLength);
      for (let sampleIndex = 0; sampleIndex < this.bufferLength; sampleIndex++) {
        const value = Math.max(-1, Math.min(1, this.buffer[sampleIndex]));
        int16[sampleIndex] = value < 0 ? value * 0x8000 : value * 0x7fff;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
      this.bufferLength = 0;
    }

    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);