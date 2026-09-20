# SlotSaver bunny asset

Export the bunny from the approved mascot artwork as `slotsaver-bunny.png` in this directory, preferably with a transparent background and at least 560 × 560 pixels. Keep the full character inside the image with some breathing room.

The dashboard detects this asset during rendering and passes it to `MascotCard`. Until it is available, the card shows a wordmark placeholder. Restart the development server or rebuild the production application after adding the asset.

## Scout interaction states

`components/mascot/ScoutMascot.tsx` is a controlled, presentational component:

```tsx
<ScoutMascot state="thinking" />
<ScoutMascot state="celebrating" message="An earlier visit, confirmed!" />
<ScoutMascot state="happy" stateImages={{ happy: "/mascots/scout-happy.png" }} />
```

States: `idle` (gentle breathing), `thinking` (tilt and dots), `happy` (greeting), `listening` (soft halo), and `celebrating` (hop and blue accents). Motion is finite and disabled by `prefers-reduced-motion`. The message remains available without animation. State changes are announced politely; avoid rapidly changing messages.

Pass `src` for a base illustration and optional `stateImages` for approved expressions. Missing state artwork falls back to the base image; missing base artwork falls back to a labeled wordmark. No artwork is generated or inferred from the reference sheet. Transparent artwork works best for motion.

Workflow owners should set states and meaningful messages from actual events. `listening` does not enable a microphone. The dashboard only demonstrates a local greeting, then returns to idle; it does not simulate recovery or patient activity.
