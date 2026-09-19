"use client";

import { useState } from "react";
import {
  ConversationProvider,
  useConversation,
  type ConversationStatus,
} from "@elevenlabs/react";

const AGENT_ID = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID;
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type VoiceState = "disconnected" | "connecting" | "listening" | "speaking" | "error";

function deriveVoiceState(
  status: ConversationStatus,
  mode: "speaking" | "listening"
): VoiceState {
  if (status === "connected") {
    return mode === "speaking" ? "speaking" : "listening";
  }
  return status;
}

const STATE_LABEL: Record<VoiceState, string> = {
  disconnected: "Not connected",
  connecting: "Connecting…",
  listening: "Listening…",
  speaking: "Speaking…",
  error: "Something went wrong",
};

const STATE_DOT: Record<VoiceState, string> = {
  disconnected: "bg-neutral-400",
  connecting: "bg-amber-500 animate-pulse",
  listening: "bg-teal-500 animate-pulse",
  speaking: "bg-blue-500 animate-pulse",
  error: "bg-red-500",
};

function TalkPanel() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // Temporary test-only control: there's no login/session system yet, so
  // this stands in for "who is calling" until that exists. Not production UI.
  const [patientId, setPatientId] = useState("test-patient-1");

  const conversation = useConversation({
    onConnect: () => setErrorMessage(null),
    onError: (message) => setErrorMessage(message),
    onDisconnect: () => setErrorMessage(null),
    clientTools: {
      // Called by the ElevenLabs agent's "save_scheduling_intent" tool.
      // Forwards straight to our backend; no extraction happens here.
      save_scheduling_intent: async (parameters: {
        patient_id?: string;
        raw_text?: string;
      }) => {
        try {
          const res = await fetch(`${API_URL}/api/voice/preferences`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              patient_id: parameters.patient_id,
              raw_text: parameters.raw_text,
            }),
          });
          if (!res.ok) {
            console.error("save_scheduling_intent failed", res.status, await res.text());
            return "I had trouble saving that just now.";
          }
          return "Saved your scheduling preferences.";
        } catch (err) {
          console.error("save_scheduling_intent error", err);
          return "I had trouble saving that just now.";
        }
      },
    },
  });

  // errorMessage can be set before the SDK's own status ever leaves
  // "disconnected" (e.g. a missing agent ID caught before startSession is
  // even called), so it takes priority over the raw hook status here.
  const voiceState: VoiceState = errorMessage
    ? "error"
    : deriveVoiceState(conversation.status, conversation.mode);
  const isActive =
    conversation.status === "connecting" || conversation.status === "connected";

  // Requesting the mic only happens here, inside startSession(), which only
  // runs once the visitor presses the button below — never on page load.
  const handleStart = () => {
    setErrorMessage(null);
    if (!AGENT_ID) {
      setErrorMessage(
        "Missing NEXT_PUBLIC_ELEVENLABS_AGENT_ID — check your .env file."
      );
      return;
    }
    conversation.startSession({
      agentId: AGENT_ID,
      dynamicVariables: { patient_id: patientId },
    });
  };

  const handleEnd = () => {
    conversation.endSession();
  };

  return (
    <div className="flex w-full max-w-sm flex-col items-center gap-4 rounded-2xl border border-neutral-200 bg-white p-8 shadow-sm">
      <div className="flex items-center gap-2 text-sm font-medium text-neutral-600">
        <span className={`h-2.5 w-2.5 rounded-full ${STATE_DOT[voiceState]}`} />
        {STATE_LABEL[voiceState]}
      </div>

      {voiceState === "error" && errorMessage && (
        <p className="text-center text-sm text-red-600">{errorMessage}</p>
      )}

      {/* Temporary test-only control — stands in for a real session/login
          until that exists. Not production UI. */}
      {!isActive && (
        <label className="flex w-full flex-col gap-1 text-xs text-neutral-500">
          Test patient ID
          <input
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            className="rounded-md border border-neutral-300 px-2 py-1.5 text-sm text-neutral-900"
          />
        </label>
      )}

      {!isActive ? (
        <button
          onClick={handleStart}
          className="rounded-full bg-neutral-900 px-6 py-3 text-sm font-semibold text-white transition hover:bg-neutral-700"
        >
          Talk to SlotSaver
        </button>
      ) : (
        <button
          onClick={handleEnd}
          className="rounded-full border border-neutral-300 px-6 py-3 text-sm font-semibold text-neutral-700 transition hover:bg-neutral-100"
        >
          End conversation
        </button>
      )}

      <p className="text-center text-xs text-neutral-400">
        Microphone access is requested only after you press &ldquo;Talk to
        SlotSaver&rdquo;.
      </p>
    </div>
  );
}

export function VoiceAgent() {
  return (
    <ConversationProvider>
      <TalkPanel />
    </ConversationProvider>
  );
}
