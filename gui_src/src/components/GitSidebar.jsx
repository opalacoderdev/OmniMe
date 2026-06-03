import React from 'react';

// Left sidebar — Source Control (Git) tab: commit form + changed files list.
export default function GitSidebar({
  activeProject,
  gitChanges,
  commitMessage,
  setCommitMessage,
  isCommitting,
  handleGitCommit,
}) {
  return (
    <div className="vscode-sidebar-content" style={{ padding: '12px', display: 'flex', flexDirection: 'column', height: '100%', gap: '16px' }}>
      <div className="vscode-sidebar-title">SOURCE CONTROL (GIT)</div>

      {!activeProject ? (
        <div style={{ fontSize: '12px', color: '#808080', fontStyle: 'italic' }}>
          Selecione um projeto para ver as alterações Git.
        </div>
      ) : gitChanges.length === 0 ? (
        <div style={{ fontSize: '12px', color: '#808080', fontStyle: 'italic' }}>
          Sem alterações locais.
        </div>
      ) : (
        <div className="flex flex-col flex-1 overflow-hidden" style={{ gap: '16px' }}>
          {/* Commit form */}
          <form onSubmit={handleGitCommit} className="flex flex-col" style={{ gap: '8px' }}>
            <input
              type="text"
              placeholder="Mensagem do Commit..."
              value={commitMessage}
              onChange={(e) => setCommitMessage(e.target.value)}
              required
              style={{ width: '100%', fontSize: '12px' }}
            />
            <button
              type="submit"
              className="vscode-button"
              disabled={isCommitting || !commitMessage.trim()}
              style={{ width: '100%' }}
            >
              {isCommitting ? 'Commit...' : 'Commit'}
            </button>
          </form>

          {/* Changed files */}
          <div className="flex-1 overflow-y-auto" style={{ borderTop: '1px solid var(--vscode-border)', paddingTop: '12px' }}>
            <div className="vscode-sidebar-section-title" style={{ marginBottom: '8px', padding: 0 }}>
              Modificações ({gitChanges.length})
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {gitChanges.map((change, i) => {
                let statusColor = '#cccccc';
                let statusLabel = change.status;

                if (change.status === 'M') { statusColor = '#e2b52b'; statusLabel = 'M'; }
                else if (change.status === '??' || change.status === 'A') { statusColor = '#73c991'; statusLabel = 'U'; }
                else if (change.status === 'D') { statusColor = '#f48771'; statusLabel = 'D'; }

                return (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      fontSize: '12px',
                      padding: '4px 6px',
                      borderRadius: '3px',
                      background: 'rgba(255,255,255,0.02)',
                    }}
                  >
                    <span className="truncate" title={change.path} style={{ color: '#cccccc', flex: 1, marginRight: '8px' }}>
                      {change.path}
                    </span>
                    <span style={{ fontWeight: 'bold', color: statusColor, fontSize: '11px', minWidth: '12px', textAlign: 'center' }}>
                      {statusLabel}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
