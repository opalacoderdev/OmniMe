import React from 'react';
import { X, FolderOpen } from 'lucide-react';

// Modal for registering a new project.
export default function NewProjectModal({
  onClose,
  onSubmit,
  newProjName, setNewProjName,
  newProjPath, setNewProjPath,
  newProjDesc, setNewProjDesc,
  newProjModel, setNewProjModel,
  newProjMode, setNewProjMode,
  newProjApiKey, setNewProjApiKey,
  newProjApiBase, setNewProjApiBase,
  newProjError,
  modelConfigMsg,
  onLoadModelConfig,
  onOpenDirPicker,
}) {
  return (
    <div className="vscode-modal-overlay">
      <div className="vscode-modal">
        <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
          <span className="vscode-sidebar-title" style={{ color: '#ffffff' }}>REGISTRAR NOVO PROJETO</span>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}>
            <X size={14} />
          </button>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col overflow-y-auto flex-1" style={{ padding: '16px', gap: '12px' }}>
          {/* Project name */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Nome do Projeto *</label>
            <input
              type="text"
              value={newProjName}
              onChange={(e) => setNewProjName(e.target.value)}
              placeholder="Ex: Meu Servidor Web"
              required
            />
          </div>

          {/* Project path */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Caminho Absoluto *</label>
            <div style={{ display: 'flex', gap: '6px' }}>
              <input
                type="text"
                value={newProjPath}
                onChange={(e) => setNewProjPath(e.target.value)}
                placeholder="Ex: /home/gilzamir/projetos/meu-app"
                required
                style={{ flex: 1 }}
              />
              <button type="button" className="vscode-button" style={{ padding: '4px 8px', whiteSpace: 'nowrap' }}
                onClick={() => onOpenDirPicker('new', newProjPath || '~')}>
                <FolderOpen size={14} />
              </button>
            </div>
          </div>

          {/* Description */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Descrição</label>
            <textarea
              value={newProjDesc}
              onChange={(e) => setNewProjDesc(e.target.value)}
              placeholder="Descritivo do projeto..."
              rows={2}
              style={{ resize: 'none' }}
            />
          </div>

          {/* API credentials */}
          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Chave de API (Opcional)</label>
              <input type="password" value={newProjApiKey} onChange={(e) => setNewProjApiKey(e.target.value)} placeholder="Ex: sk-..." />
            </div>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>URL Base da API (Opcional)</label>
              <input type="text" value={newProjApiBase} onChange={(e) => setNewProjApiBase(e.target.value)} placeholder="Ex: http://localhost:11434/v1" />
            </div>
          </div>

          <div style={{ fontSize: '11px', color: '#808080', marginTop: '-6px', lineHeight: '1.4' }}>
            Dica: Para usar o Ollama local com <strong>ollama/ministral-3:14b</strong>, informe a URL Base acima e selecione o modelo correspondente.
          </div>

          {/* Model + mode */}
          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Modelo de IA</label>
              <input
                type="text"
                list="default-models"
                value={newProjModel}
                onChange={(e) => setNewProjModel(e.target.value)}
                placeholder="Selecione ou digite o modelo"
              />
              <datalist id="default-models">
                <option value="gemini/gemini-2.5-flash" />
                <option value="gemini/gemini-2.5-pro" />
                <option value="openai/gpt-4o" />
                <option value="ollama/ministral-3:14b" />
              </datalist>
            </div>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Modo de Execução</label>
              <select value={newProjMode} onChange={(e) => setNewProjMode(e.target.value)}>
                <option value="auto">Auto (Completo)</option>
                <option value="plan">Plan (Planejar)</option>
                <option value="edit">Edit (Editar)</option>
              </select>
            </div>
          </div>

          {/* Load refined config */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <button type="button" className="vscode-button" style={{ background: '#3c3c3c', fontSize: '12px' }} onClick={onLoadModelConfig}>
              Load Refined Config
            </button>
            {modelConfigMsg && (
              <span style={{ fontSize: '11px', color: modelConfigMsg.startsWith('✅') ? '#4ec9b0' : '#f48771' }}>
                {modelConfigMsg}
              </span>
            )}
          </div>

          {newProjError && (
            <div style={{ color: '#f48771', fontSize: '11px', marginTop: '4px', whiteSpace: 'pre-wrap' }}>
              ⚠️ {newProjError}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', paddingTop: '12px', borderTop: '1px solid #3c3c3c', marginTop: '4px' }}>
            <button type="button" onClick={onClose} className="vscode-button" style={{ backgroundColor: '#3c3c3c', color: '#ffffff' }}>
              Cancelar
            </button>
            <button type="submit" className="vscode-button">Registrar</button>
          </div>
        </form>
      </div>
    </div>
  );
}
