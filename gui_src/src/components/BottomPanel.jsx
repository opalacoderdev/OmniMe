import { useRef } from 'react';
import { AlertCircle, Trash, Maximize2, Minimize2, ChevronUp, ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useTextContextMenu } from '../hooks/useTextContextMenu.js';
import TextContextMenu from './TextContextMenu.jsx';

// Bottom panel with Output / Problems / Thinking / Terminal tabs.
export default function BottomPanel({
  activeBottomTab,
  setActiveBottomTab,
  isTerminalCollapsed,
  setIsTerminalCollapsed,
  terminalLogs,
  setTerminalLogs,
  problems,
  setProblems,
  thinkingLogs,
  setThinkingLogs,
  bottomPanelHeight,
  activeProject,
  terminalRef,
  terminalInstanceRef,
  logEndRef,
  startResizing,
  isBottomMaximized,
  onToggleMaximizeBottom,
}) {
  const { t } = useTranslation();
  const contentRef = useRef(null);
  const { menu, onContextMenu, handleCopy, handlePaste, handleSelectAll } = useTextContextMenu();

  const selectTab = (tab) => {
    setActiveBottomTab(tab);
    if (isTerminalCollapsed) setIsTerminalCollapsed(false);
  };

  const clearTitle = activeBottomTab === 'output'
    ? t('bottomPanel.clearOutput')
    : activeBottomTab === 'problems'
      ? t('bottomPanel.clearProblems')
      : t('bottomPanel.clearThinking');

  return (
    <>
      <TextContextMenu
        menu={menu}
        onCopy={handleCopy}
        onPaste={handlePaste}
        onSelectAll={
          activeBottomTab === 'terminal'
            ? () => {
                const term = terminalInstanceRef?.current;
                close();
                if (term) {
                  term.selectAll();
                  setTimeout(() => term.focus(), 50);
                }
              }
            : () => handleSelectAll(contentRef)
        }
      />
      {/* Vertical resize handle */}
      {!isTerminalCollapsed && !isBottomMaximized && (
        <div
          className="vscode-resizer-vertical"
          onMouseDown={(e) => startResizing(e, 'bottom')}
        />
      )}

      <div
        className="vscode-bottom-panel"
        style={{ height: isTerminalCollapsed ? '30px' : isBottomMaximized ? '100%' : `${bottomPanelHeight}px` }}
      >
        {/* Tab header */}
        <div className="vscode-bottom-tabs">
          <div className="vscode-bottom-tab-list">
            {['output', 'problems', 'thinking', 'terminal'].map((tab) => (
              <span
                key={tab}
                className={`vscode-bottom-tab ${activeBottomTab === tab ? 'active' : ''}`}
                onClick={() => selectTab(tab)}
              >
                {tab === 'output' && t('bottomPanel.outputTab')}
                {tab === 'problems' && (
                  <>
                    {t('bottomPanel.problemsTab')}{' '}
                    {problems.length > 0 && (
                      <span style={{ marginLeft: '4px', background: '#f48771', color: '#1e1e1e', borderRadius: '10px', padding: '0 6px', fontSize: '10px', fontWeight: 'bold' }}>
                        {problems.length}
                      </span>
                    )}
                  </>
                )}
                {tab === 'thinking' && t('bottomPanel.thinkingTab')}
                {tab === 'terminal' && t('bottomPanel.terminalTab')}
              </span>
            ))}
          </div>

          <div className="flex items-center" style={{ gap: '8px' }}>
            {(activeBottomTab === 'output' || activeBottomTab === 'problems' || activeBottomTab === 'thinking') && (
              <button
                onClick={
                  activeBottomTab === 'output'
                    ? () => setTerminalLogs([])
                    : activeBottomTab === 'problems'
                      ? () => setProblems([])
                      : () => setThinkingLogs([])
                }
                className="vscode-bottom-panel-clear-btn"
                title={clearTitle}
              >
                <Trash size={12} />
                <span>{t('bottomPanel.clear')}</span>
              </button>
            )}
            <button
              onClick={() => {
                if (isBottomMaximized) onToggleMaximizeBottom();
                setIsTerminalCollapsed(!isTerminalCollapsed);
              }}
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
              title={isTerminalCollapsed ? t('bottomPanel.expandPanel') : t('bottomPanel.collapsePanel')}
            >
              {isTerminalCollapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {!isTerminalCollapsed && (
              <button
                onClick={onToggleMaximizeBottom}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
                title={isBottomMaximized ? t('bottomPanel.restorePanel') : t('bottomPanel.maximizePanel')}
              >
                {isBottomMaximized ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
              </button>
            )}
          </div>
        </div>

        {/* Panel content — always mounted so xterm is never destroyed on collapse */}
        <div
          ref={contentRef}
          style={{ display: isTerminalCollapsed ? 'none' : 'block', height: 'calc(100% - 30px)', width: '100%' }}
          onContextMenu={onContextMenu}
        >

            {/* Output tab */}
            {activeBottomTab === 'output' && (
              <div className="vscode-logs" style={{ height: '100%' }}>
                {terminalLogs.length === 0 ? (
                  <div style={{ color: '#808080', fontStyle: 'italic' }}>
                    {t('bottomPanel.noLogs')}
                  </div>
                ) : (
                  terminalLogs.map((log, i) => {
                    let color = 'text-[#cccccc]';
                    let label = 'SYSTEM';

                    if (log.type === 'error') { color = 'text-[#f48771] font-semibold'; label = 'ERROR'; }
                    else if (log.type === 'info') { color = 'text-[#75beff]'; label = 'INFO'; }
                    else if (log.type === 'thought') { color = 'text-[#da70d6] italic'; label = 'THOUGHT'; }
                    else if (log.type === 'tool_call') { color = 'text-[#d7ba7d]'; label = 'TOOL'; }
                    else if (log.type === 'tool_result') { color = 'text-[#89d4a5]'; label = 'RESULT'; }

                    return (
                      <div key={i} className={color} style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', marginBottom: '3px' }}>
                        <span style={{ color: '#5a5a5a' }}>[{log.timestamp}]</span>
                        <span style={{ fontWeight: 'bold' }}>[{label}]</span>
                        <span style={{ whiteSpace: 'pre-wrap', flex: 1 }}>{log.message}</span>
                      </div>
                    );
                  })
                )}
                <div ref={logEndRef} />
              </div>
            )}

            {/* Problems tab */}
            {activeBottomTab === 'problems' && (
              <div className="vscode-problems-list" style={{ padding: '8px', overflowY: 'auto', height: '100%', color: '#cccccc', fontFamily: 'Consolas, monospace', fontSize: '12px' }}>
                {problems.length === 0 ? (
                  <div style={{ color: '#808080', fontStyle: 'italic', padding: '8px' }}>{t('bottomPanel.noProblems')}</div>
                ) : (
                  problems.map((prob) => (
                    <div key={prob.id} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', borderBottom: '1px solid #2d2d2d', padding: '6px 0' }}>
                      <AlertCircle size={14} className="text-[#f48771]" style={{ flexShrink: 0, marginTop: '2px' }} />
                      <div>
                        <div style={{ fontWeight: 'bold', color: '#f48771', marginBottom: '2px' }}>
                          [{prob.timestamp}] {t('bottomPanel.errorIn', { tool: prob.tool })}
                        </div>
                        <pre style={{ whiteSpace: 'pre-wrap', margin: 0, color: '#e0e0e0', fontSize: '12px', fontFamily: 'inherit' }}>
                          {prob.message}
                        </pre>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Thinking tab */}
            {activeBottomTab === 'thinking' && (
              <div className="vscode-logs" style={{ height: '100%' }}>
                {thinkingLogs.length === 0 ? (
                  <div style={{ color: '#808080', fontStyle: 'italic' }}>
                    {t('bottomPanel.noThinking')}
                  </div>
                ) : (
                  thinkingLogs.map((log, i) => {
                    const isReflection = log.type === 'REFLECTION';
                    return (
                      <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', marginBottom: '4px' }}>
                        <span style={{ color: '#5a5a5a', flexShrink: 0 }}>[{log.timestamp}]</span>
                        <span style={{ fontWeight: 'bold', flexShrink: 0, color: isReflection ? '#4ec9b0' : '#da70d6' }}>
                          [{log.type || 'THINKING'}]
                        </span>
                        <span style={{ whiteSpace: 'pre-wrap', flex: 1, fontFamily: 'Consolas, monospace', color: isReflection ? '#4ec9b0' : '#da70d6' }}>
                          {log.content}
                        </span>
                      </div>
                    );
                  })
                )}
              </div>
            )}

            {/* Terminal tab */}
            <div style={{ display: activeBottomTab === 'terminal' ? 'block' : 'none', height: '100%', background: '#1e1e1e', overflow: 'hidden' }}>
              {!activeProject ? (
                <div style={{ color: '#808080', fontStyle: 'italic', padding: '16px' }}>
                  {t('bottomPanel.setProjectForTerminal')}
                </div>
              ) : (
                <div ref={terminalRef} style={{ width: '100%', height: '100%', padding: '4px' }} />
              )}
            </div>
          </div>
      </div>
    </>
  );
}
