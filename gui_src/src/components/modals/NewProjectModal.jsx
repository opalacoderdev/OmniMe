import React from 'react';
import { X, FolderOpen } from 'lucide-react';
import { useTranslation, Trans } from 'react-i18next';

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
  const { t } = useTranslation();

  return (
    <div className="vscode-modal-overlay">
      <div className="vscode-modal">
        <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
          <span className="vscode-sidebar-title" style={{ color: 'var(--vscode-text-fg)' }}>{t('newProjectModal.title')}</span>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}>
            <X size={14} />
          </button>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col overflow-y-auto flex-1" style={{ padding: '16px', gap: '12px' }}>
          {/* Project name */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('newProjectModal.projectName')}</label>
            <input
              type="text"
              value={newProjName}
              onChange={(e) => setNewProjName(e.target.value)}
              placeholder={t('newProjectModal.projectNamePlaceholder')}
              required
            />
          </div>

          {/* Project path */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('newProjectModal.projectPath')}</label>
            <div style={{ display: 'flex', gap: '6px' }}>
              <input
                type="text"
                value={newProjPath}
                onChange={(e) => setNewProjPath(e.target.value)}
                placeholder={t('newProjectModal.projectPathPlaceholder')}
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
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('newProjectModal.description')}</label>
            <textarea
              value={newProjDesc}
              onChange={(e) => setNewProjDesc(e.target.value)}
              placeholder={t('newProjectModal.descriptionPlaceholder')}
              rows={2}
              style={{ resize: 'none' }}
            />
          </div>

          {/* API credentials */}
          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('newProjectModal.apiKey')}</label>
              <input type="password" value={newProjApiKey} onChange={(e) => setNewProjApiKey(e.target.value)} placeholder={t('newProjectModal.apiKeyPlaceholder')} />
            </div>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('newProjectModal.apiBase')}</label>
              <input type="text" value={newProjApiBase} onChange={(e) => setNewProjApiBase(e.target.value)} placeholder={t('newProjectModal.apiBasePlaceholder')} />
            </div>
          </div>

          <div style={{ fontSize: '11px', color: '#808080', marginTop: '-6px', lineHeight: '1.4' }}>
            <Trans i18nKey="newProjectModal.ollamaTip" components={[<span />, <strong />]} />
          </div>

          {/* Model + mode */}
          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('newProjectModal.aiModel')}</label>
              <input
                type="text"
                list="default-models"
                value={newProjModel}
                onChange={(e) => setNewProjModel(e.target.value)}
                onBlur={() => onLoadModelConfig(true)}
                placeholder={t('newProjectModal.modelPlaceholder')}
              />
              <datalist id="default-models">
                <option value="gemini/gemini-2.5-flash" />
                <option value="gemini/gemini-2.5-pro" />
                <option value="openai/gpt-4o" />
                <option value="ollama/gemma4:12b" />
              </datalist>
            </div>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('newProjectModal.executionMode')}</label>
              <select value={newProjMode} onChange={(e) => setNewProjMode(e.target.value)}>
                <option value="auto">{t('newProjectModal.modeAuto')}</option>
                <option value="plan">{t('newProjectModal.modePlan')}</option>
                <option value="edit">{t('newProjectModal.modeEdit')}</option>
              </select>
            </div>
          </div>

          {/* Load refined config */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <button type="button" className="vscode-button" style={{ background: '#3c3c3c', fontSize: '12px' }} onClick={onLoadModelConfig}>
              {t('newProjectModal.loadRefinedConfig')}
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
              {t('newProjectModal.cancel')}
            </button>
            <button type="submit" className="vscode-button">{t('newProjectModal.register')}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
