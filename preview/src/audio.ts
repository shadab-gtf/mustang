import { clamp } from "./physics.ts"

export class VehicleAudio {
  private readonly context = new AudioContext()
  private readonly engine = this.context.createOscillator()
  private readonly exhaust = this.context.createBiquadFilter()
  private readonly engineVolume = this.context.createGain()
  private readonly tireVolume = this.context.createGain()

  constructor() {
    const harmonics = new Float32Array([0, 1, 0.37, 0.72, 0.26, 0.41, 0.22, 0.15, 0.07])
    this.engine.setPeriodicWave(this.context.createPeriodicWave(new Float32Array(harmonics.length), harmonics))
    this.exhaust.type = "lowpass"
    this.engineVolume.gain.value = 0
    this.tireVolume.gain.value = 0
    this.engine.connect(this.exhaust).connect(this.engineVolume).connect(this.context.destination)
    const texture = this.context.createBuffer(1, this.context.sampleRate, this.context.sampleRate)
    const samples = texture.getChannelData(0)
    for (let i = 0; i < samples.length; i++) samples[i] = Math.random() * 2 - 1
    const noise = this.context.createBufferSource()
    noise.buffer = texture
    noise.loop = true
    const squeal = this.context.createBiquadFilter()
    squeal.type = "bandpass"
    squeal.frequency.value = 2580
    squeal.Q.value = 3.5
    noise.connect(squeal).connect(this.tireVolume).connect(this.context.destination)
    this.engine.start()
    noise.start()
  }

  setEnabled(enabled: boolean) {
    return enabled ? this.context.resume() : this.context.suspend()
  }

  update(rpm: number, throttle: number, slip: number) {
    const now = this.context.currentTime
    this.engine.frequency.setTargetAtTime(rpm / 15, now, 0.05)
    this.exhaust.frequency.setTargetAtTime(310 + throttle * 850 + rpm * 0.09, now, 0.07)
    this.engineVolume.gain.setTargetAtTime(0.05 + throttle * 0.095, now, 0.07)
    this.tireVolume.gain.setTargetAtTime(clamp((slip - 0.24) * 0.24, 0, 0.15), now, 0.04)
  }
}
