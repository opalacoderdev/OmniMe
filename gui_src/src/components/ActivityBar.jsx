import React from 'react';
import { Files, GitBranch, MessageSquare, Settings } from 'lucide-react';

// Left-side vertical activity bar (VSCode-style icon strip).
export default function ActivityBar({
  activeSidebarTab,
  setActiveSidebarTab,
  isChatVisible,
  setIsChatVisible,
  gitChangesCount,
  onOpenSettings,
}) {
  return (
    <div className="vscode-activitybar">
      <div className="vscode-activitybar-top">
        <button
          onClick={() => setActiveSidebarTab('explorer')}
          className={`vscode-activitybar-btn ${activeSidebarTab === 'explorer' ? 'active' : ''}`}
          title="Explorer"
        >
          <Files size={22} />
        </button>

        <button
          onClick={() => setActiveSidebarTab('git')}
          className={`vscode-activitybar-btn ${activeSidebarTab === 'git' ? 'active' : ''}`}
          title="Source Control"
          style={{ position: 'relative' }}
        >
          <GitBranch size={22} />
          {gitChangesCount > 0 && (
            <span style={{
              position: 'absolute',
              top: '4px',
              right: '4px',
              background: '#007acc',
              color: '#ffffff',
              borderRadius: '50%',
              width: '16px',
              height: '16px',
              fontSize: '9px',
              fontWeight: 'bold',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 4px rgba(0,0,0,0.5)',
            }}>
              {gitChangesCount}
            </span>
          )}
        </button>

        <button
          onClick={() => setIsChatVisible(!isChatVisible)}
          className={`vscode-activitybar-btn ${isChatVisible ? 'active' : ''}`}
          title="Opala Chat"
        >
          <MessageSquare size={22} />
        </button>
      </div>

      <div>
        <button
          onClick={onOpenSettings}
          className="vscode-activitybar-btn"
          title="Settings"
        >
          <Settings size={20} />
        </button>
      </div>
    </div>
  );
}
