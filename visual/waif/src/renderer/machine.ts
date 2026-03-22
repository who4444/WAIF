import { createMachine, assign } from 'xstate'

const speechAssign = assign({
  speechText: ({ event }: any) => event.text ?? '',
  audioUrl: ({ event }: any) => event.audio_url ?? '',
})

export const companionMachine = createMachine({
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
        WANDER_START: 'wandering',
        FOCUS_MODE: 'focused_dim',
        SLEEP: 'sleeping',
        SPEECH: { target: 'speaking', actions: speechAssign },
      },
    },
    listening: {
      on: {
        TASK_START: 'processing',
        SPEECH: { target: 'speaking', actions: speechAssign },
        WAKE: 'idle',
      },
    },
    processing: {
      on: {
        SPEECH: { target: 'speaking', actions: speechAssign },
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
        SPEECH: { target: 'speaking', actions: speechAssign },
      },
    },
    wandering: {
      on: {
        WANDER_STOP: 'idle',
        NAVIGATE: {
          target: 'interacting',
          actions: assign({
            targetX: ({ event }: any) => event.x,
            targetY: ({ event }: any) => event.y,
          }),
        },
        WAKE: 'listening',
        ALERT: 'alert',
        SPEECH: { target: 'speaking', actions: speechAssign },
      },
    },
    interacting: {
      on: {
        WANDER_START: 'wandering',
        WANDER_STOP: 'idle',
        WAKE: 'listening',
        SPEECH: { target: 'speaking', actions: speechAssign },
      },
    },
    focused_dim: {
      on: {
        FOCUS_END: 'idle',
        WAKE: 'listening',
        ALERT: 'alert',
        SPEECH: { target: 'speaking', actions: speechAssign },
      },
    },
    sleeping: {
      on: {
        WAKE: 'idle',
        ALERT: 'alert',
        SPEECH: { target: 'speaking', actions: speechAssign },
      },
    },
  },
})

export type CompanionState = typeof companionMachine