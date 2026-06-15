import React from 'react';
import { X, Settings, Check, FolderOpen } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useModelValidation } from './useModelValidation';

// Numeric input helper to avoid repetition in the advanced params grid.
function ParamNumber({ label, value, onChange, step, min, max, placeholder }) {
  return (
    <div className="flex flex-col" style={{ gap: '4px' }}>
      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{label}</label>
      <input
        type="number"
        step={step}
        min={min}
        max={max}
        placeholder={placeholder}
        value={value ?? ''}
        onChange={onChange}
      />
    </div>
  );
}

// Project settings edit modal (model params, paths, credentials, etc.).
export default function EditProjectModal({
  editingProject,
  setEditingProject,
  onClose,
  onSubmit,
  editProjError,
  showAdvancedParams,
  setShowAdvancedParams,
  modelConfigMsg,
  onLoadModelConfig,
  onOpenDirPicker,
}) {
  const { t } = useTranslation();
  const { hardware, modelStatus } = useModelValidation(editingProject?.model);

  const getBorderColor = () => {
    if (modelStatus === 'green') return '#4ade80';
    if (modelStatus === 'yellow') return '#facc15';
    if (modelStatus === 'red') return '#f87171';
    return undefined;
  };

  if (!editingProject) return null;

  // Helper to update a model_param key.
  const setParam = (key, value) => {
    setEditingProject(p => {
      const n = { ...p.model_params };
      if (value === undefined || value === '') {
        delete n[key];
      } else {
        let clampedValue = value;
        const limits = {
          temperature: { min: 0, max: 2 },
          top_p: { min: 0, max: 1 },
          frequency_penalty: { min: -2, max: 2 },
          presence_penalty: { min: -2, max: 2 },
          min_p: { min: 0, max: 1 },
          eviction_threshold: { min: 0, max: 1 },
          memory_pressure_threshold: { min: 0, max: 1 },
          max_tokens: { min: 1 },
          num_ctx: { min: 1 },
          seed: { min: 0 },
          top_k: { min: 1 },
          repetition_penalty: { min: 0 },
          max_heartbeats: { min: 1 },
          max_context_tokens: { min: 1 },
          max_iterations: { min: 1 },
          max_tool_calls: { min: 1 },

        };
        if (limits[key] && typeof clampedValue === 'number') {
          const { min, max } = limits[key];
          if (min !== undefined && clampedValue < min) clampedValue = min;
          if (max !== undefined && clampedValue > max) clampedValue = max;
        }
        n[key] = clampedValue;
      }
      return { ...p, model_params: n };
    });
  };

  const parseNum = (str, asFloat = false) => {
    if (str === '' || str === undefined || str === null) return undefined;
    const cleanStr = String(str).replace(',', '.');
    const val = asFloat ? parseFloat(cleanStr) : parseInt(cleanStr, 10);
    return isNaN(val) ? undefined : val;
  };

  return (
    <div className="vscode-modal-overlay">
      <div className="vscode-modal" style={{ maxWidth: '520px', width: '92%' }}>
        {/* Header */}
        <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
          <span className="vscode-sidebar-title" style={{ color: 'var(--vscode-text-fg)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Settings size={14} style={{ color: '#007acc' }} />
            {t('editProjectModal.title', { name: editingProject.project_name || editingProject.name })}
          </span>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}>
            <X size={14} />
          </button>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col overflow-y-auto flex-1" style={{ padding: '16px', gap: '14px' }}>

          {/* Internal key (read-only) */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.internalId')}</label>
            <input type="text" value={editingProject.name} readOnly style={{ opacity: 0.5, cursor: 'not-allowed' }} />
          </div>

          {/* Display name */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.displayName')}</label>
            <input
              type="text"
              value={editingProject.project_name}
              onChange={e => setEditingProject(p => ({ ...p, project_name: e.target.value }))}
              required
              placeholder={t('editProjectModal.projectNamePlaceholder')}
            />
          </div>

          {/* Project path */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.projectPath')}</label>
            <div style={{ display: 'flex', gap: '6px' }}>
              <input
                type="text"
                value={editingProject.project_path}
                onChange={e => setEditingProject(p => ({ ...p, project_path: e.target.value }))}
                placeholder={t('editProjectModal.projectPathPlaceholder')}
                style={{ flex: 1 }}
              />
              <button type="button" className="vscode-button" style={{ padding: '4px 8px', whiteSpace: 'nowrap' }}
                onClick={() => onOpenDirPicker('edit', editingProject.project_path || '~')}>
                <FolderOpen size={14} />
              </button>
            </div>
          </div>

          {/* Model + mode */}
          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.mainModel')}</label>
              <input
                type="text"
                list="edit-models"
                value={editingProject.model}
                onChange={e => setEditingProject(p => ({ ...p, model: e.target.value }))}
                onBlur={() => onLoadModelConfig(true)}
                placeholder="gemini/gemini-2.5-flash"
                style={{ borderColor: getBorderColor(), borderWidth: modelStatus !== 'unknown' ? '2px' : '1px' }}
              />
              <datalist id="edit-models">
                <option value="gemini/gemini-flash-lite-latest" />
                <option value="anthropic/claude-3-5-sonnet-latest" />
                <option value="openai/gpt-4o" />
                <option value="ollama/gemma4:12b" />
                <option value="ollama/gemma4:31b-cloud" />
              </datalist>
              {modelStatus === 'green' && <span style={{ fontSize: '10px', color: '#4ade80' }}>✓ Modelo adequado ao seu hardware.</span>}
              {modelStatus === 'yellow' && <span style={{ fontSize: '10px', color: '#facc15' }}>⚠ Poderá ficar lento (uso de CPU RAM).</span>}
              {modelStatus === 'red' && <span style={{ fontSize: '10px', color: '#f87171' }}>❌ Pode exceder a memória da máquina.</span>}
              {hardware && <span style={{ fontSize: '10px', color: '#a0a0c0' }}>VRAM: {hardware.vram_gb}GB | RAM: {hardware.ram_gb}GB</span>}
            </div>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.mode')}</label>
              <select className="vscode-settings-input" value={editingProject.mode} onChange={e => setEditingProject(p => ({ ...p, mode: e.target.value }))}>
                <option value="auto">{t('editProjectModal.modeAuto')}</option>
                <option value="plan">{t('editProjectModal.modePlan')}</option>
                <option value="edit">{t('editProjectModal.modeEdit')}</option>
              </select>
            </div>
          </div>

          {/* Load refined config */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <button type="button" className="vscode-button" style={{ background: '#3c3c3c', fontSize: '12px' }} onClick={() => onLoadModelConfig(false)}>
              {t('editProjectModal.loadRefinedConfig')}
            </button>
            <button type="button" className="vscode-button" style={{ background: '#3c3c3c', fontSize: '12px' }} onClick={() => onOpenDirPicker('export-modelconfig', editingProject.project_path || '~')}>
              Exportar Modelconfig
            </button>
            {modelConfigMsg && (
              <span style={{ fontSize: '11px', color: modelConfigMsg.startsWith('✅') ? '#4ec9b0' : '#f48771' }}>
                {modelConfigMsg}
              </span>
            )}
          </div>

          {/* Worker model */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.workerModel')}</label>
            <input
              type="text"
              list="edit-worker-models"
              value={editingProject.worker_model}
              onChange={e => setEditingProject(p => ({ ...p, worker_model: e.target.value }))}
              placeholder={t('editProjectModal.workerModelPlaceholder')}
            />
            <datalist id="edit-worker-models">
              <option value="gemini/gemini-flash-lite-latest" />
              <option value="anthropic/claude-3-5-sonnet-latest" />
              <option value="ollama/gemma4:12b" />
              <option value="ollama/gemma4:31b-cloud" />
            </datalist>
          </div>

          {/* API credentials (main model) */}
          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.apiKey')}</label>
              <input type="password" value={editingProject.api_key} onChange={e => setEditingProject(p => ({ ...p, api_key: e.target.value }))} placeholder={t('editProjectModal.apiKeyPlaceholder')} />
            </div>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.apiBase')}</label>
              <input type="text" value={editingProject.api_base} onChange={e => setEditingProject(p => ({ ...p, api_base: e.target.value }))} placeholder={t('editProjectModal.apiBasePlaceholder')} />
            </div>
          </div>

          {/* API credentials (worker model) */}
          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.workerApiKey')}</label>
              <input type="password" value={editingProject.worker_api_key} onChange={e => setEditingProject(p => ({ ...p, worker_api_key: e.target.value }))} placeholder={t('editProjectModal.apiKeyPlaceholder')} />
            </div>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.workerApiBase')}</label>
              <input type="text" value={editingProject.worker_api_base} onChange={e => setEditingProject(p => ({ ...p, worker_api_base: e.target.value }))} placeholder={t('editProjectModal.apiBasePlaceholder')} />
            </div>
          </div>

          {/* Description */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>{t('editProjectModal.description')}</label>
            <textarea
              value={editingProject.description}
              onChange={e => setEditingProject(p => ({ ...p, description: e.target.value }))}
              placeholder={t('editProjectModal.descriptionPlaceholder')}
              rows={2}
              style={{ resize: 'none' }}
            />
          </div>

          {/* Advanced params (collapsible) */}
          <div className="flex flex-col" style={{ marginTop: '4px' }}>
            <button
              type="button"
              onClick={() => setShowAdvancedParams(!showAdvancedParams)}
              style={{ background: 'transparent', border: 'none', color: '#007acc', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', padding: '4px 0', fontSize: '12px', fontWeight: 'bold', textAlign: 'left', width: 'fit-content' }}
            >
              <span>{showAdvancedParams ? '▼' : '▶'} {t('editProjectModal.advancedParams')}</span>
            </button>

            {showAdvancedParams && (
              <div style={{ border: '1px solid #3c3c3c', borderRadius: '4px', padding: '12px', marginTop: '8px', backgroundColor: '#252526', display: 'flex', flexDirection: 'column', gap: '16px' }}>

                {/* LiteLLM params */}
                <div>
                  <div style={{ color: '#9cdcfe', fontSize: '11px', fontWeight: 'bold', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {t('editProjectModal.litellmParams')}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                    <ParamNumber label="Temperature" step="0.1" min="0" max="2" placeholder="padrão: 0.7"
                      value={editingProject.model_params?.temperature}
                      onChange={e => setParam('temperature', parseNum(e.target.value, true))} />
                    <ParamNumber label="Max Tokens" min="1" placeholder="ilimitado"
                      value={editingProject.model_params?.max_tokens}
                      onChange={e => setParam('max_tokens', parseNum(e.target.value))} />
                    <ParamNumber label="Context Window (num_ctx)" min="1" placeholder="padrão: 8192"
                      value={editingProject.model_params?.num_ctx}
                      onChange={e => setParam('num_ctx', parseNum(e.target.value))} />
                    <ParamNumber label="Seed" min="0" placeholder="padrão: nenhum"
                      value={editingProject.model_params?.seed}
                      onChange={e => setParam('seed', parseNum(e.target.value))} />
                    <ParamNumber label="Top P" step="0.05" min="0" max="1" placeholder="padrão: 1.0"
                      value={editingProject.model_params?.top_p}
                      onChange={e => setParam('top_p', parseNum(e.target.value, true))} />
                    <ParamNumber label="Frequency Penalty" step="0.1" min="-2" max="2" placeholder="padrão: 0.0"
                      value={editingProject.model_params?.frequency_penalty}
                      onChange={e => setParam('frequency_penalty', parseNum(e.target.value, true))} />
                    <ParamNumber label="Presence Penalty" step="0.1" min="-2" max="2" placeholder="padrão: 0.0"
                      value={editingProject.model_params?.presence_penalty}
                      onChange={e => setParam('presence_penalty', parseNum(e.target.value, true))} />
                    <ParamNumber label="Top K" min="1" placeholder="padrão: 40"
                      value={editingProject.model_params?.top_k}
                      onChange={e => setParam('top_k', parseNum(e.target.value))} />
                    <ParamNumber label="Min P" step="0.05" min="0" max="1" placeholder="padrão: 0.0"
                      value={editingProject.model_params?.min_p}
                      onChange={e => setParam('min_p', parseNum(e.target.value, true))} />
                    <ParamNumber label="Repetition Penalty" step="0.1" min="0" placeholder="padrão: 1.0"
                      value={editingProject.model_params?.repetition_penalty}
                      onChange={e => setParam('repetition_penalty', parseNum(e.target.value, true))} />

                    <div className="flex flex-col" style={{ gap: '4px' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Reasoning Effort</label>
                      <select
                        className="vscode-settings-input"
                        value={editingProject.model_params?.reasoning_effort ?? ''}
                        onChange={e => setParam('reasoning_effort', e.target.value || undefined)}
                      >
                        <option value="">— padrão —</option>
                        <option value="none">none</option>
                        <option value="low">low</option>
                        <option value="medium">medium</option>
                        <option value="high">high</option>
                        <option value="xhigh">xhigh</option>
                      </select>
                    </div>

                    <div className="flex flex-col" style={{ gap: '4px', justifyContent: 'flex-end' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Thinking (think)</label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', userSelect: 'none' }}>
                        <input type="checkbox"
                          checked={!!editingProject.model_params?.think}
                          onChange={e => setEditingProject(p => ({ ...p, model_params: { ...p.model_params, think: e.target.checked } }))} />
                        <span style={{ fontSize: '12px', color: '#cccccc' }}>{t('editProjectModal.enabled')}</span>
                      </label>
                    </div>

                    <div className="flex flex-col" style={{ gap: '4px', justifyContent: 'flex-end' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Stream</label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', userSelect: 'none' }}>
                        <input type="checkbox"
                          checked={!!editingProject.model_params?.stream}
                          onChange={e => setEditingProject(p => ({ ...p, model_params: { ...p.model_params, stream: e.target.checked } }))} />
                        <span style={{ fontSize: '12px', color: '#cccccc' }}>{t('editProjectModal.enabled')}</span>
                      </label>
                    </div>
                  </div>
                </div>

                {/* Agent params */}
                <div>
                  <div style={{ color: '#9cdcfe', fontSize: '11px', fontWeight: 'bold', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {t('editProjectModal.agentParams')}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                    <ParamNumber label="Max Heartbeats (MemGPT)" min="1" placeholder="padrão: 20 (memgpt)"
                      value={editingProject.model_params?.max_heartbeats}
                      onChange={e => setParam('max_heartbeats', parseNum(e.target.value))} />
                    <ParamNumber label="Max Context Tokens (MemGPT)" min="1" placeholder="padrão: igual a num_ctx"
                      value={editingProject.model_params?.max_context_tokens}
                      onChange={e => setParam('max_context_tokens', parseNum(e.target.value))} />
                    <ParamNumber label="Eviction Threshold" step="0.05" min="0" max="1" placeholder="padrão: 1.0"
                      value={editingProject.model_params?.eviction_threshold}
                      onChange={e => setParam('eviction_threshold', parseNum(e.target.value, true))} />
                    <ParamNumber label="Memory Pressure Threshold" step="0.05" min="0" max="1" placeholder="padrão: 0.7"
                      value={editingProject.model_params?.memory_pressure_threshold}
                      onChange={e => setParam('memory_pressure_threshold', parseNum(e.target.value, true))} />
                    <ParamNumber label="Max Iterations (Worker)" min="1" placeholder="padrão: sem limite"
                      value={editingProject.model_params?.max_iterations}
                      onChange={e => setParam('max_iterations', parseNum(e.target.value))} />
                    <ParamNumber label="Max Tool Calls (Worker)" min="1" placeholder="padrão: 40"
                      value={editingProject.model_params?.max_tool_calls}
                      onChange={e => setParam('max_tool_calls', parseNum(e.target.value))} />
                    <ParamNumber label="Loop Detection Limit" min="1" placeholder="padrão: 3"
                      value={editingProject.model_params?.loop_detection_limit}
                      onChange={e => setParam('loop_detection_limit', parseNum(e.target.value))} />
                    
                    <div className="flex flex-col" style={{ gap: '4px', justifyContent: 'flex-end' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Loop Detection</label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', userSelect: 'none' }}>
                        <input type="checkbox"
                          checked={editingProject.model_params?.loop_detection ?? true}
                          onChange={e => setEditingProject(p => ({ ...p, model_params: { ...p.model_params, loop_detection: e.target.checked } }))} />
                        <span style={{ fontSize: '12px', color: '#cccccc' }}>Habilitado</span>
                      </label>
                    </div>
                    <div className="flex flex-col" style={{ gap: '4px' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Response Mode (MemGPT)</label>
                      <select
                        className="vscode-settings-input"
                        value={editingProject.model_params?.response_mode ?? 'last'}
                        onChange={e => setEditingProject(p => ({ ...p, model_params: { ...p.model_params, response_mode: e.target.value } }))}
                      >
                        <option value="all">{t('editProjectModal.responseModeAll')}</option>
                        <option value="last">{t('editProjectModal.responseModeLast')}</option>
                      </select>
                    </div>

                    <div className="flex flex-col" style={{ gap: '4px', justifyContent: 'flex-end' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Debug</label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', userSelect: 'none' }}>
                        <input type="checkbox"
                          checked={!!editingProject.model_params?.debug}
                          onChange={e => setEditingProject(p => ({ ...p, model_params: { ...p.model_params, debug: e.target.checked } }))} />
                        <span style={{ fontSize: '12px', color: '#cccccc' }}>{t('editProjectModal.enabled')}</span>
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {editProjError && (
            <div style={{ color: '#f48771', fontSize: '11px', marginTop: '4px', whiteSpace: 'pre-wrap' }}>
              ⚠️ {editProjError}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', paddingTop: '12px', borderTop: '1px solid #3c3c3c', marginTop: '4px' }}>
            <button type="button" onClick={onClose} className="vscode-button" style={{ backgroundColor: '#3c3c3c', color: '#ffffff' }}>
              {t('editProjectModal.cancel')}
            </button>
            <button type="submit" className="vscode-button">
              <Check size={12} />
              {t('editProjectModal.saveChanges')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
