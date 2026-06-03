import React from 'react';
import { X, Settings, Check, FolderOpen } from 'lucide-react';

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
  showAdvancedParams,
  setShowAdvancedParams,
  modelConfigMsg,
  onLoadModelConfig,
  onOpenDirPicker,
}) {
  if (!editingProject) return null;

  // Helper to update a model_param key.
  const setParam = (key, value) => {
    setEditingProject(p => {
      const n = { ...p.model_params };
      if (value === undefined || value === '') {
        delete n[key];
      } else {
        n[key] = value;
      }
      return { ...p, model_params: n };
    });
  };

  const parseNum = (str, asFloat = false) =>
    str === '' ? undefined : asFloat ? parseFloat(str) : parseInt(str, 10);

  return (
    <div className="vscode-modal-overlay">
      <div className="vscode-modal" style={{ maxWidth: '520px', width: '92%' }}>
        {/* Header */}
        <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
          <span className="vscode-sidebar-title" style={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Settings size={14} style={{ color: '#007acc' }} />
            CONFIGURAÇÕES DO PROJETO
          </span>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}>
            <X size={14} />
          </button>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col overflow-y-auto flex-1" style={{ padding: '16px', gap: '14px' }}>

          {/* Internal key (read-only) */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>ID Interno (somente leitura)</label>
            <input type="text" value={editingProject.name} readOnly style={{ opacity: 0.5, cursor: 'not-allowed' }} />
          </div>

          {/* Display name */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Nome de Exibição *</label>
            <input
              type="text"
              value={editingProject.project_name}
              onChange={e => setEditingProject(p => ({ ...p, project_name: e.target.value }))}
              required
              placeholder="Nome do projeto"
            />
          </div>

          {/* Project path */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Caminho Absoluto</label>
            <div style={{ display: 'flex', gap: '6px' }}>
              <input
                type="text"
                value={editingProject.project_path}
                onChange={e => setEditingProject(p => ({ ...p, project_path: e.target.value }))}
                placeholder="/caminho/absoluto/do/projeto"
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
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Modelo Principal</label>
              <input
                type="text"
                list="edit-models"
                value={editingProject.model}
                onChange={e => setEditingProject(p => ({ ...p, model: e.target.value }))}
                placeholder="gemini/gemini-2.5-flash"
              />
              <datalist id="edit-models">
                <option value="gemini/gemini-2.5-flash" />
                <option value="gemini/gemini-2.5-pro" />
                <option value="openai/gpt-4o" />
                <option value="ollama/ministral-3:14b" />
              </datalist>
            </div>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Modo</label>
              <select value={editingProject.mode} onChange={e => setEditingProject(p => ({ ...p, mode: e.target.value }))}>
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

          {/* Alternative model */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Modelo Alternativo</label>
            <input
              type="text"
              list="edit-alt-models"
              value={editingProject.alternative_model}
              onChange={e => setEditingProject(p => ({ ...p, alternative_model: e.target.value }))}
              placeholder="(usa o padrão global se vazio)"
            />
            <datalist id="edit-alt-models">
              <option value="gemini/gemini-2.5-flash" />
              <option value="openai/gpt-4o-mini" />
              <option value="ollama/gemma3:4b" />
            </datalist>
          </div>

          {/* API credentials */}
          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Chave de API (Opcional)</label>
              <input type="password" value={editingProject.api_key} onChange={e => setEditingProject(p => ({ ...p, api_key: e.target.value }))} placeholder="Ex: sk-..." />
            </div>
            <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
              <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>URL Base da API (Opcional)</label>
              <input type="text" value={editingProject.api_base} onChange={e => setEditingProject(p => ({ ...p, api_base: e.target.value }))} placeholder="Ex: http://localhost:11434/v1" />
            </div>
          </div>

          {/* Description */}
          <div className="flex flex-col" style={{ gap: '4px' }}>
            <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Descrição</label>
            <textarea
              value={editingProject.description}
              onChange={e => setEditingProject(p => ({ ...p, description: e.target.value }))}
              placeholder="Descrição opcional do projeto..."
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
              <span>{showAdvancedParams ? '▼' : '▶'} Parâmetros do Modelo (Avançado)</span>
            </button>

            {showAdvancedParams && (
              <div style={{ border: '1px solid #3c3c3c', borderRadius: '4px', padding: '12px', marginTop: '8px', backgroundColor: '#252526', display: 'flex', flexDirection: 'column', gap: '16px' }}>

                {/* LiteLLM params */}
                <div>
                  <div style={{ color: '#9cdcfe', fontSize: '11px', fontWeight: 'bold', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Parâmetros LiteLLM (model_kwargs)
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                    <ParamNumber label="Temperature" step="0.1" min="0" max="2" placeholder="padrão: 0.7"
                      value={editingProject.model_params?.temperature}
                      onChange={e => setParam('temperature', parseNum(e.target.value, true))} />
                    <ParamNumber label="Max Tokens" min="1" placeholder="padrão: 4096"
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

                    <div className="flex flex-col" style={{ gap: '4px' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Reasoning Effort</label>
                      <select
                        value={editingProject.model_params?.reasoning_effort ?? ''}
                        onChange={e => setParam('reasoning_effort', e.target.value || undefined)}
                        style={{ backgroundColor: '#3c3c3c', color: '#cccccc', border: '1px solid #555', borderRadius: '3px', padding: '4px 6px', fontSize: '12px' }}
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
                        <span style={{ fontSize: '12px', color: '#cccccc' }}>Habilitado</span>
                      </label>
                    </div>

                    <div className="flex flex-col" style={{ gap: '4px', justifyContent: 'flex-end' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Stream</label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', userSelect: 'none' }}>
                        <input type="checkbox"
                          checked={!!editingProject.model_params?.stream}
                          onChange={e => setEditingProject(p => ({ ...p, model_params: { ...p.model_params, stream: e.target.checked } }))} />
                        <span style={{ fontSize: '12px', color: '#cccccc' }}>Habilitado</span>
                      </label>
                    </div>
                  </div>
                </div>

                {/* Agent params */}
                <div>
                  <div style={{ color: '#9cdcfe', fontSize: '11px', fontWeight: 'bold', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Parâmetros do Agente
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
                    <ParamNumber label="Max Tool Calls (Worker)" min="1" placeholder="padrão: 10"
                      value={editingProject.model_params?.max_tool_calls}
                      onChange={e => setParam('max_tool_calls', parseNum(e.target.value))} />

                    <div className="flex flex-col" style={{ gap: '4px' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Response Mode (MemGPT)</label>
                      <select
                        value={editingProject.model_params?.response_mode ?? 'all'}
                        onChange={e => setEditingProject(p => ({ ...p, model_params: { ...p.model_params, response_mode: e.target.value } }))}
                        style={{ backgroundColor: '#3c3c3c', color: '#cccccc', border: '1px solid #555', borderRadius: '3px', padding: '4px 6px', fontSize: '12px' }}
                      >
                        <option value="all">all — concatena todas as mensagens</option>
                        <option value="last">last — só a última mensagem</option>
                      </select>
                    </div>

                    <div className="flex flex-col" style={{ gap: '4px', justifyContent: 'flex-end' }}>
                      <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Debug</label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', userSelect: 'none' }}>
                        <input type="checkbox"
                          checked={!!editingProject.model_params?.debug}
                          onChange={e => setEditingProject(p => ({ ...p, model_params: { ...p.model_params, debug: e.target.checked } }))} />
                        <span style={{ fontSize: '12px', color: '#cccccc' }}>Habilitado</span>
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', paddingTop: '12px', borderTop: '1px solid #3c3c3c', marginTop: '4px' }}>
            <button type="button" onClick={onClose} className="vscode-button" style={{ backgroundColor: '#3c3c3c', color: '#ffffff' }}>
              Cancelar
            </button>
            <button type="submit" className="vscode-button">
              <Check size={12} />
              Salvar Alterações
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
