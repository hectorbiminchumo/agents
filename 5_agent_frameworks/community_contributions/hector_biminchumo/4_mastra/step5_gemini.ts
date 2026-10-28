/**
 * Step 5 on Gemini: the same worker as step5.ts, with the model swapped.
 *
 * Only the model line changes. We build an OpenAI provider whose baseURL points at
 * Gemini's OpenAI-compatible endpoint and use provider.chat(...), which forces the
 * Chat Completions API. (provider("model") would use the Responses API, which Gemini
 * does not offer.) Gemini 3 models fail on tool calls this way (missing
 * thought_signature), so we use a 2.5 model. Needs GOOGLE_API_KEY in the repo-root .env.
 * Writes madrid_gemini.txt so the OpenAI run's madrid.txt stays for comparison.
 *
 * Original step 5 header:
 *
 * Now the payoff. Give one agent all three board tools and the filesystem server,
 * hand it the goal, and let it run. It plans its own steps on the board, works them
 * with its file tools, ticks each one off, and closes the goal when the work is
 * done. That is the agent loop running on its own: read, plan, act, check off,
 * repeat. Run it with: npm run step5
 *
 * The terminal worker that Day 5 launches is worker.ts next to this file: the same
 * agent, plus the bits the project needs (claim one task on a shared board, switch
 * model via WORKER_MODEL, print each tool call).
 */

import "./env.ts";
import { join } from "node:path";
import { mkdirSync, rmSync, existsSync, readFileSync } from "node:fs";
import { Agent } from "@mastra/core/agent";
import { createOpenAI } from "@ai-sdk/openai";
import { boardTools, makeFilesystem, WORKSPACE } from "./tools.ts";
import { resetBoard, addGoal, claimTodo, showBoard } from "./board.ts";

const GOAL = "Write a short haiku about Madrid into madrid_gemini.txt.";

const INSTRUCTIONS = `
You are a careful worker with a shared todo board and a set of file tools.

Take the pending goal and see it through. Begin by laying out a short plan: the handful of concrete steps the work itself breaks down into, added to the board under the goal. Then carry them out with your file tools, marking each step done as you finish it. Once the steps are all done, close the goal. Your files live in the single folder your tools are allowed to use.
`;

// Seed the board with the one goal and clear any old output.
mkdirSync(WORKSPACE, { recursive: true });
rmSync(join(WORKSPACE, "madrid_gemini.txt"), { force: true });
resetBoard();
const goalId = addGoal(GOAL);
claimTodo(goalId); // the worker picks up the goal: pending -> in_progress
console.log(`Seeded goal ${goalId}: ${GOAL}\n`);


// The model swap: same agent, a different endpoint behind the provider.
const provider = createOpenAI({
  baseURL: "https://generativelanguage.googleapis.com/v1beta/openai/",
  apiKey: process.env.GOOGLE_API_KEY,
});

const filesystem = makeFilesystem();
const worker = new Agent({
  id: "worker",
  name: "Worker",
  instructions: INSTRUCTIONS,
  model: provider.chat("gemini-2.5-flash-lite"),
  tools: { ...boardTools, ...(await filesystem.listTools()) },
});

await worker.generate("Please work the pending goal on the board.", { maxSteps: 25 });
await filesystem.disconnect();

console.log("\nBoard after the run:");
showBoard();
const haiku = join(WORKSPACE, "madrid_gemini.txt");
if (existsSync(haiku)) {
  console.log("\nmadrid_gemini.txt:\n" + readFileSync(haiku, "utf-8"));
}

process.exit(0); // Mastra keeps its model connection pool open, so exit once the work is done
