import React, { useEffect, useRef, useState } from 'react';
import { Send, X, Wand2, Wrench, MessageSquarePlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * InlinePromptOverlay
 *
 * A floating panel that appears anchored near the Monaco cursor/selection.
 * Props:
 *   inlinePrompt  — { x, y, startLine, endLine, cursorCol, selectedText, mode }
 *                   mode: 'free' | 'refine' | 'fix'
 *   onSubmit(instruction: string) — called when user confirms
 *   onClose()                     — called when user dismisses
 */
export default function InlinePromptOverlay({ inlinePrompt, onSubmit, onClose }) {
  const { t } = useTranslation();
  const inputRef = useRef(null);
  const [value, setValue] = useState('');

  // Reset value and focus when prompt opens / mode changes
  useEffect(() => {
    if (!inlinePrompt) return;
    const defaults = {
      refine: t('editorPanel.inlinePromptRefineDefault'),
      fix: t('editorPanel.inlinePromptFixDefault'),
      free: '',
    };
    setValue(defaults[inlinePrompt.mode] ?? '');
    // Slight delay so Monaco doesn't steal focus back
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [inlinePrompt]);

  if (!inlinePrompt) return null;

  const { x, y, startLine, endLine, selectedText, mode } = inlinePrompt;

  const modeIcon = {
    refine: <Wand2 size={13} style={{ color: '#4ec9b0' }} />,
    fix: <Wrench size={13} style={{ color: '#f48771' }} />,
    free: <MessageSquarePlus size={13} style={{ color: '#75beff' }} />,
  }[mode] ?? null;

  const modeLabel = {
    refine: t('editorPanel.refineSelection'),
    fix: t('editorPanel.fixSelection'),
    free: t('editorPanel.inlinePromptTitle'),
  }[mode] ?? '';

  const hasSelection = selectedText && selectedText.trim().length > 0;
  const lineInfo = hasSelection
    ? `Lines ${startLine}–${endLine}`
    : `Line ${startLine}, col ${inlinePrompt.cursorCol}`;

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  const handleSubmit = () => {
    const instruction = value.trim();
    if (!instruction) return;
    onSubmit(instruction);
  };

  // Clamp position so the overlay stays on-screen
  const overlayWidth = 380;
  const overlayHeight = 130;
  const safeX = Math.min(x, window.innerWidth - overlayWidth - 16);
  const safeY = Math.min(y, window.innerHeight - overlayHeight - 16);

  return (
    <>
      {/* Backdrop — clicking outside closes overlay */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 9998,
          background: 'transparent',
        }}
        onMouseDown={onClose}
      />

      {/* Overlay panel */}
      <div
        style={{
          position: 'fixed',
          top: `${safeY}px`,
          left: `${safeX}px`,
          zIndex: 9999,
          width: `${overlayWidth}px`,
          background: 'rgba(30, 30, 35, 0.92)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: '8px',
          boxShadow: '0 8px 32px rgba(0,0,0,0.55)',
          padding: '10px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          animation: 'inlineOverlayFadeIn 0.12s ease-out',
        }}
        onMouseDown={(e) => e.stopPropagation()} // prevent backdrop close
      >
        {/* Header row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {modeIcon}
            <span style={{ fontSize: '11px', fontWeight: 600, color: '#ccc', letterSpacing: '0.03em' }}>
              {modeLabel}
            </span>
            <span style={{ fontSize: '10px', color: '#555', marginLeft: '4px' }}>
              {lineInfo}
            </span>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: '#666',
              padding: '2px',
              display: 'flex',
              alignItems: 'center',
              borderRadius: '3px',
            }}
            onMouseEnter={(e) => e.currentTarget.style.color = '#aaa'}
            onMouseLeave={(e) => e.currentTarget.style.color = '#666'}
          >
            <X size={13} />
          </button>
        </div>

        {/* Snippet preview (if selection) */}
        {hasSelection && (
          <div
            style={{
              fontSize: '10px',
              color: '#888',
              background: 'rgba(255,255,255,0.04)',
              borderRadius: '4px',
              padding: '4px 6px',
              maxHeight: '40px',
              overflow: 'hidden',
              whiteSpace: 'pre',
              fontFamily: 'monospace',
              borderLeft: '2px solid #3c3c5c',
            }}
          >
            {selectedText.length > 120 ? selectedText.slice(0, 120) + '…' : selectedText}
          </div>
        )}

        {/* Input row */}
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('editorPanel.inlinePromptPlaceholder')}
            style={{
              flex: 1,
              fontSize: '12px',
              padding: '5px 8px',
              background: 'rgba(255,255,255,0.07)',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '5px',
              color: '#e0e0e0',
              outline: 'none',
              fontFamily: 'inherit',
              transition: 'border-color 0.15s',
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = '#007acc'; e.currentTarget.select(); }}
            onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)'; }}
          />
          <button
            onClick={handleSubmit}
            disabled={!value.trim()}
            style={{
              background: value.trim() ? '#007acc' : '#2a2a2a',
              border: 'none',
              borderRadius: '5px',
              color: value.trim() ? '#fff' : '#555',
              cursor: value.trim() ? 'pointer' : 'not-allowed',
              padding: '5px 9px',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => { if (value.trim()) e.currentTarget.style.background = '#1177bb'; }}
            onMouseLeave={(e) => { if (value.trim()) e.currentTarget.style.background = '#007acc'; }}
          >
            <Send size={12} />
            <span>{t('editorPanel.inlinePromptSend')}</span>
          </button>
        </div>

        {/* Hint */}
        <span style={{ fontSize: '10px', color: '#444', userSelect: 'none' }}>
          Enter {t('editorPanel.inlinePromptSend').toLowerCase()} · Esc {t('editorPanel.inlinePromptCancel').toLowerCase()}
        </span>
      </div>
    </>
  );
}
