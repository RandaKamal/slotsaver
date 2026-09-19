import { VoiceAgent } from "@/components/calls/VoiceAgent";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-neutral-50 px-4">
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-neutral-900">SlotSaver</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Talk to us about booking, rescheduling, or your scheduling
          preferences.
        </p>
      </div>
      <VoiceAgent />
    </main>
  );
}
