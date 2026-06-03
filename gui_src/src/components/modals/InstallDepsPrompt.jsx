import React from 'react';
import { X } from 'lucide-react';

// Startup prompt asking the user to install optional sentence-transformers dependencies.
export default function InstallDepsPrompt({ onClose, onInstall }) {
  return (
    <div className="vscode-modal-overlay">
      <div className="vscode-modal" style={{ maxWidth: '440px', width: '90%' }}>
        <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
          <span className="vscode-sidebar-title" style={{ color: '#ffffff' }}>MÓDULOS OPCIONAIS REQUERIDOS</span>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
          >
            <X size={14} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1" style={{ padding: '16px', color: '#cccccc', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <p style={{ fontSize: '13px', lineHeight: '1.5' }}>
            Os módulos opcionais para embeddings offline (<code>sentence-transformers</code>) não foram encontrados no ambiente.
          </p>
          <p style={{ fontSize: '12px', color: '#888888', lineHeight: '1.4' }}>
            Recomendamos a instalação para habilitar o processamento local de vetores e a indexação de código sem depender de APIs externas.
          </p>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px', borderTop: '1px solid #3c3c3c', paddingTop: '12px' }}>
            <button onClick={onClose} className="vscode-button" style={{ backgroundColor: '#3c3c3c', color: '#ffffff' }}>
              Ignorar
            </button>
            <button onClick={onInstall} className="vscode-button">
              Instalar Agora
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
