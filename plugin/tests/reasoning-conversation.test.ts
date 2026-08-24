import assert from "node:assert/strict";
import test from "node:test";
import { ReasoningPlanningApiClient, ReasoningPlanningApiError } from "../src/reasoning/api";
import { ConversationHistory, responseView } from "../src/reasoning/conversation";
import { parseReasoningPlanningResponse } from "../src/reasoning/contracts";

function response(overrides: Record<string, unknown> = {}) {
  return {
    reasoning_requested: false,
    reasoning_invoked: false,
    proposal_produced: false,
    proposal_validated: false,
    planning_context_enriched: false,
    provider: null,
    model: null,
    explanation: "Reasoning was not requested.",
    planning: {
      status: "planned",
      routing: {
        selected_agent: { id: "project", name: "Project Agent" },
        match: {
          agent_id: "project",
          matched: true,
          score: 55,
          matched_signals: ["project"],
          reasoning: ["Matched project planning."],
          priority: 20,
        },
        matches: [],
        preferred_agent_rejected: false,
      },
      context: null,
      plan: {
        agent_id: "project",
        agent_name: "Project Agent",
        status: "proposal_only",
        objective: "Plan the project",
        context_used: false,
        steps: [
          {
            order: 1,
            title: "Inspect scope",
            description: "Review the requested scope.",
            source_memory_ids: [],
            proposed_action: "Inspect only.",
            requires_confirmation: false,
            execution_available: false,
            warnings: [],
            tool_reference: { tool_id: "project", operation_id: "plan", target: null },
            operation_input: null,
          },
        ],
        open_questions: [],
        warnings: ["No action was executed."],
        requires_confirmation: true,
        execution_performed: false,
        metadata: {},
      },
      proposal_only: true,
      execution_performed: false,
      review_approved: false,
      runtime_started: false,
    },
    ...overrides,
  };
}

test("reasoning request defaults use_reasoning to false and never sends allow_execution", async () => {
  const calls: Array<[string, Readonly<Record<string, unknown>>, number]> = [];
  const client = new ReasoningPlanningApiClient("http://localhost:8765", async (...call) => {
    calls.push(call);
    return response();
  });

  await client.plan({ instruction: "Plan this safely" });

  assert.equal(calls[0]?.[0], "/api/reasoning/plan");
  assert.deepEqual(calls[0]?.[1], {
    instruction: "Plan this safely",
    use_reasoning: false,
  });
  assert.equal("allow_execution" in (calls[0]?.[1] ?? {}), false);
});

test("reasoning toggle sends use_reasoning true without execution controls", async () => {
  let body: Readonly<Record<string, unknown>> = {};
  const client = new ReasoningPlanningApiClient("http://localhost", async (_path, value) => {
    body = value;
    return response({ reasoning_requested: true, reasoning_invoked: true });
  });

  await client.plan({ instruction: "Analyze options", useReasoning: true });

  assert.equal(body.use_reasoning, true);
  assert.equal("allow_execution" in body, false);
});

test("response view exposes selected agent, planning status, and safety flags", () => {
  const view = responseView(parseReasoningPlanningResponse(response()));

  assert.equal(view.planningStatus, "planned");
  assert.equal(view.selectedAgent, "Project Agent (project)");
  assert.match(view.routingMatch, /matched · score 55/);
  assert.deepEqual(view.safety, [
    ["proposal_only", true],
    ["execution_performed", false],
    ["review_approved", false],
    ["runtime_started", false],
  ]);
});

test("provider failures become safe messages without leaking provider secrets", async () => {
  const secret = "sk-provider-secret-at-/Users/private/model";
  const client = new ReasoningPlanningApiClient("http://localhost", async () => {
    throw new Error(secret);
  });

  await assert.rejects(
    client.plan({ instruction: "Plan", useReasoning: true }),
    (error: unknown) => {
      assert.ok(error instanceof ReasoningPlanningApiError);
      assert.equal(error.message, "Advisory planning is unavailable. No action was taken.");
      assert.equal(error.message.includes(secret), false);
      return true;
    },
  );
});

test("conversation history retains previous entries for the panel session", () => {
  const history = new ConversationHistory();
  const first = parseReasoningPlanningResponse(response());
  const second = parseReasoningPlanningResponse(
    response({ reasoning_requested: true, reasoning_invoked: true }),
  );

  history.add({ instruction: "First", useReasoning: false, response: first });
  history.add({ instruction: "Second", useReasoning: true, response: second });

  assert.deepEqual(
    history.entries().map((entry) => entry.instruction),
    ["First", "Second"],
  );
  assert.equal(history.entries()[1]?.useReasoning, true);
});

test("conversation panel source contains only the advisory planning client", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile("src/views/CaucoConversationPanel.ts", "utf8");

  assert.match(source, /ReasoningPlanningApiClient/);
  for (const forbidden of [
    "ExecutionService",
    "MutationService",
    "createExecution",
    "approvePlanReview",
    "confirmMutation",
    "executeStep",
    "allow_execution",
  ]) {
    assert.equal(source.includes(forbidden), false);
  }
});
