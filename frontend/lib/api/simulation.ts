/**
 * Simulation transcript API client.
 *
 * Mirrors `characters.ts`: typed POST/GET, zod-validated responses.
 */
import {
  simulationTranscriptSchema,
  transcriptTurnSchema,
  type SimulationContinueRequest,
  type SimulationTranscript,
  type TranscriptTurn,
} from "@/types/story";
import { apiFetch } from "./client";

export async function getSimulationTranscript(
  sessionId: string,
): Promise<SimulationTranscript> {
  const raw = await apiFetch<unknown>(
    `/api/simulation/${encodeURIComponent(sessionId)}/transcript`,
  );
  return simulationTranscriptSchema.parse(raw);
}

export async function continueSimulation(
  req: SimulationContinueRequest,
): Promise<TranscriptTurn> {
  const raw = await apiFetch<unknown>("/api/simulation/continue", {
    method: "POST",
    body: JSON.stringify(req),
  });
  return transcriptTurnSchema.parse(raw);
}
