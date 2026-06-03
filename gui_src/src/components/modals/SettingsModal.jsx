import React from 'react';
import { X, Settings } from 'lucide-react';
import { safeSetLocalStorage } from '../../utils/storage';

// IDE global settings modal (theme, font size, tab size, word wrap, optional deps).
export default function SettingsModal({
  onClose,
  settingsTab,
  setSettingsTab,
  theme,
  setTheme,
  editorFontSize,
  setEditorFontSize,
  editorTabSize,
  setEditorTabSize,
  editorWordWrap,
  setEditorWordWrap,
  isInstallingDeps,
  installDepsStatus,
  installDepsLog,
  onInstallDeps,
}) {
  return (
    <div className="vscode-modal-overlay">
      <div className="vscode-modal" style={{ maxWidth: '440px', width: '90%' }}>
        {/* Header */}
        <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
          <span className="vscode-sidebar-title" style={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Settings size={14} style={{ color: '#007acc' }} />
            CONFIGURAÇÕES DA IDE
          </span>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}>
            <X size={14} />
          </button>
        </div>

        {/* Tab selector */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--vscode-border)', backgroundColor: 'var(--vscode-tab-inactive-bg)' }}>
          {['preferences', 'about'].map(tab => (
            <button
              key={tab}
              onClick={() => setSettingsTab(tab)}
              style={{
                flex: 1, padding: '8px',
                background: settingsTab === tab ? 'var(--vscode-tab-active-bg)' : 'transparent',
                border: 'none',
                borderBottom: settingsTab === tab ? '2px solid var(--vscode-active-border)' : 'none',
                color: settingsTab === tab ? '#ffffff' : '#808080',
                fontWeight: 'bold', fontSize: '11px', textTransform: 'uppercase', cursor: 'pointer',
              }}
            >
              {tab === 'preferences' ? 'Preferências' : 'Sobre'}
            </button>
          ))}
        </div>

        <div className="flex flex-col overflow-y-auto flex-1" style={{ padding: '16px', gap: '14px' }}>
          {settingsTab === 'preferences' ? (
            <>
              {/* Theme */}
              <div className="flex flex-col" style={{ gap: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Tema de Cor</label>
                <select value={theme} onChange={(e) => setTheme(e.target.value)} style={{ width: '100%' }}>
                  <option value="dark">Escuro (Dark Mode)</option>
                  <option value="light">Claro (Light Mode)</option>
                </select>
              </div>

              {/* Font size */}
              <div className="flex flex-col" style={{ gap: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Tamanho da Fonte do Editor</label>
                <input
                  type="number" min="10" max="30" value={editorFontSize}
                  onChange={(e) => { const val = Number(e.target.value); setEditorFontSize(val); safeSetLocalStorage('editorFontSize', val); }}
                  style={{ width: '100%' }}
                />
              </div>

              {/* Tab size */}
              <div className="flex flex-col" style={{ gap: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Tamanho do Tab (Espaços)</label>
                <select value={editorTabSize} onChange={(e) => { const val = Number(e.target.value); setEditorTabSize(val); safeSetLocalStorage('editorTabSize', val); }} style={{ width: '100%' }}>
                  <option value={2}>2 Espaços</option>
                  <option value={4}>4 Espaços</option>
                  <option value={8}>8 Espaços</option>
                </select>
              </div>

              {/* Word wrap */}
              <div className="flex flex-col" style={{ gap: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Quebra Automática de Linha (Word Wrap)</label>
                <select value={editorWordWrap} onChange={(e) => { setEditorWordWrap(e.target.value); safeSetLocalStorage('editorWordWrap', e.target.value); }} style={{ width: '100%' }}>
                  <option value="on">Ativado (On)</option>
                  <option value="off">Desativado (Off)</option>
                </select>
              </div>

              {/* Optional dependencies */}
              <div className="flex flex-col" style={{ gap: '6px', borderTop: '1px solid var(--vscode-border)', paddingTop: '12px', marginTop: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Dependências Opcionais</label>
                <span style={{ fontSize: '11px', color: '#888888', lineHeight: '1.4' }}>
                  Instale recursos extras (Local Embeddings, PyTorch, CUDA, etc.) que otimizam o processamento off-line.
                </span>
                <button type="button" className="vscode-button" disabled={isInstallingDeps} onClick={onInstallDeps} style={{ width: '100%', marginTop: '6px' }}>
                  {isInstallingDeps ? 'Instalando...' : 'Instalar Recursos Opcionais'}
                </button>
                {installDepsStatus && (
                  <span style={{ fontSize: '11px', fontWeight: 'bold', color: installDepsStatus.includes('Erro') || installDepsStatus.includes('Falha') ? '#f48771' : '#73c991', marginTop: '4px' }}>
                    Status: {installDepsStatus}
                  </span>
                )}
                {installDepsLog && (
                  <textarea readOnly value={installDepsLog} style={{ width: '100%', height: '80px', marginTop: '8px', fontSize: '10px', fontFamily: 'monospace', background: '#151515', color: '#89d4a5', border: '1px solid var(--vscode-border)', padding: '6px', resize: 'none' }} />
                )}
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', color: '#cccccc' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span className="vscode-sidebar-section-title" style={{ padding: 0 }}>Versão</span>
                <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#ffffff' }}>0.1.26 alfa</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span className="vscode-sidebar-section-title" style={{ padding: 0 }}>Autor</span>
                <span style={{ fontSize: '13px', color: '#ffffff' }}>dev@opala.com</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span className="vscode-sidebar-section-title" style={{ padding: 0 }}>Licença</span>
                <span style={{ fontSize: '13px', color: '#ffffff' }}>MIT</span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '12px 16px', gap: '8px', borderTop: '1px solid var(--vscode-border)', backgroundColor: 'var(--vscode-sidebar-bg)' }}>
          <button onClick={onClose} className="vscode-button">Fechar</button>
        </div>
      </div>
    </div>
  );
}
