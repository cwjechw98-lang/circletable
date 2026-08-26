const MASCOT_DEFS = {
  owl:     { emoji: '🦉', color: '#aa44ff' },
  robot:   { emoji: '🤖', color: '#00ff66' },
  cat:     { emoji: '🐱', color: '#4488ff' },
  llama:   { emoji: '🦙', color: '#ff8833' },
  dragon:  { emoji: '🐲', color: '#ff3355' },
  wizard:  { emoji: '🧙', color: '#00f0f0' },
  ghost:   { emoji: '👻', color: '#e0e0e8' },
  crystal: { emoji: '💎', color: '#1abc9c' },
  fox:     { emoji: '🦊', color: '#e67e22' },
  panda:   { emoji: '🐼', color: '#95a5a6' },
  wolf:    { emoji: '🐺', color: '#7f8c8d' },
  tiger:   { emoji: '🐯', color: '#f39c12' },
  frog:    { emoji: '🐸', color: '#2ecc71' },
  octopus: { emoji: '🐙', color: '#9b59b6' },
  alien:   { emoji: '👽', color: '#7bed9f' },
  bat:     { emoji: '🦇', color: '#6c5ce7' },
  bee:     { emoji: '🐝', color: '#f1c40f' },
  eagle:   { emoji: '🦅', color: '#c6a56b' },
  unicorn: { emoji: '🦄', color: '#ff66cc' },
  raccoon: { emoji: '🦝', color: '#a1887f' },
}

const MASCOT_LABELS = {
  owl: 'сова',
  robot: 'робот',
  cat: 'кот',
  llama: 'лама',
  dragon: 'дракон',
  wizard: 'маг',
  ghost: 'призрак',
  crystal: 'кристалл',
  fox: 'лис',
  panda: 'панда',
  wolf: 'волк',
  tiger: 'тигр',
  frog: 'лягушка',
  octopus: 'осьминог',
  alien: 'пришелец',
  bat: 'летучая мышь',
  bee: 'пчела',
  eagle: 'орёл',
  unicorn: 'единорог',
  raccoon: 'енот',
}

const ROLE_FALLBACK_MASCOTS = {
  strategist: 'owl',
  creative: 'robot',
  critic: 'cat',
  analyst: 'fox',
  diplomat: 'crystal',
  pragmatist: 'panda',
  investigator: 'ghost',
  showman: 'dragon',
  optimist: 'bee',
  skeptic: 'wolf',
  provocateur: 'bat',
  synthesizer: 'unicorn',
  visionary: 'eagle',
}

const EMOJI_FALLBACK_MASCOTS = Object.fromEntries(
  Object.entries(MASCOT_DEFS).map(([mascot, def]) => [def.emoji, mascot]),
)

// Temporary per-mascot switch. Flip any entry to `emoji` while redrawing that character.
const MASCOT_VISUAL_MODES = {
  owl: 'sprite',
  robot: 'sprite',
  cat: 'sprite',
  llama: 'sprite',
  dragon: 'sprite',
  wizard: 'sprite',
  ghost: 'sprite',
  crystal: 'sprite',
  fox: 'sprite',
  panda: 'sprite',
  wolf: 'sprite',
  tiger: 'sprite',
  frog: 'sprite',
  octopus: 'sprite',
  alien: 'sprite',
  bat: 'sprite',
  bee: 'sprite',
  eagle: 'sprite',
  unicorn: 'sprite',
  raccoon: 'sprite',
}

function resolveMascot(agent) {
  if (agent?.mascot && MASCOT_DEFS[agent.mascot]) {
    return agent.mascot
  }
  if (agent?.emoji && EMOJI_FALLBACK_MASCOTS[agent.emoji]) {
    return EMOJI_FALLBACK_MASCOTS[agent.emoji]
  }
  if (agent?.role && ROLE_FALLBACK_MASCOTS[agent.role]) {
    return ROLE_FALLBACK_MASCOTS[agent.role]
  }
  return 'wizard'
}

function getMascotVisualMode(mascot) {
  return MASCOT_VISUAL_MODES[mascot] || 'sprite'
}

export {
  MASCOT_DEFS,
  MASCOT_LABELS,
  MASCOT_VISUAL_MODES,
  getMascotVisualMode,
  resolveMascot,
}
