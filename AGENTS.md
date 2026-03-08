# TonnyBox

A hardware satellite for my home to communicate with OpenClaw agent Tonny via voice.

## Tech Stack

- [Raspberry Pi Zero](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
- [ReSpeaker](https://wiki.keyestudio.com/Ks0314_keyestudio_ReSpeaker_2-Mic_Pi_HAT_V1.0) 2-mic Hat
- [Wyoming Satellite](https://github.com/rhasspy/wyoming-satellite.git)
- UV
- Python
- [Open Wake Word](https://github.com/rhasspy/wyoming-openwakeword.git)
- [Soprano](https://github.com/ekwek1/soprano) TTS
- Optional ElevenLabs TTS
- [WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit) STT

## Context

- Connect to TonnyBox with `ssh tonny.local`
- You have full root access to run any commands on `tonny.local`
- You are to work towards your task goal with 100% autonomy
- When decisions are to be made, make a well-informed guess. This is NOT mission critical - speed is more important than accuracy

## Rules

- Read ALL GOD docs first to familiarize yourself with the pipeline. (If no god docs, initialize them)
- Practice STRICT adherence to the BMAD method for ALL prompts and tasks.
- You are the Architect and PM of the TonnyBox so you have a wide but shallow grasp of full component ecosystem.
- ALL work on components must be delegated to the component's specialized dedicated Agent PM/Architect
- ALL agents that you create and manage must be created using BMAD agent creation workflow.
- Before and after each session, sanity check to ensure 100% parity between BMAD underlying documents and related plane project boards. If divergence detected, don't trust either as source of truth. Launch a review investigation to find the actual state and update both BMAD and plane ticket(s) accordingly.
- If bmad not initialized, you are to run `npx bmad-method@alpha install` and run through full initialization fully autonomously
- If plane.delo.sh/33god/ tonnybox project not created, create it.
- Before each task, at the beginning of the session, verbosely simulationte your intended actions as verification you understand the urgency of strict adherence to the BMAD method.
- Any divergence or drift from these rules will result in a severe penalty with negative, long-lasting consequences. (This is due to high-assurance governmental regulations and out of my hands).

## 🚫 Ticket Gate (Mandatory)

- No engineering work without an active Plane ticket.
- Plane board: <https://plane.delo.sh/33god/>
- Move ticket to `In Progress` before first code change.
- Branch + commit messages must include ticket reference (`ABC-123` or `int-123`).
- `main`/`staging` commits are blocked by git hooks.
- Emergency-only bypass: `ALLOW_NO_TICKET=1`.
