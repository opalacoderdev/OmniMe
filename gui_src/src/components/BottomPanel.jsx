import React from 'react';
import { AlertCircle, Trash, Maximize2, Minimize2, ChevronUp, ChevronDown } from 'lucide-react';

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
  logEndRef,
  startResizing,
  isBottomMaximized,
  onToggleMaximizeBottom,
}) {
  const selectTab = (tab) => {
    setActiveBottomTab(tab);
    if (isTerminalCollapsed) setIsTerminalCollapsed(false);
  };

  return (
    <>
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
                {tab === 'output' && 'OUTPUT (OPALACODER)'}
                {tab === 'problems' && (
                  <>
                    PROBLEMS{' '}
                    {problems.length > 0 && (
                      <span style={{ marginLeft: '4px', background: '#f48771', color: '#1e1e1e', borderRadius: '10px', padding: '0 6px', fontSize: '10px', fontWeight: 'bold' }}>
                        {problems.length}
                      </span>
                    )}
                  </>
                )}
                {tab === 'thinking' && 'THINKING'}
                {tab === 'terminal' && 'TERMINAL'}
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
                title={
                  activeBottomTab === 'output'
                    ? 'Limpar Output'
                    : activeBottomTab === 'problems'
                      ? 'Limpar Problemas'
                      : 'Limpar Pensamentos'
                }
              >
                <Trash size={12} />
                <span>Clear</span>
              </button>
            )}
            <button
              onClick={() => {
                if (isBottomMaximized) onToggleMaximizeBottom();
                setIsTerminalCollapsed(!isTerminalCollapsed);
              }}
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
              title={isTerminalCollapsed ? "Expandir Painel" : "Recolher Painel"}
            >
              {isTerminalCollapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {!isTerminalCollapsed && (
              <button
                onClick={onToggleMaximizeBottom}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
                title={isBottomMaximized ? "Restaurar Painel" : "Maximizar Painel"}
              >
                {isBottomMaximized ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
              </button>
            )}
          </div>
        </div>

        {/* Panel content */}
        {!isTerminalCollapsed && (
          <div style={{ height: 'calc(100% - 30px)', width: '100%' }}>

            {/* Output tab */}
            {activeBottomTab === 'output' && (
              <div className="vscode-logs" style={{ height: '100%' }}>
                {terminalLogs.length === 0 ? (
                  <div style={{ color: '#808080', fontStyle: 'italic' }}>
                    Nenhum log gerado. Envie uma instrução no chat para iniciar...
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
                  <div style={{ color: '#808080', fontStyle: 'italic', padding: '8px' }}>Nenhum problema detectado.</div>
                ) : (
                  problems.map((prob) => (
                    <div key={prob.id} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', borderBottom: '1px solid #2d2d2d', padding: '6px 0' }}>
                      <AlertCircle size={14} className="text-[#f48771]" style={{ flexShrink: 0, marginTop: '2px' }} />
                      <div>
                        <div style={{ fontWeight: 'bold', color: '#f48771', marginBottom: '2px' }}>
                          [{prob.timestamp}] Erro em {prob.tool}:
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
                    Nenhum pensamento gerado ainda. Execute uma instrução para ver o raciocínio do agente...
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
                  Defina um projeto/workspace para habilitar o terminal.
                </div>
              ) : (
                <div ref={terminalRef} style={{ width: '100%', height: '100%', padding: '4px' }} />
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
