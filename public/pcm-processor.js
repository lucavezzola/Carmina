// AudioWorkletProcessor: converts microphone audio (float32 at the browser's
// native sample rate, often 44.1/48 kHz) into mono PCM Int16 at 16 kHz,
// which is the format expected by Vosk in AcceptWaveform().

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
    this.voiceActive = false;
    // Keep recognition latency short; the server receives the final fragment
    // through flushBuffer() when the voice hangover expires.
    this.buffer = new Float32Array(1024);
    this.bufferLength = 0;
  }

  flushBuffer() {
    if (this.bufferLength === 0) return false;
    const int16 = new Int16Array(this.bufferLength);
    for (let sampleIndex = 0; sampleIndex < this.bufferLength; sampleIndex++) {
      const value = Math.max(-1, Math.min(1, this.buffer[sampleIndex]));
      int16[sampleIndex] = value < 0 ? value * 0x8000 : value * 0x7fff;
    }
    this.port.postMessage(int16.buffer, [int16.buffer]);
    this.bufferLength = 0;
    return true;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channelData = input[0]; // Mono: use the first channel only.

    let sumSquares = 0;
    for (let i = 0; i < channelData.length; i++) {
      sumSquares += channelData[i] * channelData[i];
    }
    const rms = Math.sqrt(sumSquares / channelData.length);
    if (rms >= this.voiceThreshold) {
      this.remainingHangoverSamples = this.hangoverSamples;
      this.voiceActive = true;
    }

    // Downsampling with the nearest-neighbour method: take one sample every
    // `ratio` steps. This is enough for keyword spotting and keeps the
    // processing lightweight for this use case.
    for (let i = 0; i < channelData.length; i += this.ratio) {
      const idx = Math.floor(i);
      if (idx >= channelData.length) break;
      const sample = channelData[idx];
      if (this.remainingHangoverSamples <= 0) continue;
      this.buffer[this.bufferLength++] = sample;
      this.remainingHangoverSamples--;

      if (this.bufferLength >= this.buffer.length) this.flushBuffer();
    }

    // Send the final voice fragment as soon as the hangover expires. This
    // never adds silence, but prevents it waiting for the next utterance.
    if (this.remainingHangoverSamples <= 0 && this.voiceActive) {
      this.flushBuffer();
      this.voiceActive = false;
      // This is a control event, not silent audio. It lets the server start
      // a fresh phrase without padding the recognizer with silence.
      this.port.postMessage({ type: "voice_end" });
    }

    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);