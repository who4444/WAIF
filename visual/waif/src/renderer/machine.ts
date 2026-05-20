import { setup, assign } from 'xstate'

type CompanionContext = {
  speechText: string
  audioUrl: string
  targetX: number
  targetY: number
}

type CompanionEvent =
  | { type: 'WAKE' }
  | { type: 'ALERT' }
  | { type: 'NAVIGATE'; x: number; y: number; label?: string }
  | { type: 'FOCUS_MODE' }
  | { type: 'FOCUS_END' }
  | { type: 'SLEEP' }
  | { type: 'TASK_START' }
  | { type: 'SPEECH'; text?: string; audio_url?: string }
  | { type: 'SPEECH_END' }

export const companionMachine = setup({
  types: {} as {
    context: CompanionContext
    events: CompanionEvent
  },
  actions: {
    assignSpeech: assign({
      speechText: ({ event }) => event.type === 'SPEECH' ? event.text ?? '' : '',
      audioUrl: ({ event }) => event.type === 'SPEECH' ? event.audio_url ?? '' : '',
    }),
    assignTarget: assign({
      targetX: ({ event }) => event.type === 'NAVIGATE' ? event.x : 0,
      targetY: ({ event }) => event.type === 'NAVIGATE' ? event.y : 0,
    }),
  },
}).createMachine({
  id: 'companion',
  initial: 'idle',
  context: {
    speechText: '',
    audioUrl: '',
    targetX: 0,
    targetY: 0,
  },
  states: {
    idle: {
      on: {
        WAKE: 'listening',
        ALERT: 'alert',
        NAVIGATE: {
          target: 'interacting',
          actions: 'assignTarget',
        },
        FOCUS_MODE: 'focused_dim',
        SLEEP: 'sleeping',
        SPEECH: { target: 'speaking', actions: 'assignSpeech' },
      },
    },
    listening: {
      on: {
        TASK_START: 'processing',
        SPEECH: { target: 'speaking', actions: 'assignSpeech' },
        WAKE: 'idle',
      },
    },
    processing: {
      on: {
        SPEECH: { target: 'speaking', actions: 'assignSpeech' },
        WAKE: 'idle',
      },
    },
    speaking: {
      on: {
        SPEECH_END: 'idle',
        WAKE: 'listening',
      },
    },
    alert: {
      on: {
        WAKE: 'listening',
        SPEECH_END: 'idle',
        SPEECH: { target: 'speaking', actions: 'assignSpeech' },
      },
    },
    interacting: {
      on: {
        WAKE: 'listening',
        SPEECH: { target: 'speaking', actions: 'assignSpeech' },
      },
    },
    focused_dim: {
      on: {
        FOCUS_END: 'idle',
        WAKE: 'listening',
        ALERT: 'alert',
        SPEECH: { target: 'speaking', actions: 'assignSpeech' },
      },
    },
    sleeping: {
      on: {
        WAKE: 'idle',
        ALERT: 'alert',
        SPEECH: { target: 'speaking', actions: 'assignSpeech' },
      },
    },
  },
})

export type CompanionState = typeof companionMachine
