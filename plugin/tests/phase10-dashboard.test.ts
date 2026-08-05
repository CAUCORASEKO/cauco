import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parseCognitiveCycle, parseLearningGuidance, parseMemoryCandidates, parseReflection } from "../src/cognitive/api";

const cycle = { review_id: "review-1", current_stage: "awaiting_memory_candidate_review", overall_cycle_status: "awaiting_human_action", blocked: false, terminal: false, awaiting_human_action: true, next_permitted_action: "review_memory_candidate", safe_endpoint: "/api/memory-candidates", related_record_ids: { candidate_ids: ["candidate-1"] }, candidate_counts: { pending_review: 1 }, proposal_counts: { pending: 0 }, warnings: [], limitations: ["bounded"], method: "test" };
const guidance = { guidance: [{ candidate_id: "candidate-1", experience_id: "experience-1", proposal_id: "proposal-1", category: "execution", lesson: "Prefer small steps.", confidence: 0.8, reason_selected: "Exact tool/operation match.", tool_id: "git", operation_id: "status", step_index: 1 }] };
const reflection = { summary: { approved_candidates: 2, applied_learning_proposals: 1, planning: 1, execution: 0, verification: 0 }, patterns: [{ category: "planning", lesson: "Prefer small steps.", count: 1 }], method: "test", limitations: [] };
const candidate = { candidate_id: "candidate-1", experience_id: "experience-1", verification_id: "verification-1", execution_id: "execution-1", review_id: "review-1", lesson: { category: "execution", observation: "Observed", lesson: "Prefer small steps.", confidence: 0.8 }, target: "learning", status: "approved", disposition: "promote_to_memory", rationale: "Reusable" };

test("parses cognitive dashboard response families", () => {
  assert.equal(parseCognitiveCycle(cycle).currentStage, "awaiting_memory_candidate_review");
  assert.equal(parseLearningGuidance(guidance)[0].proposalId, "proposal-1");
  assert.equal(parseReflection(reflection).patterns[0].count, 1);
  assert.equal(parseMemoryCandidates({ candidates: [candidate] })[0].status, "approved");
});

test("rejects malformed dashboard data", () => {
  assert.throws(() => parseCognitiveCycle({ ...cycle, blocked: "no" }));
  assert.throws(() => parseLearningGuidance({ guidance: [{ ...guidance.guidance[0], confidence: "high" }] }));
  assert.throws(() => parseReflection({ ...reflection, patterns: [{ category: "x" }] }));
  assert.throws(() => parseMemoryCandidates({ candidates: [{ ...candidate, status: "unknown" }] }));
});

test("dashboard source keeps cognitive observation read-only", () => {
  const source = readFileSync("src/views/CaucoDashboardView.ts", "utf8");
  assert.match(source, /getCognitiveCycle/);
  assert.doesNotMatch(source, /requestUrl\(\{\s*url:.*input/);
  assert.match(source, /getCognitiveCycle/);
});
