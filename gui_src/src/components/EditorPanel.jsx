import React from 'react';
import Editor from '@monaco-editor/react';
import { Files, RefreshCw, Check, X, Maximize2, Minimize2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { getLanguage } from '../utils/language';

// Center panel: file tabs + Monaco editor (or empty state when no file is open).
export default function EditorPanel({
  selectedFile,
  openFiles,
  fileContent,
  fileContents,
  isSaving,
  theme,
  editorFontSize,
  editorTabSize,
  editorWordWrap,
  handleFileSelect,
  handleCloseTab,
  saveFile,
  handleEditorDidMount,
  setFileContent,
  isMaximized,
  onToggleMaximize,
}) {
  const { t } = useTranslation();

  if (!selectedFile) {
    return (
      <div className="vscode-editor-container" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <Files size={64} style={{ color: '#3c3c3c', marginBottom: '16px' }} />
          <h3 style={{ fontSize: '14px', fontWeight: 'bold', color: '#b0b0b0', marginBottom: '4px' }}>{t('editorPanel.noFileOpen')}</h3>
          <p style={{ fontSize: '12px', color: '#808080' }}>{t('editorPanel.openFileHint')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="vscode-editor-panel">
      {/* Tab bar */}
      <div className="vscode-tabs">
        <div className="flex h-full overflow-x-auto" style={{ gap: '2px' }}>
          {openFiles.map(filePath => {
            const isActive = filePath === selectedFile;
            return (
              <div
                key={filePath}
                onClick={() => handleFileSelect(filePath)}
                className={`vscode-tab ${isActive ? 'active' : ''}`}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                <span style={{ color: isActive ? '#ffffff' : '#a0a0a0' }}>
                  {filePath.split('/').pop()}
                </span>
                <button
                  onClick={(e) => handleCloseTab(filePath, e)}
                  className="vscode-tab-close-btn"
                >
                  <X size={12} />
                </button>
              </div>
            );
          })}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={saveFile}
            disabled={isSaving}
            className="vscode-button"
          >
            {isSaving ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
            <span>{isSaving ? t('editorPanel.saving') : t('editorPanel.save')}</span>
          </button>

          <button
            onClick={onToggleMaximize}
            className="vscode-bottom-panel-clear-btn"
            style={{ padding: '6px' }}
            title={isMaximized ? t('editorPanel.restoreEditor') : t('editorPanel.maximizeEditor')}
          >
            {isMaximized ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
        </div>
      </div>

      {/* Monaco editor */}
      <div className="vscode-editor-container">
        <Editor
          height="100%"
          path={selectedFile}
          language={getLanguage(selectedFile)}
          theme={theme === 'light' ? 'light' : 'vs-dark'}
          value={fileContent}
          onChange={(val) => setFileContent(val)}
          onMount={handleEditorDidMount}
          options={{
            minimap: { enabled: true },
            fontSize: editorFontSize,
            lineNumbers: 'on',
            tabSize: editorTabSize,
            wordWrap: editorWordWrap,
            automaticLayout: true,
          }}
        />
      </div>
    </div>
  );
}
