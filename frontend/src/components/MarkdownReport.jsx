import React from 'react'

function escapeHtml(value) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function formatInline(text) {
  let html = escapeHtml(text)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/_([^_]+)_/g, '<em>$1</em>')
  return html
}

function markdownToHtml(markdown) {
  const lines = (markdown || '').replaceAll('\r\n', '\n').split('\n')
  const chunks = []
  let paragraph = []
  let listType = null
  let listItems = []

  function flushParagraph() {
    if (!paragraph.length) return
    chunks.push(`<p>${formatInline(paragraph.join(' '))}</p>`)
    paragraph = []
  }

  function flushList() {
    if (!listItems.length || !listType) return
    const tag = listType
    chunks.push(`<${tag}>${listItems.map((item) => `<li>${formatInline(item)}</li>`).join('')}</${tag}>`)
    listItems = []
    listType = null
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()
    if (!line.trim()) {
      flushParagraph()
      flushList()
      continue
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/)
    if (headingMatch) {
      flushParagraph()
      flushList()
      const level = Math.min(headingMatch[1].length, 3)
      chunks.push(`<h${level}>${formatInline(headingMatch[2])}</h${level}>`)
      continue
    }

    const orderedMatch = line.match(/^\d+\.\s+(.+)$/)
    if (orderedMatch) {
      flushParagraph()
      if (listType !== 'ol') {
        flushList()
        listType = 'ol'
      }
      listItems.push(orderedMatch[1])
      continue
    }

    const unorderedMatch = line.match(/^[-*]\s+(.+)$/)
    if (unorderedMatch) {
      flushParagraph()
      if (listType !== 'ul') {
        flushList()
        listType = 'ul'
      }
      listItems.push(unorderedMatch[1])
      continue
    }

    const quoteMatch = line.match(/^>\s+(.+)$/)
    if (quoteMatch) {
      flushParagraph()
      flushList()
      chunks.push(`<blockquote><p>${formatInline(quoteMatch[1])}</p></blockquote>`)
      continue
    }

    flushList()
    paragraph.push(line.trim())
  }

  flushParagraph()
  flushList()
  return chunks.join('')
}

export default function MarkdownReport({ markdown }) {
  const html = markdownToHtml(markdown)
  return (
    <div
      className="chat-report-markdown"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
