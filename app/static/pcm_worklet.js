class PCMForwarder extends AudioWorkletProcessor {
  // Local EOF barrier; sample forwarding below matches WLK 0.2.26.
  constructor() {
    super();
    this.port.onmessage = () => {
      this.stopped = true;
      this.port.postMessage({flushed: true});
    };
  }
  process(inputs) {
    if (this.stopped) return true;
    const input = inputs[0];
    if (input && input[0] && input[0].length) {
      // Forward mono channel (0). If multi-channel, downmixing can be added here.
      const channelData = input[0];
      const copy = new Float32Array(channelData.length);
      copy.set(channelData);
      this.port.postMessage(copy, [copy.buffer]);
    }
    // Keep processor alive
    return true;
  }
}

registerProcessor('pcm-forwarder', PCMForwarder);
