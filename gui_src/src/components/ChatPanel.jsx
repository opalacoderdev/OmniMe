import React from 'react';
import { MessageSquare, Cpu, HelpCircle, Check, X, ArrowRight, Eraser } from 'lucide-react';
import { formatMessageContent } from '../utils/formatMessage';

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
}) {
  if (!isChatVisible) return null;

  return (
    <aside className="vscode-chat" style={{ width: `${chatWidth}px` }}>
      {/* Header */}
      <div className="vscode-chat-header">
        <span className="vscode-sidebar-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <MessageSquare size={12} style={{ color: '#007acc' }} />
          <span>OPALA CHAT</span>
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={onClearChat}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
            title="Limpar chat (Varrer)"
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

      {/* Message history */}
      <div className="vscode-chat-history">
        {chatMessages.map((msg, i) => {
          const isUser = msg.role === 'user';
          return (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span
                className="vscode-chat-msg-header"
                style={{ color: isUser ? '#75beff' : '#da70d6' }}
              >
                {isUser ? 'VOCÊ' : 'OPALACODER'}
              </span>
              <div className="vscode-chat-msg-content">
                {formatMessageContent(msg.content)}
              </div>
            </div>
          );
        })}

        {isAgentRunning && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span className="vscode-chat-msg-header" style={{ color: '#da70d6' }}>OPALACODER</span>
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
      <form onSubmit={handleSendMessage} className="vscode-chat-form">
        <div className="vscode-chat-input-row">
          <input
            type="text"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            disabled={!activeProject || isAgentRunning}
            placeholder={
              !activeProject ? 'Defina um projeto...' :
              isAgentRunning ? 'Pensando...' :
              'Pergunte ao OpalaCoder...'
            }
            style={{ flex: 1 }}
          />
          {isAgentRunning ? (
            <button
              type="button"
              onClick={handleInterruptAgent}
              className="vscode-button"
              style={{ padding: '6px', backgroundColor: '#f48771', color: '#1e1e1e' }}
              title="Interromper agente"
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
