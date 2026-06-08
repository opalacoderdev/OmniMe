import { useRef, useState, useCallback } from 'react';
import { MessageSquare, Cpu, HelpCircle, Check, X, ArrowRight, Eraser, Globe, Settings } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { formatMessageContent } from '../utils/formatMessage';
import { readClipboard } from '../utils/clipboard.js';
import { useTextContextMenu } from '../hooks/useTextContextMenu.js';
import TextContextMenu from './TextContextMenu.jsx';

// Right-side chat panel for interacting with the OpalaCoder agent.
export default function ChatPanel({
  chatMessages,
  chatInput,
  setChatInput,
  isAgentRunning,
  activeProject,
  isChatVisible,
  setIsChatVisible,
  chatWidth,
  handleSendMessage,
  handleInterruptAgent,
  chatEndRef,
  onClearChat,
  webSearchConfig,
  setWebSearchConfig,
}) {
  const { t } = useTranslation();
  const historyRef = useRef(null);
  const inputRef = useRef(null);
  const { menu, onContextMenu, handleCopy, handleSelectAll, close: closeMenu } = useTextContextMenu();

  const handlePaste = useCallback(() => {
    readClipboard().then((text) => {
      if (!text) return;
      const el = inputRef.current;
      if (el) {
        const start = el.selectionStart ?? chatInput.length;
        const end = el.selectionEnd ?? chatInput.length;
        const next = chatInput.slice(0, start) + text + chatInput.slice(end);
        setChatInput(next);
        requestAnimationFrame(() => {
          el.focus();
          const pos = start + text.length;
          el.setSelectionRange(pos, pos);
        });
      } else {
        setChatInput((prev) => prev + text);
      }
    });
    closeMenu();
  }, [chatInput, setChatInput, closeMenu]);

  // Chat input history state
  const [inputHistory, setInputHistory] = useState(() => {
    try {
      const saved = localStorage.getItem('chatInputHistory');
      return saved ? JSON.parse(saved) : [];
    } catch (_) {
      return [];
    }
  });
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [tempInput, setTempInput] = useState('');

  // MCP config panel state
  const [showMcpPanel, setShowMcpPanel] = useState(false);
  const [mcpUrlDraft, setMcpUrlDraft] = useState('');
  const [mcpToolDraft, setMcpToolDraft] = useState('web_search');
  const [mcpApiKeyDraft, setMcpApiKeyDraft] = useState('');
  const [useMcpDraft, setUseMcpDraft] = useState(false);
  const [mcpTestStatus, setMcpTestStatus] = useState(''); // '', 'testing', 'ok', 'error:<msg>'

  if (!isChatVisible) return null;

  const searchEnabled = webSearchConfig?.enabled ?? true;

  const handleToggleWebSearch = async () => {
    const newEnabled = !searchEnabled;
    const updated = { ...webSearchConfig, enabled: newEnabled };
    setWebSearchConfig(updated);
    try {
      await fetch('/api/settings/web-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated),
      });
    } catch (_) {}
  };

  const handleOpenMcp = () => {
    setMcpUrlDraft(webSearchConfig?.mcp_url || '');
    setMcpToolDraft(webSearchConfig?.mcp_tool || 'web_search');
    setMcpApiKeyDraft(webSearchConfig?.mcp_api_key || '');
    const provider = webSearchConfig?.provider;
    const isMcp = provider ? (provider === 'mcp') : !!(webSearchConfig?.mcp_url);
    setUseMcpDraft(isMcp);
    setMcpTestStatus('');
    setShowMcpPanel(p => !p);
  };

  const handleSaveMcp = async () => {
    const updated = {
      ...webSearchConfig,
      mcp_url: mcpUrlDraft.trim(),
      mcp_tool: mcpToolDraft.trim() || 'web_search',
      mcp_api_key: mcpApiKeyDraft.trim(),
      provider: useMcpDraft ? 'mcp' : 'duckduckgo',
    };
    setWebSearchConfig(updated);
    try {
      await fetch('/api/settings/web-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated),
      });
      setShowMcpPanel(false);
    } catch (_) {}
  };

  const handleTestMcp = async () => {
    setMcpTestStatus('testing');
    try {
      const res = await fetch('/api/settings/web-search/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mcp_url: mcpUrlDraft.trim(),
          mcp_tool: mcpToolDraft.trim() || 'web_search',
          mcp_api_key: mcpApiKeyDraft.trim(),
        }),
      });
      const data = await res.json();
      setMcpTestStatus(data.ok ? 'ok' : `error:${data.error || 'Unknown error'}`);
    } catch (e) {
      setMcpTestStatus(`error:${e.message}`);
    }
  };

  const handleFormSubmit = (e) => {
    if (e) e.preventDefault();
    if (!chatInput.trim() || !activeProject || isAgentRunning) return;
    const text = chatInput.trim();
    setInputHistory(prev => {
      if (prev[prev.length - 1] === text) return prev;
      const newHist = [...prev, text].slice(-100);
      try {
        localStorage.setItem('chatInputHistory', JSON.stringify(newHist));
      } catch (_) {}
      return newHist;
    });
    setHistoryIndex(-1);
    setTempInput('');
    handleSendMessage(e);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowUp') {
      if (inputHistory.length === 0) return;
      e.preventDefault();
      let newIndex;
      if (historyIndex === -1) {
        setTempInput(chatInput);
        newIndex = inputHistory.length - 1;
      } else {
        newIndex = Math.max(0, historyIndex - 1);
      }
      setHistoryIndex(newIndex);
      setChatInput(inputHistory[newIndex]);
    } else if (e.key === 'ArrowDown') {
      if (historyIndex === -1) return;
      e.preventDefault();
      if (historyIndex === inputHistory.length - 1) {
        setHistoryIndex(-1);
        setChatInput(tempInput);
      } else {
        const newIndex = historyIndex + 1;
        setHistoryIndex(newIndex);
        setChatInput(inputHistory[newIndex]);
      }
    } else if (e.key === 'Escape') {
      if (historyIndex !== -1) {
        e.preventDefault();
        setHistoryIndex(-1);
        setChatInput(tempInput);
      }
    }
  };

  const hasMcp = webSearchConfig?.provider === 'mcp' && !!(webSearchConfig?.mcp_url);

  return (
    <aside className="vscode-chat" style={{ width: `${chatWidth}px` }}>
      <TextContextMenu
        menu={menu}
        onCopy={handleCopy}
        onPaste={handlePaste}
        onSelectAll={() => handleSelectAll(historyRef)}
      />
      {/* Header */}
      <div className="vscode-chat-header">
        <span className="vscode-sidebar-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <MessageSquare size={12} style={{ color: '#007acc' }} />
          <span>{t('chatPanel.header')}</span>
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={onClearChat}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
            title={t('chatPanel.clearChat')}
          >
            <Eraser size={14} />
          </button>
          <button
            onClick={() => setIsChatVisible(false)}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Quick actions toolbar */}
      <div className="vscode-chat-toolbar">
        <button onClick={() => setChatInput('/skills')} className="vscode-chat-tool-btn">
          <Cpu size={11} />
          <span>/skills</span>
        </button>
        <button onClick={() => setChatInput('/help')} className="vscode-chat-tool-btn">
          <HelpCircle size={11} />
          <span>/help</span>
        </button>
        <button onClick={() => setChatInput('/commit')} className="vscode-chat-tool-btn">
          <Check size={11} />
          <span>/commit</span>
        </button>
      </div>

      {/* Web Search toggle bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '4px 10px',
          borderBottom: '1px solid var(--border-color, #333)',
          background: 'var(--sidebar-bg, #1e1e1e)',
          minHeight: '28px',
          gap: '6px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Globe size={12} style={{ color: searchEnabled ? '#4ec9b0' : '#666' }} />
          <span style={{ fontSize: '11px', color: searchEnabled ? '#ccc' : '#666', userSelect: 'none' }}>
            {t('chatPanel.webSearch')}
            {hasMcp && searchEnabled && (
              <span style={{ marginLeft: '4px', fontSize: '10px', color: '#888' }}>{t('chatPanel.mcpIndicator')}</span>
            )}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {/* Settings / MCP gear button */}
          <button
            onClick={handleOpenMcp}
            title={t('chatPanel.configureMcp')}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: showMcpPanel ? '#4ec9b0' : '#555',
              padding: '1px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <Settings size={11} />
          </button>
          {/* Toggle switch */}
          <button
            id="web-search-toggle"
            onClick={handleToggleWebSearch}
            title={searchEnabled ? t('chatPanel.disableWebSearch') : t('chatPanel.enableWebSearch')}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: '0',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <div
              style={{
                width: '28px',
                height: '14px',
                borderRadius: '7px',
                background: searchEnabled ? '#4ec9b0' : '#444',
                position: 'relative',
                transition: 'background 0.2s',
              }}
            >
              <div
                style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  background: '#fff',
                  position: 'absolute',
                  top: '2px',
                  left: searchEnabled ? '16px' : '2px',
                  transition: 'left 0.2s',
                }}
              />
            </div>
          </button>
        </div>
      </div>

      {/* MCP config panel (inline, collapsible) */}
      {showMcpPanel && (
        <div
          style={{
            padding: '8px 10px',
            borderBottom: '1px solid var(--border-color, #333)',
            background: 'var(--sidebar-bg, #1a1a1a)',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
            <input
              id="use-mcp-checkbox"
              type="checkbox"
              checked={useMcpDraft}
              onChange={e => setUseMcpDraft(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            <label htmlFor="use-mcp-checkbox" style={{ fontSize: '11px', color: '#ccc', cursor: 'pointer', userSelect: 'none' }}>
              {t('chatPanel.useMcpServer')}
            </label>
          </div>

          <label style={{ fontSize: '10px', color: useMcpDraft ? '#aaa' : '#555' }}>{t('chatPanel.serverUrl')}</label>
          <input
            id="mcp-url-input"
            type="text"
            value={mcpUrlDraft}
            disabled={!useMcpDraft}
            onChange={e => { setMcpUrlDraft(e.target.value); setMcpTestStatus(''); }}
            placeholder={t('chatPanel.mcpUrlPlaceholder')}
            style={{
              fontSize: '11px',
              padding: '3px 6px',
              background: useMcpDraft ? '#2d2d2d' : '#222',
              border: '1px solid #444',
              borderRadius: '3px',
              color: useMcpDraft ? '#ccc' : '#666',
              outline: 'none',
            }}
          />

          <label style={{ fontSize: '10px', color: useMcpDraft ? '#aaa' : '#555' }}>{t('chatPanel.toolName')}</label>
          <input
            id="mcp-tool-input"
            type="text"
            value={mcpToolDraft}
            disabled={!useMcpDraft}
            onChange={e => { setMcpToolDraft(e.target.value); setMcpTestStatus(''); }}
            placeholder={t('chatPanel.mcpToolPlaceholder')}
            style={{
              fontSize: '11px',
              padding: '3px 6px',
              background: useMcpDraft ? '#2d2d2d' : '#222',
              border: '1px solid #444',
              borderRadius: '3px',
              color: useMcpDraft ? '#ccc' : '#666',
              outline: 'none',
            }}
          />

          <label style={{ fontSize: '10px', color: useMcpDraft ? '#aaa' : '#555' }}>{t('chatPanel.apiKeyOptional')}</label>
          <input
            id="mcp-api-key-input"
            type="password"
            value={mcpApiKeyDraft}
            disabled={!useMcpDraft}
            onChange={e => { setMcpApiKeyDraft(e.target.value); setMcpTestStatus(''); }}
            placeholder={t('chatPanel.mcpApiKeyPlaceholder')}
            style={{
              fontSize: '11px',
              padding: '3px 6px',
              background: useMcpDraft ? '#2d2d2d' : '#222',
              border: '1px solid #444',
              borderRadius: '3px',
              color: useMcpDraft ? '#ccc' : '#666',
              outline: 'none',
            }}
          />

          <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginTop: '2px' }}>
            <button
              id="mcp-test-btn"
              onClick={handleTestMcp}
              disabled={!useMcpDraft || !mcpUrlDraft.trim() || mcpTestStatus === 'testing'}
              style={{
                fontSize: '10px',
                padding: '3px 8px',
                background: '#2d2d2d',
                border: '1px solid #555',
                borderRadius: '3px',
                color: (useMcpDraft && mcpUrlDraft.trim()) ? '#ccc' : '#555',
                cursor: (useMcpDraft && mcpUrlDraft.trim()) ? 'pointer' : 'not-allowed',
              }}
            >
              {mcpTestStatus === 'testing' ? '...' : t('chatPanel.test')}
            </button>
            <button
              id="mcp-save-btn"
              onClick={handleSaveMcp}
              style={{
                fontSize: '10px',
                padding: '3px 8px',
                background: '#0e639c',
                border: 'none',
                borderRadius: '3px',
                color: '#fff',
                cursor: 'pointer',
              }}
            >
              {t('chatPanel.save')}
            </button>
            <button
              onClick={() => { setShowMcpPanel(false); setMcpTestStatus(''); }}
              style={{
                fontSize: '10px',
                padding: '3px 6px',
                background: 'transparent',
                border: 'none',
                color: '#888',
                cursor: 'pointer',
              }}
            >
              {t('chatPanel.cancel')}
            </button>
          </div>

          {/* Test result */}
          {mcpTestStatus && mcpTestStatus !== 'testing' && (
            <div
              style={{
                fontSize: '10px',
                color: mcpTestStatus === 'ok' ? '#4ec9b0' : '#f48771',
                marginTop: '2px',
              }}
            >
              {mcpTestStatus === 'ok'
                ? t('chatPanel.connectionOk')
                : t('chatPanel.connectionError', { error: mcpTestStatus.replace('error:', '') })}
            </div>
          )}
        </div>
      )}

      {/* Message history */}
      <div className="vscode-chat-history" ref={historyRef} onContextMenu={onContextMenu}>
        {chatMessages.map((msg, i) => {
          const isUser = msg.role === 'user';
          return (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span
                className={`vscode-chat-msg-header ${isUser ? 'chat-header-user' : 'chat-header-agent'}`}
              >
                {isUser ? t('chatPanel.you') : t('chatPanel.opalacoder')}
              </span>
              <div className="vscode-chat-msg-content">
                {formatMessageContent(msg.content)}
              </div>
            </div>
          );
        })}

        {isAgentRunning && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span className="vscode-chat-msg-header chat-header-agent">{t('chatPanel.opalacoder')}</span>
            <div className="vscode-chat-msg-content">
              <div className="thinking-indicator">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input form */}
      <form onSubmit={handleFormSubmit} className="vscode-chat-form">
        <div className="vscode-chat-input-row">
          <input
            ref={inputRef}
            type="text"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!activeProject || isAgentRunning}
            placeholder={
              !activeProject ? t('chatPanel.setProjectFirst') :
              isAgentRunning ? t('chatPanel.thinking') :
              t('chatPanel.askOpalaCoder')
            }
            style={{ flex: 1 }}
          />
          {isAgentRunning ? (
            <button
              type="button"
              onClick={handleInterruptAgent}
              className="vscode-button"
              style={{ padding: '6px', backgroundColor: '#f48771', color: '#1e1e1e' }}
              title={t('chatPanel.interruptAgent')}
            >
              <X size={14} />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!activeProject || !chatInput.trim()}
              className="vscode-button"
              style={{ padding: '6px' }}
            >
              <ArrowRight size={14} />
            </button>
          )}
        </div>
      </form>
    </aside>
  );
}
