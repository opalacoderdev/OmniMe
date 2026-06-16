import { useRef, useState, useCallback, useLayoutEffect } from 'react';
import { MessageSquare, Cpu, HelpCircle, Check, X, ArrowRight, Eraser, Globe, Settings, Plus, Trash2, Search, Paperclip, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { formatMessageContent } from '../utils/formatMessage';
import { readClipboard } from '../utils/clipboard.js';
import { useTextContextMenu } from '../hooks/useTextContextMenu.js';
import TextContextMenu from './TextContextMenu.jsx';
import SearchChatsModal from './modals/SearchChatsModal.jsx';

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
  activeChatId,
  setActiveChatId,
  chats,
  setChats,
  setChatMessages,
  pendingAttachments,
  setPendingAttachments,
}) {
  const { t } = useTranslation();
  const historyRef = useRef(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const { menu, onContextMenu, handleCopy, handleSelectAll, close: closeMenu } = useTextContextMenu();

  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, [chatInput]);

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

  // Custom prompt state for new chat
  const [showNewChatPrompt, setShowNewChatPrompt] = useState(false);
  const [newChatName, setNewChatName] = useState('');
  const [showSearchModal, setShowSearchModal] = useState(false);

  // Custom confirm state for deleting chat
  const [chatToDelete, setChatToDelete] = useState(null);

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
    if ((!chatInput.trim() && (!pendingAttachments || pendingAttachments.length === 0)) || !activeProject || isAgentRunning) return;
    const text = chatInput.trim();
    if (text) {
      setInputHistory(prev => {
        if (prev[prev.length - 1] === text) return prev;
        const newHist = [...prev, text].slice(-100);
        try {
          localStorage.setItem('chatInputHistory', JSON.stringify(newHist));
        } catch (_) {}
        return newHist;
      });
    }
    setHistoryIndex(-1);
    setTempInput('');
    handleSendMessage(e);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleFormSubmit(null);
    } else if (e.key === 'ArrowUp') {
      const el = e.currentTarget;
      const onFirstLine = el.selectionStart === 0 || !el.value.slice(0, el.selectionStart).includes('\n');
      if (!onFirstLine || inputHistory.length === 0) return;
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
      const el = e.currentTarget;
      const onLastLine = el.selectionEnd === el.value.length || !el.value.slice(el.selectionEnd).includes('\n');
      if (!onLastLine || historyIndex === -1) return;
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

  // ---- Attachment helpers ----
  const uploadFile = async (file) => {
    const reader = new FileReader();
    return new Promise((resolve, reject) => {
      reader.onload = async (ev) => {
        const dataUrl = ev.target.result;
        const base64 = dataUrl.split(',')[1];
        try {
          const res = await fetch('/api/chat/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              filename: file.name,
              data_b64: base64,
              mime: file.type || 'application/octet-stream',
              project_name: activeProject?.name,
            }),
          });
          if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
          const descriptor = await res.json();
          // keep original data URL for image preview in the UI
          descriptor._previewUrl = file.type?.startsWith('image/') ? dataUrl : null;
          resolve(descriptor);
        } catch (err) {
          reject(err);
        }
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  const processFiles = async (files) => {
    if (!files || files.length === 0) return;
    setUploadingFiles(true);
    const results = [];
    for (const f of Array.from(files)) {
      const mime = f.type || '';
      if (!mime.startsWith('image/') && mime !== 'application/pdf') continue;
      try {
        const desc = await uploadFile(f);
        results.push(desc);
      } catch (err) {
        console.error('Attachment upload failed:', err);
      }
    }
    setPendingAttachments(prev => [...(prev || []), ...results]);
    setUploadingFiles(false);
  };

  const removeAttachment = (idx) => {
    setPendingAttachments(prev => prev.filter((_, i) => i !== idx));
  };

  const handleFileInputChange = (e) => {
    processFiles(e.target.files);
    e.target.value = '';
  };

  const handleDragOver = (e) => { e.preventDefault(); setIsDragOver(true); };
  const handleDragLeave = () => setIsDragOver(false);
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    processFiles(e.dataTransfer.files);
  };

  const handleCreateChatClick = () => {
    if (!activeProject) return;
    setNewChatName(`Chat ${chats.length + 1}`);
    setShowNewChatPrompt(true);
  };

  const submitNewChat = async (e) => {
    e?.preventDefault();
    if (!activeProject || !newChatName.trim()) return;

    try {
      const res = await fetch('/api/chat/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: activeProject.name, chat_name: newChatName.trim() })
      });
      if (!res.ok) throw new Error('Failed to create chat');
      const data = await res.json();
      setChats(prev => [...prev, data]);
      setActiveChatId(data.id);
      
      const greeting = activeProject.project_name || activeProject.name;
      setChatMessages([{ role: 'assistant', content: t('app.greeting', { projectName: greeting }) }]);
      setShowNewChatPrompt(false);
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateChat = async () => {
    // Legacy fallback, replaced by handleCreateChatClick
  };

  const handleDeleteChatClick = (id, e) => {
    e.stopPropagation();
    if (!activeProject || id === 'main') return;
    setChatToDelete(id);
  };

  const confirmDeleteChat = async () => {
    if (!activeProject || !chatToDelete || chatToDelete === 'main') return;
    const id = chatToDelete;
    
    try {
      const res = await fetch('/api/chat/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: activeProject.name, chat_id: id })
      });
      if (!res.ok) throw new Error('Failed to delete chat');
      const newChats = chats.filter(c => c.id !== id);
      setChats(newChats);
      if (activeChatId === id) {
        // Switch to main if we deleted the current one
        setActiveChatId('main');
        handleSwitchChat('main', newChats);
      }
      setChatToDelete(null);
    } catch (err) {
      console.error(err);
      setChatToDelete(null);
    }
  };

  const handleSwitchChat = async (id, currentChats = chats) => {
    if (!activeProject || id === activeChatId) return;
    setActiveChatId(id);
    
    // We must load the project's history for this chat
    try {
      // Actually, we could just rely on App.jsx handling it, but App.jsx doesn't refetch on activeChatId change.
      // So let's re-fetch the project or have a dedicated endpoint for chat history.
      // Easiest is to simulate /api/opalacoder/run with a "load_chat" command, but we don't have that.
      // Let's call a minimal endpoint or we can just send `/api/opalacoder/list-projects` again and find ours? No, list-projects doesn't load chat history.
      // A quick hack: dispatch a slash command or do a dummy request? No, wait. App.jsx passes down `chats` but not full project data per chat.
      // Let's add `/api/chat/history` or fetch the project. 
      // Actually we can just update `activeProject` in App by calling an endpoint, but we don't have an endpoint just for fetching a project with a specific chat_id. Wait! UpdateProject doesn't return history.
      // Wait, let me add `/api/chat/history` in `ide_server.py`. I will add it right now.
      const res = await fetch(`/api/chat/history?project_name=${encodeURIComponent(activeProject.name)}&chat_id=${encodeURIComponent(id)}&t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        const greeting = activeProject.project_name || activeProject.name;
        if (data.history && data.history.length > 0) {
          setChatMessages(data.history);
        } else {
          setChatMessages([{ role: 'assistant', content: t('app.greeting', { projectName: greeting }) }]);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

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
      
      {/* Chat Selector Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 10px', borderBottom: '1px solid var(--border-color, #333)', background: 'var(--sidebar-bg, #1e1e1e)', minHeight: '28px', gap: '6px' }}>
        <select 
          className="vscode-settings-input" 
          value={activeChatId} 
          onChange={(e) => handleSwitchChat(e.target.value)}
          style={{ flex: 1, padding: '2px 4px', fontSize: '11px', height: '22px' }}
        >
          {chats.map(c => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <div style={{ display: 'flex', gap: '4px' }}>
          <button onClick={() => setShowSearchModal(true)} title={t('chat.searchChats', 'Search Chats')} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0', display: 'flex', alignItems: 'center', padding: '2px' }}>
            <Search size={14} />
          </button>
          <button onClick={handleCreateChatClick} title="Novo Chat" style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#4ec9b0', display: 'flex', alignItems: 'center', padding: '2px' }}>
            <Plus size={14} />
          </button>
          {activeChatId !== 'main' && (
            <button onClick={(e) => handleDeleteChatClick(activeChatId, e)} title="Deletar Chat Atual" style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#f87171', display: 'flex', alignItems: 'center', padding: '2px' }}>
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {chatToDelete && (
        <div style={{ padding: '8px', borderBottom: '1px solid var(--border-color, #333)', background: 'var(--sidebar-bg, #1e1e1e)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <span style={{ fontSize: '11px', color: '#ccc' }}>Deletar este chat e todo o seu histórico?</span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button onClick={confirmDeleteChat} className="vscode-button" style={{ height: '24px', padding: '0 8px', fontSize: '11px', background: '#f87171', color: '#fff', border: 'none' }}>
              Deletar
            </button>
            <button onClick={() => setChatToDelete(null)} className="vscode-button" style={{ height: '24px', padding: '0 8px', fontSize: '11px', background: 'transparent', color: '#ccc', border: '1px solid #555' }}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      {showSearchModal && (
        <SearchChatsModal
          onClose={() => setShowSearchModal(false)}
          activeProject={activeProject?.name}
          onSwitchChat={handleSwitchChat}
        />
      )}

      {showNewChatPrompt && (
        <div style={{ padding: '8px', borderBottom: '1px solid var(--border-color, #333)', background: 'var(--sidebar-bg, #1e1e1e)' }}>
          <form onSubmit={submitNewChat} style={{ display: 'flex', gap: '6px' }}>
            <input 
              autoFocus
              className="vscode-settings-input"
              value={newChatName}
              onChange={e => setNewChatName(e.target.value)}
              placeholder="Nome do chat"
              style={{ flex: 1, height: '24px', fontSize: '11px' }}
            />
            <button type="submit" className="vscode-button" style={{ height: '24px', padding: '0 8px', fontSize: '11px' }}>
              Criar
            </button>
            <button type="button" onClick={() => setShowNewChatPrompt(false)} className="vscode-button" style={{ height: '24px', padding: '0 8px', fontSize: '11px', background: 'transparent', color: '#ccc', border: '1px solid #555' }}>
              Cancelar
            </button>
          </form>
        </div>
      )}

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
          const atts = msg._attachments || [];
          return (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span
                className={`vscode-chat-msg-header ${isUser ? 'chat-header-user' : 'chat-header-agent'}`}
              >
                {isUser ? t('chatPanel.you') : t('chatPanel.opalacoder')}
              </span>
              {/* Attachment previews */}
              {atts.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', margin: '2px 0' }}>
                  {atts.map((att, ai) => (
                    <div key={ai} style={{
                      display: 'flex', alignItems: 'center', gap: '4px',
                      background: '#2d2d2d', borderRadius: '4px', padding: '3px 7px',
                      fontSize: '11px', color: '#aaa',
                    }}>
                      {att._previewUrl
                        ? <img src={att._previewUrl} alt={att.name} style={{ height: '40px', borderRadius: '3px', objectFit: 'cover' }} />
                        : <FileText size={14} style={{ color: '#4ec9b0' }} />}
                      <span>{att.name}</span>
                    </div>
                  ))}
                </div>
              )}
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
      <form
        onSubmit={handleFormSubmit}
        className="vscode-chat-form"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={isDragOver ? { outline: '2px dashed #4ec9b0', outlineOffset: '-2px' } : {}}
      >
        {/* Pending attachment preview strip */}
        {pendingAttachments && pendingAttachments.length > 0 && (
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: '6px',
            padding: '6px 10px', borderBottom: '1px solid #2d2d2d',
          }}>
            {pendingAttachments.map((att, idx) => (
              <div key={idx} style={{
                display: 'flex', alignItems: 'center', gap: '4px',
                background: '#2a2a2a', border: '1px solid #3d3d3d',
                borderRadius: '4px', padding: '3px 6px', fontSize: '11px', color: '#ccc',
              }}>
                {att._previewUrl
                  ? <img src={att._previewUrl} alt={att.name} style={{ height: '32px', borderRadius: '2px', objectFit: 'cover' }} />
                  : <FileText size={13} style={{ color: '#4ec9b0' }} />}
                <span style={{ maxWidth: '100px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{att.name}</span>
                <button
                  type="button"
                  onClick={() => removeAttachment(idx)}
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#888', padding: '0 2px', lineHeight: 1 }}
                >
                  <X size={11} />
                </button>
              </div>
            ))}
          </div>
        )}
        {/* Upload status */}
        {uploadingFiles && (
          <div style={{ padding: '4px 10px', fontSize: '11px', color: '#888' }}>
            {t('chatPanel.uploadingFiles', 'Processing attachment...')}
          </div>
        )}
        <div className="vscode-chat-input-row">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,application/pdf"
            multiple
            style={{ display: 'none' }}
            onChange={handleFileInputChange}
            id="chat-file-input"
          />
          {/* Paperclip button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={!activeProject || isAgentRunning}
            title={t('chatPanel.attachFile', 'Attach image or PDF')}
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: (pendingAttachments && pendingAttachments.length > 0) ? '#4ec9b0' : '#666',
              padding: '4px', display: 'flex', alignItems: 'center',
            }}
          >
            <Paperclip size={15} />
          </button>
          <textarea
            ref={inputRef}
            rows={1}
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!activeProject || isAgentRunning}
            placeholder={
              !activeProject ? t('chatPanel.setProjectFirst') :
              isAgentRunning ? t('chatPanel.thinking') :
              t('chatPanel.askOpalaCoder')
            }
            className="vscode-chat-textarea"
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
              disabled={!activeProject || (!chatInput.trim() && (!pendingAttachments || pendingAttachments.length === 0))}
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
