export const SPECIALTY_GROUPS = [
  {
    label: 'Бизнес и рост',
    options: [
      { value: 'digital-generalist', label: 'Универсальный эксперт по цифровому бизнесу' },
      { value: 'marketing-generalist', label: 'Маркетолог-универсал' },
      { value: 'product-marketing', label: 'Продуктовый маркетолог' },
      { value: 'seo-strategy', label: 'SEO и органический рост' },
      { value: 'brand-content', label: 'Бренд, контент и копирайтинг' },
      { value: 'sales-funnels', label: 'Продажи и воронки' },
      { value: 'pr-comms', label: 'PR и внешние коммуникации' },
      { value: 'business-dev', label: 'Бизнес-девелопмент и партнёрства' },
    ],
  },
  {
    label: 'Продукт и технологии',
    options: [
      { value: 'product-manager', label: 'Продуктовый менеджмент' },
      { value: 'ux-research', label: 'UX, интерфейсы и исследование пользователей' },
      { value: 'frontend-engineer', label: 'Фронтенд и клиентский UX' },
      { value: 'backend-architect', label: 'Бэкенд и архитектура систем' },
      { value: 'ai-automation', label: 'AI, автоматизация и агентные системы' },
      { value: 'data-analytics', label: 'Аналитика данных и метрики' },
      { value: 'cybersecurity', label: 'Кибербезопасность и технические риски' },
      { value: 'fintech-systems', label: 'Финтех и платёжные системы' },
    ],
  },
  {
    label: 'Финансы и право',
    options: [
      { value: 'economist', label: 'Экономика и макротренды' },
      { value: 'finance-strategy', label: 'Финансы, unit-экономика и бюджеты' },
      { value: 'investor', label: 'Инвестиционный анализ' },
      { value: 'lawyer', label: 'Юридическая экспертиза' },
      { value: 'compliance-risk', label: 'Комплаенс и регуляторные риски' },
    ],
  },
  {
    label: 'Люди и процессы',
    options: [
      { value: 'ops-manager', label: 'Операционный менеджмент' },
      { value: 'hr-people', label: 'HR, найм и оргдизайн' },
      { value: 'psychologist', label: 'Психология и поведение людей' },
      { value: 'coach-facilitator', label: 'Коучинг и фасилитация' },
      { value: 'customer-success', label: 'Клиентский сервис и удержание' },
    ],
  },
  {
    label: 'Медиа и креатив',
    options: [
      { value: 'producer', label: 'Продюсирование и запуск проектов' },
      { value: 'storyteller', label: 'Сторителлинг и сценарное мышление' },
      { value: 'creator-blogger', label: 'Блогинг и личный бренд' },
      { value: 'community-smm', label: 'SMM и комьюнити' },
      { value: 'design-creative', label: 'Креативный директор и дизайн-мышление' },
    ],
  },
  {
    label: 'Необычные оптики',
    options: [
      { value: 'philosophy', label: 'Философия и смысловые конструкции' },
      { value: 'sports-coach', label: 'Спортивный тренер и дисциплина' },
      { value: 'infobiz', label: 'Инфобизнес и упаковка экспертизы' },
      { value: 'standup', label: 'Стендап и комедийная подача' },
      { value: 'mystic', label: 'Гадалка-мистификатор' },
    ],
  },
]

export const SPECIALTY_OPTIONS = SPECIALTY_GROUPS.flatMap((group) => group.options)

export const SPECIALTY_LABELS = Object.fromEntries(
  SPECIALTY_OPTIONS.map((specialty) => [specialty.value, specialty.label]),
)

export function normalizeCustomSpecialtyGroups(customGroups = []) {
  return (customGroups || [])
    .map((group) => {
      const groupLabel = group?.label || group?.groupLabel || 'Кастомные оптики'
      const options = (group?.options || [])
        .filter((option) => option?.value && option?.label)
        .map((option) => ({
          id: option.id,
          value: option.value,
          label: option.label,
          description: option.description || '',
          groupLabel,
        }))
      return { label: groupLabel, options }
    })
    .filter((group) => group.options.length > 0)
}

export function mergeSpecialtyGroups(customGroups = []) {
  const seen = new Set(SPECIALTY_OPTIONS.map((specialty) => specialty.value))
  const normalizedCustomGroups = normalizeCustomSpecialtyGroups(customGroups)
    .map((group) => ({
      ...group,
      options: group.options.filter((option) => {
        if (seen.has(option.value)) return false
        seen.add(option.value)
        return true
      }),
    }))
    .filter((group) => group.options.length > 0)
  return [...SPECIALTY_GROUPS, ...normalizedCustomGroups]
}

export function getSpecialtyValues(customGroups = []) {
  return new Set(mergeSpecialtyGroups(customGroups).flatMap((group) => group.options.map((option) => option.value)))
}

export function buildSpecialtyLabels(customGroups = []) {
  const labels = { ...SPECIALTY_LABELS }
  normalizeCustomSpecialtyGroups(customGroups).forEach((group) => {
    group.options.forEach((option) => {
      labels[option.value] = option.label
    })
  })
  return labels
}

export function getSpecialtyLabel(specialty, customLabelOrLabels) {
  if (typeof customLabelOrLabels === 'string' && customLabelOrLabels.trim()) {
    return customLabelOrLabels
  }
  if (customLabelOrLabels && typeof customLabelOrLabels === 'object' && customLabelOrLabels[specialty]) {
    return customLabelOrLabels[specialty]
  }
  return SPECIALTY_LABELS[specialty] || specialty
}
