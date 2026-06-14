import { useRef, useEffect } from 'react';
import Editor from '@monaco-editor/react';
import { Files, RefreshCw, Check, X, Maximize2, Minimize2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { getLanguage } from '../utils/language';
import InlinePromptOverlay from './InlinePromptOverlay';

// Center panel: file tabs + Monaco editor (or empty state when no file is open).
export default function EditorPanel({
  selectedFile,
  openFiles,
  fileContent,
  fileContents,
  originalFileContents,
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
  // Inline prompt props
  inlinePrompt,
  setInlinePrompt,
  onInlineSubmit,
  isInlineRunning,
  onInlineCancel,
  onToggleTerminal,
}) {
  const { t } = useTranslation();
  // Ref so the Monaco command closure always calls the latest callback,
  // even after React re-renders update isTerminalCollapsed state.
  const onToggleTerminalRef = useRef(onToggleTerminal);
  onToggleTerminalRef.current = onToggleTerminal;

  const localEditorRef = useRef(null);

  // Wrap the external mount handler so we can also register the context-menu
  // actions and the Ctrl+L shortcut ourselves.
  const handleMount = (editor, monaco) => {
    localEditorRef.current = editor;

    // ── Ctrl+J — toggle terminal ────────────────────────────────────────────
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyJ,
      () => {
        if (onToggleTerminalRef.current) onToggleTerminalRef.current();
      }
    );

    // ── Ctrl+L — open inline free prompt ────────────────────────────────────
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyL,
      () => {
        const model = editor.getModel();
        const sel = editor.getSelection();
        if (!model || !sel) return;

        const selectedText = model.getValueInRange(sel);
        const pos = editor.getPosition();

        // Get pixel coordinates near the cursor
        const coords = editor.getScrolledVisiblePosition(pos);
        const domNode = editor.getDomNode();
        const rect = domNode?.getBoundingClientRect() ?? { left: 200, top: 100 };

        setInlinePrompt({
          x: rect.left + (coords?.left ?? 60) + 20,
          y: rect.top + (coords?.top ?? 40) + 24,
          startLine: sel.startLineNumber,
          endLine: sel.endLineNumber,
          cursorCol: pos?.column ?? 1,
          selectedText,
          mode: 'free',
        });
      }
    );

    // ── Paste via backend (navigator.clipboard.readText fails while context
    //    menu is open because hasTextFocus() is false; run() receives the
    //    editor directly so it works regardless of focus state).
    editor.addAction({
      id: 'opalacoder.paste',
      label: 'Paste',
      contextMenuGroupId: '9_cutcopypaste',
      contextMenuOrder: 3,
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyV],
      run: async (ed) => {
        let text = '';
        try {
          const res = await fetch('/api/clipboard/read');
          const data = await res.json();
          text = data.text ?? '';
        } catch (_) {}
        if (text) ed.trigger('keyboard', 'paste', { text });
      },
    });

    // ── Monaco context menu — Refine Selection ───────────────────────────────
    editor.addAction({
      id: 'opalacoder.refineSelection',
      label: t('editorPanel.refineSelection'),
      contextMenuGroupId: 'opalacoder',
      contextMenuOrder: 1,
      // Only show when there is a non-empty selection
      precondition: 'editorHasSelection',
      run: (ed) => {
        const model = ed.getModel();
        const sel = ed.getSelection();
        if (!model || !sel) return;
        const selectedText = model.getValueInRange(sel);
        const pos = ed.getPosition();
        const coords = ed.getScrolledVisiblePosition(pos);
        const domNode = ed.getDomNode();
        const rect = domNode?.getBoundingClientRect() ?? { left: 200, top: 100 };
        setInlinePrompt({
          x: rect.left + (coords?.left ?? 60) + 20,
          y: rect.top + (coords?.top ?? 40) + 24,
          startLine: sel.startLineNumber,
          endLine: sel.endLineNumber,
          cursorCol: pos?.column ?? 1,
          selectedText,
          mode: 'refine',
        });
      },
    });

    // ── Monaco context menu — Generate Code ──────────────────────────────────
    editor.addAction({
      id: 'opalacoder.generateCode',
      label: t('editorPanel.generateCode'),
      contextMenuGroupId: 'opalacoder',
      contextMenuOrder: 2,
      run: (ed) => {
        const model = ed.getModel();
        const pos = ed.getPosition();
        if (!model || !pos) return;
        
        const sel = ed.getSelection();
        const selectedText = (sel && !sel.isEmpty()) ? model.getValueInRange(sel) : '';

        const coords = ed.getScrolledVisiblePosition(pos);
        const domNode = ed.getDomNode();
        const rect = domNode?.getBoundingClientRect() ?? { left: 200, top: 100 };
        setInlinePrompt({
          x: rect.left + (coords?.left ?? 60) + 20,
          y: rect.top + (coords?.top ?? 40) + 24,
          startLine: pos.lineNumber,
          endLine: pos.lineNumber,
          cursorCol: pos.column,
          selectedText,
          mode: 'generate',
        });
      },
    });

    // Delegate to the parent-level mount handler (font-size, Ctrl+S, etc.)
    if (handleEditorDidMount) handleEditorDidMount(editor, monaco);
    
    // Focus the editor when it is first mounted
    setTimeout(() => editor.focus(), 50);
  };

  useEffect(() => {
    if (localEditorRef.current && selectedFile) {
      setTimeout(() => localEditorRef.current?.focus(), 50);
    }
  }, [selectedFile]);

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
    <div className="vscode-editor-panel" style={{ position: 'relative' }}>
      {/* Tab bar */}
      <div className="vscode-tabs">
        <div className="flex h-full overflow-x-auto" style={{ gap: '2px' }}>
          {openFiles.map(filePath => {
            const isActive = filePath === selectedFile;
            const currentContent = isActive ? fileContent : fileContents[filePath];
            const isDirty = originalFileContents && currentContent !== originalFileContents[filePath] && originalFileContents[filePath] !== undefined;

            return (
              <div
                key={filePath}
                onClick={() => handleFileSelect(filePath)}
                className={`vscode-tab ${isActive ? 'active' : ''}`}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                <span style={{ color: isActive ? '#ffffff' : '#a0a0a0' }}>
                  {filePath.replace(/\\/g, '/').split('/').pop()}{isDirty ? ' *' : ''}
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
          onMount={handleMount}
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

      {/* Inline prompt overlay (rendered inside the panel for correct stacking) */}
      {inlinePrompt && (
        <InlinePromptOverlay
          inlinePrompt={inlinePrompt}
          onSubmit={onInlineSubmit}
          onClose={() => setInlinePrompt(null)}
          onCancel={onInlineCancel}
          isRunning={isInlineRunning}
        />
      )}
    </div>
  );
}
