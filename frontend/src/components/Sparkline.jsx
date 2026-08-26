import React from 'react'

export default function Sparkline({ values = [], width = 96, height = 26 }) {
  if (!Array.isArray(values) || values.length < 2) {
    return <span className="stat-spark-empty">нет истории</span>
  }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const stepX = (width - 6) / (values.length - 1)
  const points = values.map((value, index) => [
    3 + index * stepX,
    height - 3 - ((value - min) / span) * (height - 6),
  ])
  const [lastX, lastY] = points[points.length - 1]
  return (
    <svg
      className="stat-sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      shapeRendering="crispEdges"
      aria-hidden="true"
      data-hint="Динамика показателя по раундам: чем длиннее линия, тем больше раундов оценил Хрономант."
    >
      <polyline
        points={points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <rect x={lastX - 2} y={lastY - 2} width="4" height="4" fill="currentColor" />
    </svg>
  )
}
