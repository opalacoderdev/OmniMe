import React from 'react';
import { Info } from 'lucide-react';

// Bottom status bar (VSCode-style footer).
export default function StatusBar({ activeProject, isAgentRunning }) {
  return (
    <footer className="vscode-statusbar">
      <div className="flex items-center" style={{ gap: '16px' }}>
        <div className="flex items-center" style={{ gap: '6px' }}>
          <Info size={11} />
          <span style={{ fontWeight: 'bold' }}>
            {activeProject
              ? `Workspace: ${activeProject.project_name || activeProject.name}`
              : 'Sem Workspace'}
          </span>
        </div>
        {isAgentRunning && (
          <span className="flex items-center" style={{ gap: '6px' }}>
            <span style={{ width: '6px', height: '6px', backgroundColor: '#ffffff', borderRadius: '50%', display: 'inline-block' }} />
            <span style={{ fontWeight: 'bold' }}>OpalaCoder Ativo...</span>
          </span>
        )}
      </div>

      <div className="flex items-center" style={{ gap: '12px' }}>
        <span>UTF-8</span>
        <span>LF</span>
        <span>JSON IPC Bridge</span>
      </div>
    </footer>
  );
}
