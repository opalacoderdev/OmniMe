import React from 'react';

// Renders chat message content, converting simple markdown syntax to styled HTML elements.
export function formatMessageContent(content) {
  if (!content) return null;
  const lines = content.split('\n');
  return lines.map((line, idx) => {
    const trimmed = line.trim();

    // Headings: ### Title
    if (trimmed.startsWith('### ')) {
      const title = trimmed.replace('### ', '');
      return (
        <h4 key={idx} style={{ margin: '14px 0 6px 0', fontWeight: 'bold', color: '#ffffff', fontSize: '13px' }}>
          {title}
        </h4>
      );
    }

    // Emoji bullet lists: 🔹 **`cmd`** — desc  or  ⭐ **`cmd`** — desc
    if (trimmed.startsWith('🔹 ') || trimmed.startsWith('⭐ ')) {
      const icon = trimmed.substring(0, 2);
      const rest = trimmed.substring(2);

      const parts = rest.split('—');
      if (parts.length >= 2) {
        const cmdPart = parts[0].replace(/\*\*`|`\*\*/g, '').trim();
        const descPart = parts.slice(1).join('—').trim();
        return (
          <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', margin: '4px 0', paddingLeft: '4px' }}>
            <span style={{ fontSize: '12px', flexShrink: 0 }}>{icon}</span>
            <span style={{ fontSize: '13px', lineHeight: '1.4' }}>
              <code style={{ background: '#2d2d2d', padding: '2px 4px', borderRadius: '3px', color: '#f8f8f2', fontFamily: 'monospace', fontSize: '11px', marginRight: '6px' }}>
                {cmdPart}
              </code>
              <span style={{ color: '#cccccc' }}>{descPart}</span>
            </span>
          </div>
        );
      }
    }

    // Footnote notes: _(note)_
    if (trimmed.startsWith('_(') && trimmed.endsWith(')_')) {
      const note = trimmed.substring(2, trimmed.length - 2);
      return (
        <p key={idx} style={{ margin: '8px 0', fontStyle: 'italic', color: '#8a8a8a', fontSize: '11px' }}>
          {note}
        </p>
      );
    }

    // Regular line (preserving line breaks)
    return (
      <div key={idx} style={{ minHeight: '1.2em', color: '#cccccc', fontSize: '13px', margin: '2px 0' }}>
        {line}
      </div>
    );
  });
}
