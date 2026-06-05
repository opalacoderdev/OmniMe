import React from 'react';
import { X, Settings } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import i18n from '../../i18n/index.js';
import { safeSetLocalStorage } from '../../utils/storage';
// Language preference is persisted server-side via /api/settings/language (survives webview restarts)

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
  onLanguageChange,
  ephemeralParams,
  setEphemeralParams,
}) {
  const { t } = useTranslation();
  const [selectedLang, setSelectedLang] = React.useState('');

  React.useEffect(() => {
    fetch('/api/settings/language')
      .then(r => r.ok ? r.json() : null)
      .then(cfg => { if (cfg?.lang !== undefined) setSelectedLang(cfg.lang); })
      .catch(() => { });
  }, []);

  const updateEphemeralParam = (key, val) => {
    const updated = { ...ephemeralParams };
    if (val === '' || val === undefined) delete updated[key];
    else updated[key] = val;
    setEphemeralParams(updated);
    safeSetLocalStorage('ephemeralParams', JSON.stringify(updated));
  };

  return (
    <div className="vscode-modal-overlay">
      <div className="vscode-modal" style={{ maxWidth: '440px', width: '90%' }}>
        {/* Header */}
        <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
          <span className="vscode-sidebar-title" style={{ color: 'var(--vscode-text-fg)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Settings size={14} style={{ color: '#007acc' }} />
            {t('settingsModal.title')}
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
                color: settingsTab === tab ? 'var(--vscode-text-fg)' : '#808080',
                fontWeight: 'bold', fontSize: '11px', textTransform: 'uppercase', cursor: 'pointer',
              }}
            >
              {tab === 'preferences' ? t('settingsModal.tabPreferences') : t('settingsModal.tabAbout')}
            </button>
          ))}
        </div>

        <div className="flex flex-col overflow-y-auto flex-1" style={{ padding: '16px', gap: '14px' }}>
          {settingsTab === 'preferences' ? (
            <>
              {/* Language */}
              <div className="flex flex-col" style={{ gap: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.language')}</label>
                <select
                  value={selectedLang}
                  onChange={(e) => {
                    const val = e.target.value;
                    setSelectedLang(val);
                    i18n.changeLanguage(val || navigator.language || 'en');
                    if (onLanguageChange) onLanguageChange(val);
                  }}
                  className="vscode-settings-input"
                  style={{ width: '100%' }}
                >
                  <option value="">{t('settingsModal.languageSystem')}</option>
                  <option value="pt-BR">{t('settingsModal.languagePtBR')}</option>
                  <option value="en">{t('settingsModal.languageEn')}</option>
                </select>
              </div>

              {/* Theme */}
              <div className="flex flex-col" style={{ gap: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.colorTheme')}</label>
                <select value={theme} onChange={(e) => setTheme(e.target.value)} className="vscode-settings-input" style={{ width: '100%' }}>
                  <option value="dark">{t('settingsModal.themeDark')}</option>
                  <option value="light">{t('settingsModal.themeLight')}</option>
                </select>
              </div>

              {/* Font size */}
              <div className="flex flex-col" style={{ gap: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.editorFontSize')}</label>
                <input
                  type="number" min="10" max="30" value={editorFontSize}
                  onChange={(e) => { const val = Number(e.target.value); setEditorFontSize(val); safeSetLocalStorage('editorFontSize', val); }}
                  className="vscode-settings-input"
                  style={{ width: '100%' }}
                />
              </div>

              {/* Tab size */}
              <div className="flex flex-col" style={{ gap: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.tabSize')}</label>
                <select value={editorTabSize} onChange={(e) => { const val = Number(e.target.value); setEditorTabSize(val); safeSetLocalStorage('editorTabSize', val); }} className="vscode-settings-input" style={{ width: '100%' }}>
                  <option value={2}>{t('settingsModal.twoSpaces')}</option>
                  <option value={4}>{t('settingsModal.fourSpaces')}</option>
                  <option value={8}>{t('settingsModal.eightSpaces')}</option>
                </select>
              </div>

              {/* Word wrap */}
              <div className="flex flex-col" style={{ gap: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.wordWrap')}</label>
                <select value={editorWordWrap} onChange={(e) => { setEditorWordWrap(e.target.value); safeSetLocalStorage('editorWordWrap', e.target.value); }} className="vscode-settings-input" style={{ width: '100%' }}>
                  <option value="on">{t('settingsModal.wordWrapOn')}</option>
                  <option value="off">{t('settingsModal.wordWrapOff')}</option>
                </select>
              </div>

              {/* Ephemeral Agent Settings */}
              <div className="flex flex-col" style={{ gap: '6px', borderTop: '1px solid var(--vscode-border)', paddingTop: '12px', marginTop: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.ephemeralAgentTitle')}</label>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div className="flex flex-col" style={{ gap: '4px' }}>
                    <label style={{ fontSize: '11px', color: '#a0a0a0' }}>{t('settingsModal.ephemeralMaxTokens')}</label>
                    <input type="number" min="1" className="vscode-settings-input" placeholder="1024"
                      value={ephemeralParams?.max_tokens || ''}
                      onChange={e => updateEphemeralParam('max_tokens', e.target.value ? Number(e.target.value) : undefined)} />
                  </div>
                  <div className="flex flex-col" style={{ gap: '4px' }}>
                    <label style={{ fontSize: '11px', color: '#a0a0a0' }}>{t('settingsModal.ephemeralContextWindow')}</label>
                    <input type="number" min="1" className="vscode-settings-input" placeholder="4096"
                      value={ephemeralParams?.num_ctx || ''}
                      onChange={e => updateEphemeralParam('num_ctx', e.target.value ? Number(e.target.value) : undefined)} />
                  </div>
                  <div className="flex flex-col" style={{ gap: '4px' }}>
                    <label style={{ fontSize: '11px', color: '#a0a0a0' }}>{t('settingsModal.ephemeralTemperature')}</label>
                    <input type="number" step="0.1" min="0" max="2" className="vscode-settings-input" placeholder="0.7"
                      value={ephemeralParams?.temperature ?? ''}
                      onChange={e => updateEphemeralParam('temperature', e.target.value ? parseFloat(e.target.value) : undefined)} />
                  </div>
                  <div className="flex flex-col" style={{ gap: '4px' }}>
                    <label style={{ fontSize: '11px', color: '#a0a0a0' }}>{t('settingsModal.ephemeralReasoningEffort')}</label>
                    <select className="vscode-settings-input"
                      value={ephemeralParams?.reasoning_effort || ''}
                      onChange={e => updateEphemeralParam('reasoning_effort', e.target.value || undefined)}>
                      <option value="">{t('settingsModal.ephemeralDefault')}</option>
                      <option value="none">none</option>
                      <option value="low">low</option>
                      <option value="medium">medium</option>
                      <option value="high">high</option>
                      <option value="xhigh">xhigh</option>
                    </select>
                  </div>
                  <div className="flex flex-col" style={{ gap: '4px' }}>
                    <label style={{ fontSize: '11px', color: '#a0a0a0' }}>{t('settingsModal.ephemeralResponseMode')}</label>
                    <select className="vscode-settings-input"
                      value={ephemeralParams?.response_mode || 'last'}
                      onChange={e => updateEphemeralParam('response_mode', e.target.value)}>
                      <option value="last">{t('settingsModal.ephemeralLastDefault')}</option>
                      <option value="all">all</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Optional dependencies */}
              <div className="flex flex-col" style={{ gap: '6px', borderTop: '1px solid var(--vscode-border)', paddingTop: '12px', marginTop: '6px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.optionalDeps')}</label>
                <span style={{ fontSize: '11px', color: '#888888', lineHeight: '1.4' }}>
                  {t('settingsModal.optionalDepsHint')}
                </span>
                <button type="button" className="vscode-button" disabled={isInstallingDeps} onClick={onInstallDeps} style={{ width: '100%', marginTop: '6px' }}>
                  {isInstallingDeps ? t('settingsModal.installingDeps') : t('settingsModal.installDeps')}
                </button>
                {installDepsStatus && (
                  <span style={{ fontSize: '11px', fontWeight: 'bold', color: installDepsStatus.includes('Erro') || installDepsStatus.includes('Falha') || installDepsStatus.includes('Error') || installDepsStatus.includes('Fail') ? '#f48771' : '#73c991', marginTop: '4px' }}>
                    {t('settingsModal.installStatus', { status: installDepsStatus })}
                  </span>
                )}
                {installDepsLog && (
                  <textarea readOnly value={installDepsLog} style={{ width: '100%', height: '80px', marginTop: '8px', fontSize: '10px', fontFamily: 'monospace', background: '#151515', color: '#89d4a5', border: '1px solid var(--vscode-border)', padding: '6px', resize: 'none' }} />
                )}
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', color: 'var(--vscode-text-fg)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.version')}</span>
                <span style={{ fontSize: '13px', fontWeight: 'bold', color: 'var(--vscode-text-fg)' }}>0.2.3.4 ALFA</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.author')}</span>
                <span style={{ fontSize: '13px', color: 'var(--vscode-text-fg)' }}>dev@opala.com</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('settingsModal.license')}</span>
                <span style={{ fontSize: '13px', color: 'var(--vscode-text-fg)' }}>MIT</span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '12px 16px', gap: '8px', borderTop: '1px solid var(--vscode-border)', backgroundColor: 'var(--vscode-sidebar-bg)' }}>
          <button onClick={onClose} className="vscode-button">{t('settingsModal.close')}</button>
        </div>
      </div>
    </div>
  );
}
