# SlotSaver — AI-Powered Cancellation Recovery for Service Businesses

SlotSaver helps appointment-based businesses recover revenue from last-minute cancellations.

Instead of relying on static waitlists or manual phone calls, SlotSaver remembers customer scheduling preferences, ranks the best replacement candidates using NVIDIA Nemotron, and contacts them through ElevenLabs voice agents.

If normal demand is not enough, SlotSaver can also trigger business-approved incentive offers while enforcing pricing and policy constraints.

## What SlotSaver does

- Captures customer scheduling preferences from natural voice conversations
- Extracts structured intent from call data
- Detects cancelled appointment slots
- Filters eligible replacement customers
- Uses NVIDIA Nemotron to rank the best candidates
- Automatically progresses through the recovery queue
- Uses ElevenLabs voice agents for outbound customer calls
- Handles declines and timeouts automatically
- Rebooks accepted slots atomically
- Falls back to controlled incentives when demand is low
- Updates the business calendar in real time

## Core idea

> Existing waitlists store availability.  
> SlotSaver remembers scheduling intent — and acts on it.

## Architecture

### Voice Layer — ElevenLabs

ElevenLabs handles natural conversations with customers.

During a call, SlotSaver captures preferences such as:

- preferred days
- preferred times
- preferred providers
- scheduling flexibility
- willingness to move an appointment
- whether the customer wants to be contacted when an opening appears

The voice layer can later call the customer back when a matching slot becomes available.

### Decision Layer — NVIDIA Nemotron

Nemotron acts as the decision engine behind SlotSaver.

It is used to:

- interpret scheduling intent
- rank eligible customers for an open slot
- explain candidate ranking decisions
- determine whether incentive fallback should be used
- select incentives within business-defined constraints

Nemotron does not directly perform bookings. Deterministic backend logic validates and executes its decisions.

### Recovery Engine

When a cancellation occurs:

1. The appointment slot becomes available.
2. SlotSaver filters customers who cannot take the slot.
3. Nemotron ranks the remaining candidates.
4. The highest-ranked customer is contacted.
5. If they decline or time out, SlotSaver automatically moves to the next candidate.
6. If they accept, the appointment is atomically rebooked.
7. If the recovery queue is exhausted, SlotSaver can evaluate an incentive fallback.
8. Approved incentives are offered through the same voice workflow.

## Incentive Safety

Businesses remain in control of pricing.

The business can define:

- allowed incentive types
- maximum discount
- minimum revenue floor
- excluded services
- eligible time windows

Nemotron chooses from the allowed options, while the backend independently validates every decision before an offer is made.

## Stack

### Frontend
- Next.js
- TypeScript
- Tailwind CSS

Location:

```text
apps/web



## Demo

## Demo

🚀 [Try the deployed app](https://slotsaver-smoky.vercel.app)

🎥 [Watch the demo video](docs/demo/slotsaver-demo.mp4)