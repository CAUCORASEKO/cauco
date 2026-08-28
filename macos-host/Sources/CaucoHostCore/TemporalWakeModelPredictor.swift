import CoreML
import Foundation

public enum TemporalWakeModelError: Error { case invalidInput, invalidModel, predictionFailed }

public struct TemporalWakePrediction: Sendable, Equatable {
  public let probability: Double
  public let label: String
}

public final class TemporalWakeModelPredictor: @unchecked Sendable {
  private let model: MLModel
  public init(model: MLModel) throws {
    let inputs = model.modelDescription.inputDescriptionsByName
    guard let input = inputs["temporal_features"], input.type == .multiArray,
          input.multiArrayConstraint?.shape == [348] else { throw TemporalWakeModelError.invalidModel }
    let outputs = model.modelDescription.outputDescriptionsByName
    guard let probabilities = outputs["classProbability"], probabilities.type == .dictionary,
          outputs["classLabel"]?.type == .string else { throw TemporalWakeModelError.invalidModel }
    self.model = model
  }
  public func predict(features: [Double]) throws -> TemporalWakePrediction {
    guard features.count == 348 else { throw TemporalWakeModelError.invalidInput }
    guard let array = try? MLMultiArray(shape: [348], dataType: .double) else { throw TemporalWakeModelError.invalidInput }
    for i in 0..<348 { array[i] = NSNumber(value: features[i]) }
    let provider = try MLDictionaryFeatureProvider(dictionary: ["temporal_features": MLFeatureValue(multiArray: array)])
    guard let result = try? model.prediction(from: provider),
          let distribution = result.featureValue(for: "classProbability")?.dictionaryValue,
          let raw = distribution[NSString(string: "hola_cauco")] ?? distribution["hola_cauco"],
          let value = (raw as? NSNumber)?.doubleValue, value.isFinite, (0...1).contains(value) else {
      throw TemporalWakeModelError.predictionFailed
    }
    let label = result.featureValue(for: "classLabel")?.stringValue ?? ""
    return TemporalWakePrediction(probability: value, label: label)
  }
}

public struct BoundedMonoAudioBuffer: Sendable {
  public let capacity: Int
  private(set) public var samples: [Double] = []
  public init(capacity: Int = 48_000) { self.capacity = capacity }
  public mutating func append(_ values: [Double]) {
    samples.append(contentsOf: values)
    if samples.count > capacity { samples.removeFirst(samples.count - capacity) }
  }
  public mutating func reset() { samples.removeAll(keepingCapacity: true) }
}
