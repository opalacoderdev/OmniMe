import React, { useState, useEffect, useRef } from 'react';
import Editor from '@monaco-editor/react';
import { 
  Files, 
  GitBranch, 
  MessageSquare, 
  Settings, 
  Folder, 
  File, 
  Plus, 
  Trash2, 
  RefreshCw, 
  X, 
  Undo, 
  Check, 
  ArrowRight,
  ChevronRight,
  ChevronDown,
  Terminal,
  Play,
  Info,
  Maximize2,
  Minimize2
} from 'lucide-react';

export default function App() {
  // State variables
  const [projects, setProjects] = useState([]);
  const [activeProject, setActiveProject] = useState(null);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [isAgentRunning, setIsAgentRunning] = useState(false);
  const [terminalLogs, setTerminalLogs] = useState([]);
  const [isTerminalCollapsed, setIsTerminalCollapsed] = useState(false);
  const [isChatVisible, setIsChatVisible] = useState(true);
  const [activeSidebarTab, setActiveSidebarTab] = useState('explorer');

  // Panel sizing states for resizing
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [chatWidth, setChatWidth] = useState(320);
  const [bottomPanelHeight, setBottomPanelHeight] = useState(240);

  // Custom Context Menu State
  const [contextMenu, setContextMenu] = useState(null); // { x: number, y: number }

  // GUI Confirm Modal State: set when backend emits input_request event
  // Shape: { id: string, prompt: string, options: string[], default: string } | null
  const [confirmRequest, setConfirmRequest] = useState(null);

  const startResizing = (mouseDownEvent, direction) => {
    mouseDownEvent.preventDefault();
    const startX = mouseDownEvent.clientX;
    const startY = mouseDownEvent.clientY;
    const startWidthLeft = sidebarWidth;
    const startWidthRight = chatWidth;
    const startHeightBottom = bottomPanelHeight;

    const handleMouseMove = (mouseMoveEvent) => {
      if (direction === 'left') {
        const deltaX = mouseMoveEvent.clientX - startX;
        const newWidth = Math.max(150, Math.min(600, startWidthLeft + deltaX));
        setSidebarWidth(newWidth);
      } else if (direction === 'right') {
        const deltaX = startX - mouseMoveEvent.clientX;
        const newWidth = Math.max(200, Math.min(800, startWidthRight + deltaX));
        setChatWidth(newWidth);
      } else if (direction === 'bottom') {
        const deltaY = startY - mouseMoveEvent.clientY;
        const newHeight = Math.max(80, Math.min(600, startHeightBottom + deltaY));
        setBottomPanelHeight(newHeight);
      }
    };

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  // Modals & form fields
  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [newProjName, setNewProjName] = useState('');
  const [newProjPath, setNewProjPath] = useState('');
  const [newProjDesc, setNewProjDesc] = useState('');
  const [newProjModel, setNewProjModel] = useState('gemini/gemini-2.5-flash');
  const [newProjMode, setNewProjMode] = useState('auto');
  const [newProjApiKey, setNewProjApiKey] = useState('');
  const [newProjApiBase, setNewProjApiBase] = useState('');

  const chatEndRef = useRef(null);
  const logEndRef = useRef(null);

  // Initial load
  useEffect(() => {
    fetchProjects();
  }, []);

  // Sync files and greetings when project changes
  useEffect(() => {
    if (activeProject) {
      fetchFiles();
      setChatMessages([
        { role: 'assistant', content: `Olá! Estou pronto para auxiliar no projeto **${activeProject.project_name || activeProject.name}**.` }
      ]);
    } else {
      setFiles([]);
      setSelectedFile(null);
      setFileContent('');
    }
  }, [activeProject]);

  useEffect(() => {
    // Intercept native browser context menu globally
    const disableContextMenu = (e) => {
      e.preventDefault();
    };
    document.addEventListener('contextmenu', disableContextMenu);

    // Close context menu on left click anywhere
    const closeMenu = () => {
      setContextMenu(null);
    };
    document.addEventListener('click', closeMenu);

    return () => {
      document.removeEventListener('contextmenu', disableContextMenu);
      document.removeEventListener('click', closeMenu);
    };
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLogs]);

  // Keybindings (Ctrl+S to save)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        saveFile();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedFile, fileContent, activeProject]);

  // API calls
  const fetchProjects = async () => {
    try {
      const res = await fetch('/api/opalacoder/list-projects');
      if (res.ok) {
        const data = await res.json();
        setProjects(data.projects || []);
        if (data.projects && data.projects.length > 0 && !activeProject) {
          handleSelectProject(data.projects[0]);
        }
      }
    } catch (err) {
      addLog('error', `Falha ao carregar projetos: ${err.message}`);
    }
  };

  const handleSelectProject = (proj) => {
    setActiveProject(proj);
    addLog('info', `Projeto selecionado: ${proj.project_name || proj.name}`);
  };

  const fetchFiles = async () => {
    if (!activeProject) return;
    try {
      const res = await fetch(`/api/files?projectPath=${encodeURIComponent(activeProject.project_path)}`);
      if (res.ok) {
        const data = await res.json();
        setFiles(data.files || []);
      } else {
        const errData = await res.json();
        addLog('error', `Falha ao listar arquivos: ${errData.error}`);
      }
    } catch (err) {
      addLog('error', `Erro na chamada de arquivos: ${err.message}`);
    }
  };

  const handleWorkspaceContextMenu = (e) => {
    if (!activeProject) return;
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({
      x: e.clientX,
      y: e.clientY
    });
  };

  const handleCreateNewFile = async () => {
    if (!activeProject) return;
    const filename = window.prompt("Nome do novo arquivo (ex: src/utils.py):");
    if (!filename) return;
    
    try {
      const res = await fetch('/api/file/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectPath: activeProject.project_path,
          filePath: filename,
          content: ''
        })
      });
      
      if (res.ok) {
        addLog('info', `Arquivo criado: ${filename}`);
        await fetchFiles();
        setSelectedFile(filename);
        setFileContent('');
      } else {
        const errData = await res.json();
        addLog('error', `Falha ao criar arquivo: ${errData.error}`);
        alert(`Erro ao criar arquivo: ${errData.error}`);
      }
    } catch (err) {
      addLog('error', `Erro na chamada de criação de arquivo: ${err.message}`);
    }
  };

  const handleDeleteSelectedFile = async () => {
    if (!activeProject || !selectedFile) return;
    if (!window.confirm(`Tem certeza que deseja deletar o arquivo "${selectedFile}"?`)) return;
    
    try {
      const res = await fetch('/api/file/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectPath: activeProject.project_path,
          filePath: selectedFile
        })
      });
      
      if (res.ok) {
        addLog('info', `Arquivo excluído: ${selectedFile}`);
        setSelectedFile(null);
        setFileContent('');
        await fetchFiles();
      } else {
        const errData = await res.json();
        addLog('error', `Falha ao deletar arquivo: ${errData.error}`);
        alert(`Erro ao deletar arquivo: ${errData.error}`);
      }
    } catch (err) {
      addLog('error', `Erro na chamada de exclusão de arquivo: ${err.message}`);
    }
  };


  const handleFileSelect = async (filePath) => {
    if (!activeProject) return;
    setSelectedFile(filePath);
    try {
      const res = await fetch(`/api/file/read?projectPath=${encodeURIComponent(activeProject.project_path)}&filePath=${encodeURIComponent(filePath)}`);
      if (res.ok) {
        const data = await res.json();
        setFileContent(data.content);
      } else {
        addLog('error', `Erro ao ler arquivo: ${filePath}`);
      }
    } catch (err) {
      addLog('error', `Erro de leitura: ${err.message}`);
    }
  };

  const saveFile = async () => {
    if (!activeProject || !selectedFile) return;
    setIsSaving(true);
    try {
      const res = await fetch('/api/file/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectPath: activeProject.project_path,
          filePath: selectedFile,
          content: fileContent
        })
      });
      if (res.ok) {
        addLog('info', `Arquivo salvo: ${selectedFile}`);
      } else {
        addLog('error', `Erro ao salvar arquivo: ${selectedFile}`);
      }
    } catch (err) {
      addLog('error', `Erro de escrita: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateProject = async (e) => {
    e.preventDefault();
    if (!newProjName || !newProjPath) return;
    try {
      const res = await fetch('/api/opalacoder/create-project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_name: newProjName,
          project_path: newProjPath,
          description: newProjDesc,
          model: newProjModel,
          mode: newProjMode,
          api_key: newProjApiKey,
          api_base: newProjApiBase
        })
      });
      if (res.ok) {
        addLog('info', `Projeto '${newProjName}' registrado.`);
        setShowNewProjectModal(false);
        setNewProjName('');
        setNewProjPath('');
        setNewProjDesc('');
        setNewProjApiKey('');
        setNewProjApiBase('');
        fetchProjects();
      } else {
        const err = await res.json();
        addLog('error', `Erro ao criar projeto: ${err.error}`);
      }
    } catch (err) {
      addLog('error', `Erro ao criar: ${err.message}`);
    }
  };

  const handleDeleteProject = async (projName) => {
    if (!confirm(`Remover projeto '${projName}'?`)) return;
    try {
      const res = await fetch('/api/opalacoder/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: projName })
      });
      if (res.ok) {
        addLog('info', `Projeto removido: ${projName}`);
        if (activeProject && activeProject.name === projName) {
          setActiveProject(null);
        }
        fetchProjects();
      }
    } catch (err) {
      addLog('error', `Erro ao excluir: ${err.message}`);
    }
  };

  const addLog = (type, message) => {
    setTerminalLogs(prev => [...prev, { type, message, timestamp: new Date().toLocaleTimeString() }]);
  };

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    if (!chatInput.trim() || !activeProject || isAgentRunning) return;

    const userText = chatInput;
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: userText }]);
    setIsAgentRunning(true);
    addLog('info', `Iniciando agente para prompt: "${userText}"`);

    try {
      const res = await fetch('/api/opalacoder/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command: 'run',
          agent: 'chat_orchestrator',
          prompt: userText,
          project_name: activeProject.name,
          project_path: activeProject.project_path,
          model: activeProject.model
        })
      });

      if (!res.body) {
        addLog('error', 'ReadableStream não suportado pelo backend.');
        setIsAgentRunning(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const eventObj = JSON.parse(line);
            handleAgentEvent(eventObj);
          } catch (e) {
            addLog('stdout', line);
          }
        }
      }

      if (buffer.trim()) {
        try {
          const eventObj = JSON.parse(buffer);
          handleAgentEvent(eventObj);
        } catch (e) {
          addLog('stdout', buffer);
        }
      }

    } catch (err) {
      addLog('error', `Falha na execução: ${err.message}`);
    } finally {
      setIsAgentRunning(false);
      fetchFiles();
    }
  };

  const handleAgentEvent = (eventObj) => {
    const { event, ...data } = eventObj;
    switch (event) {
      case 'server_ready':
        addLog('info', 'Agente pronto.');
        break;
      case 'agent_started':
        addLog('info', `Agente ${data.agent} iniciado.`);
        break;
      case 'thought':
        addLog('thought', data.content);
        break;
      case 'tool_call':
        addLog('tool_call', `Chamando: ${data.tool} (${JSON.stringify(data.arguments)})`);
        break;
      case 'tool_result':
        addLog('tool_result', `Sucesso: ${data.tool}`);
        break;
      case 'agent_response':
        addLog('info', 'Resposta recebida.');
        setChatMessages(prev => {
          const last = prev[prev.length - 1];
          if (last && last.role === 'assistant' && last.content === data.response) {
            addLog('info', 'Duplicate assistant message ignored.');
            return prev; // duplicate, ignore
          }
          return [...prev, { role: 'assistant', content: data.response }];
        });
        break;
      case 'agent_finished':
        addLog('info', 'Processamento concluído.');
        break;
      case 'input_request':
        // Backend is awaiting a Yes/No response from the user — show modal.
        setConfirmRequest({
          id: data.id,
          prompt: data.prompt,
          options: data.options || ['yes', 'no'],
          default: data.default || 'yes',
        });
        addLog('info', `🔔 Aguardando confirmação: ${data.prompt}`);
        break;
      case 'error':
        addLog('error', data.message);
        break;
      default:
        addLog('info', `Evento: ${event}`);
    }
  };

  const sendConfirmResponse = async (value) => {
    if (!confirmRequest) return;
    const { id, prompt } = confirmRequest;
    setConfirmRequest(null);
    addLog('info', `✅ Confirmação: "${prompt}" → ${value}`);
    try {
      await fetch('/api/opalacoder/input_response', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, value }),
      });
    } catch (err) {
      addLog('error', `Erro ao enviar confirmação: ${err.message}`);
    }
  };

  const getLanguage = (filename) => {
    if (!filename) return 'plaintext';
    const ext = filename.split('.').pop().toLowerCase();
    const map = {
      py: 'python',
      js: 'javascript',
      jsx: 'javascript',
      ts: 'typescript',
      tsx: 'typescript',
      html: 'html',
      css: 'css',
      json: 'json',
      md: 'markdown',
      yml: 'yaml',
      yaml: 'yaml',
      sh: 'shell'
    };
    return map[ext] || 'plaintext';
  };



  return (
    <div className="vscode-app">
      
      {/* Main Row container */}
      <div className="vscode-main">
        
        {/* VSCode Activity Bar (48px wide) */}
        <div className="vscode-activitybar">
          <div className="vscode-activitybar-top">
            <button 
              onClick={() => setActiveSidebarTab('explorer')}
              className={`vscode-activitybar-btn ${activeSidebarTab === 'explorer' ? 'active' : ''}`}
              title="Explorer"
            >
              <Files size={22} />
            </button>
            <button 
              onClick={() => setActiveSidebarTab('git')}
              className={`vscode-activitybar-btn ${activeSidebarTab === 'git' ? 'active' : ''}`}
              title="Source Control"
            >
              <GitBranch size={22} />
            </button>
            <button 
              onClick={() => setIsChatVisible(!isChatVisible)}
              className={`vscode-activitybar-btn ${isChatVisible ? 'active' : ''}`}
              title="Copilot Chat"
            >
              <MessageSquare size={22} />
            </button>
          </div>
          
          <div>
            <button className="vscode-activitybar-btn" title="Settings">
              <Settings size={20} />
            </button>
          </div>
        </div>

        {/* VSCode Left Sidebar */}
        <aside className="vscode-sidebar" style={{ width: `${sidebarWidth}px` }}>
          {activeSidebarTab === 'explorer' ? (
            <div className="flex flex-col h-full overflow-hidden">
              {/* Sidebar Header */}
              <div className="vscode-sidebar-header">
                <span className="vscode-sidebar-title">EXPLORER: PROJECTS</span>
                <button 
                  onClick={() => setShowNewProjectModal(true)}
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#c5c5c5' }}
                  title="Novo Projeto..."
                >
                  <Plus size={14} />
                </button>
              </div>

              {/* Projects list */}
              <div className="vscode-sidebar-section">
                <div className="vscode-sidebar-section-title">Selecione o Projeto</div>
                <div className="overflow-y-auto" style={{ maxHeight: '140px' }}>
                  {projects.map(p => {
                    const isActive = activeProject && activeProject.name === p.name;
                    return (
                      <div 
                        key={p.name}
                        onClick={() => handleSelectProject(p)}
                        className={`vscode-project-item ${isActive ? 'active' : ''}`}
                      >
                        <div className="truncate flex-1">
                          <div style={{ fontSize: '13px', fontWeight: '500' }} className="truncate">{p.project_name || p.name}</div>
                          <div style={{ fontSize: '10px', color: '#808080' }} className="truncate">{p.project_path}</div>
                        </div>
                        <button 
                          onClick={(e) => { e.stopPropagation(); handleDeleteProject(p.name); }}
                          style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Files list tree */}
              <div className="vscode-sidebar-content" onContextMenu={handleWorkspaceContextMenu}>
                <div className="vscode-sidebar-section-title">Workspace Files</div>
                {files.length === 0 ? (
                  <div style={{ fontSize: '12px', color: '#808080', padding: '0 4px', fontStyle: 'italic' }}>
                    Selecione um projeto para explorar.
                  </div>
                ) : (
                  <div>
                    {files.map(node => (
                      <FileNode 
                        key={node.path} 
                        node={node} 
                        selectedFile={selectedFile} 
                        handleFileSelect={handleFileSelect} 
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="vscode-sidebar-content" style={{ padding: '16px' }}>
              <div className="vscode-sidebar-title" style={{ marginBottom: '12px' }}>SOURCE CONTROL (GIT)</div>
              <div style={{ fontSize: '12px', color: '#808080', fontStyle: 'italic' }}>Sem alterações locais.</div>
            </div>
          )}
        </aside>

        {/* Left Resizer split bar */}
        <div 
          className="vscode-resizer-horizontal"
          onMouseDown={(e) => startResizing(e, 'left')}
        />

        {/* Center Panel (Monaco Editor & Collapsible Console) */}
        <main className="vscode-editor-panel">
          
          {selectedFile ? (
            <div className="vscode-editor-panel">
              {/* Tab Header bar */}
              <div className="vscode-tabs">
                <div className="flex h-full">
                  <div className="vscode-tab">
                    <span style={{ color: '#ffffff' }}>{selectedFile.split('/').pop()}</span>
                    <button 
                      onClick={() => setSelectedFile(null)} 
                      className="vscode-tab-close-btn"
                    >
                      <X size={12} />
                    </button>
                  </div>
                </div>
                
                <div>
                  <button 
                    onClick={saveFile}
                    disabled={isSaving}
                    className="vscode-button"
                  >
                    {isSaving ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                    <span>{isSaving ? 'Salvando...' : 'Salvar (Ctrl+S)'}</span>
                  </button>
                </div>
              </div>

              {/* Editor Workspace */}
              <div className="vscode-editor-container">
                <Editor
                  height="100%"
                  language={getLanguage(selectedFile)}
                  theme="vs-dark"
                  value={fileContent}
                  onChange={(val) => setFileContent(val)}
                  options={{
                    minimap: { enabled: true },
                    fontSize: 13,
                    lineNumbers: 'on',
                    tabSize: 4,
                    wordWrap: 'on',
                    automaticLayout: true,
                  }}
                />
              </div>
            </div>
          ) : (
            <div className="vscode-editor-container" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ textAlign: 'center' }}>
                <Files size={64} style={{ color: '#3c3c3c', marginBottom: '16px' }} />
                <h3 style={{ fontSize: '14px', fontWeight: 'bold', color: '#b0b0b0', marginBottom: '4px' }}>Nenhum Arquivo Aberto</h3>
                <p style={{ fontSize: '12px', color: '#808080' }}>Abra um arquivo na barra lateral esquerda.</p>
              </div>
            </div>
          )}

          {/* Vertical Resizer split bar */}
          {!isTerminalCollapsed && (
            <div 
              className="vscode-resizer-vertical"
              onMouseDown={(e) => startResizing(e, 'bottom')}
            />
          )}

          {/* Bottom logs console */}
          <div className="vscode-bottom-panel" style={{ height: isTerminalCollapsed ? '30px' : `${bottomPanelHeight}px` }}>
            <div className="vscode-bottom-tabs">
              <div className="vscode-bottom-tab-list">
                <span className="vscode-bottom-tab active">OUTPUT (OPALACODER)</span>
                <span className="vscode-bottom-tab">PROBLEMS</span>
                <span className="vscode-bottom-tab">TERMINAL</span>
              </div>
              <button 
                onClick={() => setIsTerminalCollapsed(!isTerminalCollapsed)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
              >
                {isTerminalCollapsed ? <Maximize2 size={12} /> : <Minimize2 size={12} />}
              </button>
            </div>
            
            {!isTerminalCollapsed && (
              <div className="vscode-logs">
                {terminalLogs.length === 0 ? (
                  <div style={{ color: '#808080', fontStyle: 'italic' }}>Nenhum log gerado. Envie uma instrução no chat para iniciar...</div>
                ) : (
                  terminalLogs.map((log, i) => {
                    let color = 'text-[#cccccc]';
                    let label = 'SYSTEM';
                    
                    if (log.type === 'error') { color = 'text-[#f48771] font-semibold'; label = 'ERROR'; }
                    else if (log.type === 'info') { color = 'text-[#75beff]'; label = 'INFO'; }
                    else if (log.type === 'thought') { color = 'text-[#da70d6] italic'; label = 'THOUGHT'; }
                    else if (log.type === 'tool_call') { color = 'text-[#d7ba7d]'; label = 'TOOL'; }
                    else if (log.type === 'tool_result') { color = 'text-[#89d4a5]'; label = 'RESULT'; }
                    
                    return (
                      <div key={i} className={color} style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', marginBottom: '3px' }}>
                        <span style={{ color: '#5a5a5a' }}>[{log.timestamp}]</span>
                        <span style={{ fontWeight: 'bold' }}>[{label}]</span>
                        <span style={{ whiteSpace: 'pre-wrap', flex: 1 }}>{log.message}</span>
                      </div>
                    );
                  })
                )}
                <div ref={logEndRef} />
              </div>
            )}
          </div>
        </main>

        {/* Right Resizer split bar */}
        {isChatVisible && (
          <div 
            className="vscode-resizer-horizontal"
            onMouseDown={(e) => startResizing(e, 'right')}
          />
        )}

        {/* VSCode Copilot Chat (Right Panel) */}
        {isChatVisible && (
          <aside className="vscode-chat" style={{ width: `${chatWidth}px` }}>
            <div className="vscode-chat-header">
              <span className="vscode-sidebar-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <MessageSquare size={12} style={{ color: '#007acc' }} />
                <span>COPILOT CHAT</span>
              </span>
              <button 
                onClick={() => setIsChatVisible(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
              >
                <X size={14} />
              </button>
            </div>

            {/* Quick Actions toolbar */}
            <div className="vscode-chat-toolbar">
              <button onClick={() => setChatInput('/undo')} className="vscode-chat-tool-btn">
                <Undo size={11} />
                <span>/undo</span>
              </button>
              <button onClick={() => setChatInput('/clear')} className="vscode-chat-tool-btn">
                <RefreshCw size={11} />
                <span>/clear</span>
              </button>
              <button onClick={() => setChatInput('/commit')} className="vscode-chat-tool-btn">
                <Check size={11} />
                <span>/commit</span>
              </button>
            </div>

            {/* Chat message list */}
            <div className="vscode-chat-history">
              {chatMessages.map((msg, i) => {
                const isUser = msg.role === 'user';
                return (
                  <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span 
                       className="vscode-chat-msg-header" 
                       style={{ color: isUser ? '#75beff' : '#da70d6' }}
                    >
                      {isUser ? 'VOCÊ' : 'OPALACODER'}
                    </span>
                    <div className="vscode-chat-msg-content">
                      {formatMessageContent(msg.content)}
                    </div>
                  </div>
                );
              })}
              {isAgentRunning && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span className="vscode-chat-msg-header" style={{ color: '#da70d6' }}>
                    OPALACODER
                  </span>
                  <div className="vscode-chat-msg-content">
                    <div className="thinking-indicator">
                      <span className="dot"></span>
                      <span className="dot"></span>
                      <span className="dot"></span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Footer input form */}
            <form onSubmit={handleSendMessage} className="vscode-chat-form">
              <div className="vscode-chat-input-row">
                <input 
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  disabled={!activeProject || isAgentRunning}
                  placeholder={!activeProject ? "Defina um projeto..." : isAgentRunning ? "Pensando..." : "Pergunte ao OpalaCoder..."}
                  style={{ flex: 1 }}
                />
                <button 
                  type="submit"
                  disabled={!activeProject || isAgentRunning || !chatInput.trim()}
                  className="vscode-button"
                  style={{ padding: '6px' }}
                >
                  <ArrowRight size={14} />
                </button>
              </div>
            </form>
          </aside>
        )}
      </div>

      {/* VSCode Footer Status Bar */}
      <footer className="vscode-statusbar">
        <div className="flex items-center" style={{ gap: '16px' }}>
          <div className="flex items-center" style={{ gap: '6px' }}>
            <Info size={11} />
            <span style={{ fontWeight: 'bold' }}>
              {activeProject ? `Workspace: ${activeProject.project_name || activeProject.name}` : 'Sem Workspace'}
            </span>
          </div>
          {isAgentRunning && (
            <span className="flex items-center" style={{ gap: '6px' }}>
              <span style={{ width: '6px', height: '6px', backgroundColor: '#ffffff', borderRadius: '50%', display: 'inline-block' }}></span>
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

      {/* VSCode Style New Project Modal */}
      {showNewProjectModal && (
        <div className="vscode-modal-overlay">
          <div className="vscode-modal">
            <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
              <span className="vscode-sidebar-title" style={{ color: '#ffffff' }}>REGISTRAR NOVO PROJETO</span>
              <button 
                onClick={() => setShowNewProjectModal(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
              >
                <X size={14} />
              </button>
            </div>
            
            <form onSubmit={handleCreateProject} className="flex flex-col" style={{ padding: '16px', gap: '12px' }}>
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

              <div className="flex flex-col" style={{ gap: '4px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Caminho Absoluto *</label>
                <input 
                  type="text" 
                  value={newProjPath}
                  onChange={(e) => setNewProjPath(e.target.value)}
                  placeholder="Ex: /home/gilzamir/projetos/meu-app" 
                  required
                />
              </div>

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

              <div style={{ display: 'flex', gap: '12px' }}>
                <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
                  <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Chave de API (Opcional)</label>
                  <input 
                    type="password" 
                    value={newProjApiKey}
                    onChange={(e) => setNewProjApiKey(e.target.value)}
                    placeholder="Ex: sk-..." 
                  />
                </div>

                <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
                  <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>URL Base da API (Opcional)</label>
                  <input 
                    type="text" 
                    value={newProjApiBase}
                    onChange={(e) => setNewProjApiBase(e.target.value)}
                    placeholder="Ex: http://localhost:11434/v1" 
                  />
                </div>
              </div>
              <div style={{ fontSize: '11px', color: '#808080', marginTop: '-6px', lineHeight: '1.4' }}>
                Dica: Para usar o Ollama local com <strong>ollama/ministral-3:14b</strong>, informe a URL Base acima (ex: <code>http://localhost:11434/v1</code>) e digite/selecione o modelo correspondente.
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <div className="flex flex-col flex-1" style={{ gap: '4px' }}>
                  <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Modelo de IA</label>
                  <input
                    type="text"
                    list="default-models"
                    value={newProjModel}
                    onChange={(e) => setNewProjModel(e.target.value)}
                    placeholder="Selecione ou digite o modelo (ex: ollama/ministral-3:14b)"
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
                  <select 
                    value={newProjMode}
                    onChange={(e) => setNewProjMode(e.target.value)}
                  >
                    <option value="auto">Auto (Completo)</option>
                    <option value="plan">Plan (Planejar)</option>
                    <option value="edit">Edit (Editar)</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', paddingTop: '12px', borderTop: '1px solid #3c3c3c', marginTop: '4px' }}>
                <button 
                  type="button" 
                  onClick={() => setShowNewProjectModal(false)}
                  className="vscode-button"
                  style={{ backgroundColor: '#3c3c3c', color: '#ffffff' }}
                >
                  Cancelar
                </button>
                <button 
                  type="submit" 
                  className="vscode-button"
                >
                  Registrar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Floating custom context menu */}
      {contextMenu && (
        <div 
          className="vscode-context-menu"
          style={{ top: `${contextMenu.y}px`, left: `${contextMenu.x}px` }}
        >
          <div 
            className="vscode-context-menu-item"
            onClick={handleCreateNewFile}
          >
            <Plus size={13} style={{ color: '#007acc' }} />
            <span>New File...</span>
          </div>
          {selectedFile && (
            <div 
              className="vscode-context-menu-item"
              onClick={handleDeleteSelectedFile}
            >
              <Trash2 size={13} style={{ color: '#f48771' }} />
              <span>Delete File</span>
            </div>
          )}
        </div>
      )}

      {/* GUI Confirm Modal — slides in when backend emits input_request */}
      {confirmRequest && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)',
          animation: 'fadeIn 0.15s ease',
        }}>
          <div style={{
            background: 'linear-gradient(135deg, #1e1e2e 0%, #252537 100%)',
            border: '1px solid #3c3c5c',
            borderRadius: '12px',
            padding: '28px 32px',
            maxWidth: '420px',
            width: '90%',
            boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
          }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
              <span style={{ fontSize: '22px' }}>🔔</span>
              <span style={{ fontSize: '12px', fontWeight: 700, color: '#a0a0c0', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                Confirmação Necessária
              </span>
            </div>
            {/* Prompt text */}
            <p style={{ fontSize: '14px', color: '#e0e0f0', lineHeight: 1.6, marginBottom: '24px', margin: '0 0 24px 0' }}>
              {confirmRequest.prompt}
            </p>
            {/* Buttons */}
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                id="confirm-no-btn"
                onClick={() => sendConfirmResponse('no')}
                style={{
                  padding: '8px 20px', borderRadius: '8px', border: '1px solid #4c4c6c',
                  background: 'transparent', color: '#a0a0c0', cursor: 'pointer',
                  fontSize: '13px', fontWeight: 600, transition: 'all 0.15s',
                }}
                onMouseEnter={e => { e.target.style.background = '#2c2c3c'; e.target.style.color = '#e0e0f0'; }}
                onMouseLeave={e => { e.target.style.background = 'transparent'; e.target.style.color = '#a0a0c0'; }}
              >
                Não
              </button>
              <button
                id="confirm-yes-btn"
                onClick={() => sendConfirmResponse('yes')}
                style={{
                  padding: '8px 24px', borderRadius: '8px', border: 'none',
                  background: 'linear-gradient(135deg, #007acc, #0062a3)',
                  color: '#fff', cursor: 'pointer',
                  fontSize: '13px', fontWeight: 700,
                  boxShadow: '0 4px 16px rgba(0,122,204,0.35)',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={e => { e.target.style.background = 'linear-gradient(135deg, #0090f0, #007acc)'; }}
                onMouseLeave={e => { e.target.style.background = 'linear-gradient(135deg, #007acc, #0062a3)'; }}
              >
                Sim
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Subcomponente de nó de arquivo para respeitar as Regras de Hooks
function FileNode({ node, selectedFile, handleFileSelect }) {
  const isDir = node.isDirectory;
  const [isOpen, setIsOpen] = useState(false);

  if (isDir) {
    return (
      <div className="select-none">
        <div 
          onClick={() => setIsOpen(!isOpen)} 
          className="vscode-tree-node"
        >
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Folder size={14} className="text-white" style={{ color: '#e8a838' }} />
          <span className="truncate">{node.name}</span>
        </div>
        {isOpen && (
          <div style={{ paddingLeft: '12px', borderLeft: '1px solid #3c3c3c', marginLeft: '14px' }}>
            {node.children.map(child => (
              <FileNode 
                key={child.path}
                node={child} 
                selectedFile={selectedFile} 
                handleFileSelect={handleFileSelect} 
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const isSelected = selectedFile === node.path;
  return (
    <div 
      onClick={() => handleFileSelect(node.path)}
      className={`vscode-tree-node ${isSelected ? 'active' : ''}`}
    >
      <File size={13} style={{ color: '#a0a0a0' }} />
      <span className="truncate">{node.name}</span>
    </div>
  );
}

// Formata mensagens de chat substituindo sintaxe markdown simples por tags HTML estilizadas
function formatMessageContent(content) {
  if (!content) return null;
  const lines = content.split('\n');
  return lines.map((line, idx) => {
    const trimmed = line.trim();
    
    // Títulos: ### Título
    if (trimmed.startsWith('### ')) {
      const title = trimmed.replace('### ', '');
      return (
        <h4 key={idx} style={{ margin: '14px 0 6px 0', fontWeight: 'bold', color: '#ffffff', fontSize: '13px' }}>
          {title}
        </h4>
      );
    }
    
    // Listas: 🔹 **`cmd`** — desc ou ⭐ **`cmd`** — desc
    if (trimmed.startsWith('🔹 ') || trimmed.startsWith('⭐ ')) {
      const icon = trimmed.substring(0, 2);
      const rest = trimmed.substring(2);
      
      const parts = rest.split('—');
      if (parts.length >= 2) {
        const cmdPart = parts[0].replace(/\*\*`|`\*\*/g, '').trim();
        const descPart = parts.slice(1).join('—').trim();
        return (
          <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', margin: '4px 0', paddingLeft: '4px' }}>
            <span style={{ fontSize: '12px', flexShrink: 0 }}>{icon}</span>
            <span style={{ fontSize: '13px', lineHeight: '1.4' }}>
              <code style={{ background: '#2d2d2d', padding: '2px 4px', borderRadius: '3px', color: '#f8f8f2', fontFamily: 'monospace', fontSize: '11px', marginRight: '6px' }}>
                {cmdPart}
              </code>
              <span style={{ color: '#cccccc' }}>{descPart}</span>
            </span>
          </div>
        );
      }
    }
    
    // Notas de Rodapé: _(nota)_
    if (trimmed.startsWith('_(') && trimmed.endsWith(')_')) {
      const note = trimmed.substring(2, trimmed.length - 2);
      return (
        <p key={idx} style={{ margin: '8px 0', fontStyle: 'italic', color: '#8a8a8a', fontSize: '11px' }}>
          {note}
        </p>
      );
    }
    
    // Linha comum (respeitando quebra)
    return (
      <div key={idx} style={{ minHeight: '1.2em', color: '#cccccc', fontSize: '13px', margin: '2px 0' }}>
        {line}
      </div>
    );
  });
}
