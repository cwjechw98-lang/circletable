export const ROLE_OPTIONS = [
  { value: 'strategist', label: 'Стратег' },
  { value: 'creative', label: 'Изобретатель' },
  { value: 'critic', label: 'Критик' },
  { value: 'synthesizer', label: 'Синтезатор' },
  { value: 'visionary', label: 'Визионер' },
  { value: 'analyst', label: 'Аналитик' },
  { value: 'provocateur', label: 'Провокатор' },
  { value: 'diplomat', label: 'Дипломат' },
  { value: 'pragmatist', label: 'Прагматик' },
  { value: 'skeptic', label: 'Скептик' },
  { value: 'philosopher', label: 'Философ' },
  { value: 'mentor', label: 'Наставник' },
  { value: 'investigator', label: 'Расследователь' },
  { value: 'optimist', label: 'Оптимист' },
  { value: 'pessimist', label: 'Пессимист' },
  { value: 'comedian', label: 'Комик' },
  { value: 'showman', label: 'Шоумен' },
]

export const ROLE_LABELS = Object.fromEntries(
  ROLE_OPTIONS.map((role) => [role.value, role.label]),
)

export function getRoleLabel(role) {
  return ROLE_LABELS[role] || role
}
