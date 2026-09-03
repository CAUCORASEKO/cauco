import Accelerate
import Foundation

public struct TemporalWakeFeatureConfiguration: Sendable, Equatable {
  public let sampleRate = 16_000
  public let frameLength = 400
  public let hopLength = 160
  public let fftSize = 512
  public let melBands = 24
  public let mfccCount = 13
  public let regions = 4
  public let maximumSamples = 48_000
  public let normalize = true
  public init() {}
}

public enum TemporalWakeFeatureError: Error { case empty, tooLong, invalidLength }

/// Swift counterpart of wake-model/tools/train_temporal_acoustic.py.
public struct TemporalWakeFeatureExtractor: @unchecked Sendable {
  public let configuration: TemporalWakeFeatureConfiguration
  private let window: [Double]
  private let melBank: [[Double]]
  private let dct: [[Double]]
  private let dftSetup: vDSP_DFT_SetupD

  public init(configuration: TemporalWakeFeatureConfiguration = .init()) {
    self.configuration = configuration
    window = (0..<configuration.frameLength).map { let value = Foundation.sin(.pi * Double($0) / Double(configuration.frameLength - 1)); return value * value }
    let hzToMel: (Double) -> Double = { 2595 * log10(1 + $0 / 700) }
    let melToHz: (Double) -> Double = { 700 * (pow(10, $0 / 2595) - 1) }
    let points = (0..<(configuration.melBands + 2)).map { melToHz(hzToMel(0) + Double($0) * (hzToMel(8000) - hzToMel(0)) / Double(configuration.melBands + 1)) }
    let bins = points.map { Int(floor(Double(configuration.fftSize + 1) * $0 / 16000)) }
    melBank = (0..<configuration.melBands).map { i in
      (0...(configuration.fftSize / 2)).map { j in
        let left = bins[i], center = bins[i + 1], right = bins[i + 2]
        if j >= left && j < center && center > left { return Double(j - left) / Double(center - left) }
        if j >= center && j < right && right > center { return Double(right - j) / Double(right - center) }
        return 0
      }
    }
    dct = (0..<configuration.mfccCount).map { k in
      (0..<configuration.melBands).map { n in
        let scale = k == 0 ? sqrt(1.0 / Double(configuration.melBands)) : sqrt(2.0 / Double(configuration.melBands))
        return scale * cos(.pi * Double(k) * (Double(n) + 0.5) / Double(configuration.melBands))
      }
    }
    guard let setup = vDSP_DFT_zop_CreateSetupD(nil, vDSP_Length(configuration.fftSize), vDSP_DFT_Direction.FORWARD) else { fatalError("Unable to create DFT setup") }
    dftSetup = setup
  }

  public func extract(samples: [Double]) throws -> [Double] {
    guard !samples.isEmpty else { throw TemporalWakeFeatureError.empty }
    guard samples.count <= configuration.maximumSamples else { throw TemporalWakeFeatureError.tooLong }
    var audio = samples
    if audio.count < configuration.frameLength { audio += Array(repeating: 0, count: configuration.frameLength - audio.count) }
    let frameCount = 1 + (audio.count - configuration.frameLength) / configuration.hopLength
    var logMel = Array(repeating: Array(repeating: 0.0, count: configuration.melBands), count: frameCount)
    var mfcc = Array(repeating: Array(repeating: 0.0, count: configuration.mfccCount), count: frameCount)
    for frame in 0..<frameCount {
      let start = frame * configuration.hopLength
      var real = Array(audio[start..<(start + configuration.frameLength)])
      vDSP_vmulD(real, 1, window, 1, &real, 1, vDSP_Length(configuration.frameLength))
      real += Array(repeating: 0, count: configuration.fftSize - configuration.frameLength)
      var power = Array(repeating: 0.0, count: configuration.fftSize / 2 + 1)
      var imaginary = Array(repeating: 0.0, count: configuration.fftSize)
      var outputReal = Array(repeating: 0.0, count: configuration.fftSize)
      var outputImaginary = Array(repeating: 0.0, count: configuration.fftSize)
      vDSP_DFT_ExecuteD(dftSetup, real, imaginary, &outputReal, &outputImaginary)
      for k in 0...configuration.fftSize / 2 { power[k] = (outputReal[k] * outputReal[k] + outputImaginary[k] * outputImaginary[k]) / Double(configuration.fftSize) }
      for b in 0..<configuration.melBands {
        let energy = max(zip(power, melBank[b]).reduce(0.0) { $0 + $1.0 * $1.1 }, 1e-12)
        logMel[frame][b] = log(energy)
      }
      for k in 0..<configuration.mfccCount { mfcc[frame][k] = zip(logMel[frame], dct[k]).reduce(0.0) { $0 + $1.0 * $1.1 } }
    }
    if configuration.normalize {
      for c in 0..<configuration.melBands { let mean = logMel.map { $0[c] }.reduce(0,+) / Double(frameCount); for i in 0..<frameCount { logMel[i][c] -= mean } }
      for c in 0..<configuration.mfccCount { let mean = mfcc.map { $0[c] }.reduce(0,+) / Double(frameCount); for i in 0..<frameCount { mfcc[i][c] -= mean } }
    }
    let delta = derivative(mfcc), delta2 = derivative(derivative(mfcc))
    var result: [Double] = []
    let base = frameCount / configuration.regions, remainder = frameCount % configuration.regions
    var regionStart = 0
    for region in 0..<configuration.regions {
      let count = base + (region < remainder ? 1 : 0)
      let start = regionStart, end = regionStart + count
      regionStart = end
      let indices = start..<max(start + 1, end)
      func mean(_ values: [[Double]], _ c: Int) -> Double { indices.map { values[min($0, frameCount - 1)][c] }.reduce(0,+) / Double(indices.count) }
      func std(_ values: [[Double]], _ c: Int) -> Double { let m = mean(values,c); return sqrt(indices.map { pow(values[min($0, frameCount - 1)][c] - m, 2) }.reduce(0,+) / Double(indices.count)) }
      result += (0..<configuration.melBands).map { mean(logMel,$0) }
      result += (0..<configuration.melBands).map { std(logMel,$0) }
      result += (0..<configuration.mfccCount).map { mean(mfcc,$0) }
      result += (0..<configuration.mfccCount).map { mean(delta,$0) }
      result += (0..<configuration.mfccCount).map { mean(delta2,$0) }
    }
    guard result.count == 348 else { throw TemporalWakeFeatureError.invalidLength }
    return result
  }

  private func derivative(_ values: [[Double]]) -> [[Double]] {
    guard values.count > 1 else { return Array(repeating: Array(repeating: 0, count: values.first?.count ?? 0), count: values.count) }
    return values.indices.map { i in
      let a = values[max(0, i - 1)], b = values[min(values.count - 1, i + 1)]
      return zip(a,b).map { ($0.1 - $0.0) / (i == 0 || i == values.count - 1 ? 1 : 2) }
    }
  }
}
