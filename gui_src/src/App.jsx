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
  Edit2,
  Trash,
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
  Minimize2,
  AlertCircle,
  AlertTriangle
} from 'lucide-react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';


const safeGetLocalStorage = (key, defaultValue) => {
  try {
    const val = localStorage.getItem(key);
    return val !== null ? val : defaultValue;
  } catch (e) {
    return defaultValue;
  }
};

const safeSetLocalStorage = (key, value) => {
  try {
    localStorage.setItem(key, value);
  } catch (e) {
    // ignore
  }
};

export default function App() {
  // State variables
  const [projects, setProjects] = useState([]);
  const [activeProject, setActiveProject] = useState(null);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');
  const [openFiles, setOpenFiles] = useState([]);
  const [fileContents, setFileContents] = useState({});
  const [rightClickedNode, setRightClickedNode] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [isAgentRunning, setIsAgentRunning] = useState(false);
  const [terminalLogs, setTerminalLogs] = useState([]);
  const [isTerminalCollapsed, setIsTerminalCollapsed] = useState(false);
  const [isChatVisible, setIsChatVisible] = useState(true);
  const [activeSidebarTab, setActiveSidebarTab] = useState('explorer');
  const [activeBottomTab, setActiveBottomTab] = useState('output');
  const [problems, setProblems] = useState([]);
  
  // IDE Settings States
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState('preferences');
  const [theme, setTheme] = useState(() => safeGetLocalStorage('theme', 'dark'));
  const [editorFontSize, setEditorFontSize] = useState(() => Number(safeGetLocalStorage('editorFontSize', 13)));
  const [editorTabSize, setEditorTabSize] = useState(() => Number(safeGetLocalStorage('editorTabSize', 4)));
  const [editorWordWrap, setEditorWordWrap] = useState(() => safeGetLocalStorage('editorWordWrap', 'on'));

  // Git Source Control States
  const [gitChanges, setGitChanges] = useState([]);
  const [commitMessage, setCommitMessage] = useState('');
  const [isCommitting, setIsCommitting] = useState(false);

  // Optional Dependencies States
  const [isInstallingDeps, setIsInstallingDeps] = useState(false);
  const [installDepsStatus, setInstallDepsStatus] = useState('');
  const [installDepsLog, setInstallDepsLog] = useState('');
  const [showInstallPrompt, setShowInstallPrompt] = useState(false);


  const terminalRef = useRef(null);
  const terminalInstanceRef = useRef(null);
  const eventSourceRef = useRef(null);
  const fitAddonRef = useRef(null);


  // Panel sizing states for resizing
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [chatWidth, setChatWidth] = useState(320);
  const [bottomPanelHeight, setBottomPanelHeight] = useState(240);

  // Custom Context Menu State
  const [contextMenu, setContextMenu] = useState(null); // { x: number, y: number }

  // GUI Confirm Modal State: set when backend emits input_request event
  // Shape: { id: string, prompt: string, options: string[], default: string } | null
  const [confirmRequest, setConfirmRequest] = useState(null);

  // Project settings edit modal state
  // Shape: { name, project_name, project_path, model, alternative_model, mode, description } | null
  const [editingProject, setEditingProject] = useState(null);

  const fetchProblems = async () => {
    if (!activeProject) return;
    try {
      const res = await fetch(`/api/opalacoder/problems?projectPath=${encodeURIComponent(activeProject.project_path)}`);
      if (res.ok) {
        const data = await res.json();
        setProblems(data.problems || []);
      }
    } catch (err) {
      console.error("Failed to fetch problems", err);
    }
  };

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
        const deltaX = mouseMoveEvent.clientX - startX;
        const newWidth = Math.max(200, Math.min(600, startWidthRight - deltaX));
        setChatWidth(newWidth);
      } else if (direction === 'bottom') {
        const deltaY = mouseMoveEvent.clientY - startY;
        const newHeight = Math.max(100, Math.min(600, startHeightBottom - deltaY));
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
    const checkOptionalDeps = async () => {
      try {
        const res = await fetch('/api/settings/check-dependencies');
        if (res.ok) {
          const data = await res.json();
          if (!data.installed) {
            setShowInstallPrompt(true);
          }
        }
      } catch (e) {
        console.error("Failed to check optional dependencies", e);
      }
    };
    checkOptionalDeps();
  }, []);

  // Sync files and greetings when project changes
  useEffect(() => {
    if (activeProject) {
      fetchFiles();
      fetchProblems();
      setChatMessages([
        { role: 'assistant', content: `Olá! Estou pronto para auxiliar no projeto **${activeProject.project_name || activeProject.name}**.` }
      ]);
    } else {
      setFiles([]);
      setSelectedFile(null);
      setFileContent('');
      setOpenFiles([]);
      setFileContents({});
      setProblems([]);
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

  useEffect(() => {
    if (!activeProject) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      return;
    }

    if (!terminalRef.current) return;

    // Initialize xterm
    const term = new XTerm({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Consolas, "Courier New", monospace',
      theme: {
        background: '#1e1e1e',
        foreground: '#cccccc',
      }
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);

    // Clear element before mounting
    terminalRef.current.innerHTML = '';
    term.open(terminalRef.current);
    try {
      fitAddon.fit();
    } catch(e) {}
    terminalInstanceRef.current = term;
    fitAddonRef.current = fitAddon;

    // Connect to SSE stream
    const projectPath = activeProject.project_path;
    const url = `/api/terminal/stream?projectPath=${encodeURIComponent(projectPath)}`;
    const evs = new EventSource(url);
    eventSourceRef.current = evs;

    evs.onmessage = (event) => {
      try {
        const base64Data = event.data;
        const raw = atob(base64Data);
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) {
          bytes[i] = raw.charCodeAt(i);
        }
        term.write(bytes);
      } catch (err) {
        console.error("Error decoding terminal stream data", err);
      }
    };

    evs.onerror = (err) => {
      console.error("Terminal event source error", err);
      term.write('\r\n\x1b[31m[OpalaCoder] Conexão com o terminal perdida. Reconectando...\x1b[0m\r\n');
    };    // Keystroke handlers
    term.onData((data) => {
      fetch('/api/terminal/input', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'input', text: data, projectPath: activeProject.project_path })
      }).catch(err => console.error("Failed to send terminal input", err));
    });

    // Resize listener
    const resizeObserver = new ResizeObserver(() => {
      if (fitAddon) {
        try {
          fitAddon.fit();
          const { cols, rows } = term;
          fetch('/api/terminal/input', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'resize', cols, rows, projectPath: activeProject.project_path })
          }).catch(err => console.error("Failed to send terminal resize", err));
        } catch (e) {}
      }
    });
    resizeObserver.observe(terminalRef.current);

    return () => {
      resizeObserver.disconnect();
      if (evs) {
        evs.close();
      }
      term.dispose();
      terminalInstanceRef.current = null;
      fitAddonRef.current = null;
    };
  }, [activeProject]);

  useEffect(() => {
    safeSetLocalStorage('theme', theme);
    if (theme === 'light') {
      document.body.classList.add('light-theme');
    } else {
      document.body.classList.remove('light-theme');
    }
  }, [theme]);

  useEffect(() => {
    if (activeBottomTab === 'terminal' && terminalInstanceRef.current && fitAddonRef.current && activeProject) {
      setTimeout(() => {
        try {
          fitAddonRef.current.fit();
          const { cols, rows } = terminalInstanceRef.current;
          fetch('/api/terminal/input', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'resize', cols, rows, projectPath: activeProject.project_path })
          }).catch(err => console.error("Failed to send terminal resize", err));
          
          terminalInstanceRef.current.focus();
        } catch (e) {}
      }, 50);
    }
  }, [activeBottomTab, bottomPanelHeight, activeProject]);

  useEffect(() => {
    if (activeProject) {
      fetchGitStatus();
    } else {
      setGitChanges([]);
    }
  }, [activeProject]);

  useEffect(() => {
    if (activeSidebarTab === 'git' && activeProject) {
      fetchGitStatus();
    }
  }, [activeSidebarTab, activeProject]);





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

  const fetchGitStatus = async () => {
    if (!activeProject) return;
    try {
      const res = await fetch(`/api/git/status?projectPath=${encodeURIComponent(activeProject.project_path)}`);
      if (res.ok) {
        const data = await res.json();
        setGitChanges(data.files || []);
      }
    } catch (err) {
      console.error("Failed to fetch git status", err);
    }
  };

  const handleGitCommit = async (e) => {
    if (e) e.preventDefault();
    if (!activeProject || !commitMessage.trim() || isCommitting) return;
    setIsCommitting(true);
    addLog('info', `Criando commit com a mensagem: "${commitMessage}"...`);
    try {
      const res = await fetch('/api/git/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectPath: activeProject.project_path,
          message: commitMessage
        })
      });
      if (res.ok) {
        addLog('info', 'Commit criado com sucesso!');
        setCommitMessage('');
        fetchGitStatus();
      } else {
        const data = await res.json();
        addLog('error', `Falha ao fazer commit: ${data.error || 'Erro desconhecido'}`);
      }
    } catch (err) {
      addLog('error', `Erro ao fazer commit: ${err.message}`);
    } finally {
      setIsCommitting(false);
    }
  };

  const handleInstallOptionalDeps = async () => {
    if (isInstallingDeps) return;
    setIsInstallingDeps(true);
    setInstallDepsStatus('Instalando...');
    setInstallDepsLog('Iniciando pip install...\n');
    try {
      const response = await fetch('/api/settings/install-dependencies', {
        method: 'POST'
      });
      if (!response.ok) {
        throw new Error('Falha ao iniciar instalação');
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line.trim());
            if (data.output) {
              setInstallDepsLog(prev => prev + data.output);
            }
            if (data.status === 'success') {
              setInstallDepsStatus('Instalado com Sucesso!');
            } else if (data.status === 'error') {
              setInstallDepsStatus('Erro na Instalação');
            }
          } catch (e) {
            // Ignore formatting/chunk parsing errors
          }
        }
      }
    } catch (err) {
      setInstallDepsStatus('Falha ao conectar');
      setInstallDepsLog(prev => prev + `\nErro: ${err.message}\n`);
    } finally {
      setIsInstallingDeps(false);
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
    setRightClickedNode(null);
    setContextMenu({
      x: e.clientX,
      y: e.clientY
    });
  };

  const handleNodeContextMenu = (e, node) => {
    if (!activeProject) return;
    e.preventDefault();
    e.stopPropagation();
    setRightClickedNode(node);
    setContextMenu({
      x: e.clientX,
      y: e.clientY
    });
  };

  const handleCreateNewFile = async (parentPath) => {
    if (!activeProject) return;
    const defaultPath = parentPath ? `${parentPath}/` : '';
    const filename = window.prompt("Nome do novo arquivo (ex: src/utils.py):", defaultPath);
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
        // Open it in the editor
        await handleFileSelect(filename);
      } else {
        const errData = await res.json();
        addLog('error', `Falha ao criar arquivo: ${errData.error}`);
        alert(`Erro ao criar arquivo: ${errData.error}`);
      }
    } catch (err) {
      addLog('error', `Erro na chamada de criação de arquivo: ${err.message}`);
    }
  };

  const handleRenameNode = async (node) => {
    if (!activeProject || !node) return;
    const newPath = window.prompt(`Digite o novo caminho/nome para "${node.path}":`, node.path);
    if (!newPath || newPath === node.path) return;

    try {
      const res = await fetch('/api/file/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectPath: activeProject.project_path,
          oldPath: node.path,
          newPath: newPath
        })
      });

      if (res.ok) {
        addLog('info', `${node.isDirectory ? 'Diretório' : 'Arquivo'} renomeado de ${node.path} para ${newPath}`);
        
        if (!node.isDirectory) {
          // If it is a file, update tabs
          setOpenFiles(prev => prev.map(f => f === node.path ? newPath : f));
          setFileContents(prev => {
            const next = { ...prev };
            const content = next[node.path];
            delete next[node.path];
            next[newPath] = content;
            return next;
          });
          if (selectedFile === node.path) {
            setSelectedFile(newPath);
          }
        } else {
          // If it's a directory, update any open files inside it
          const prefix = `${node.path}/`;
          setOpenFiles(prev => prev.map(f => f.startsWith(prefix) ? f.replace(node.path, newPath) : f));
          setFileContents(prev => {
            const next = {};
            for (const [k, v] of Object.entries(prev)) {
              if (k.startsWith(prefix)) {
                next[k.replace(node.path, newPath)] = v;
              } else {
                next[k] = v;
              }
            }
            return next;
          });
          if (selectedFile && selectedFile.startsWith(prefix)) {
            setSelectedFile(prev => prev.replace(node.path, newPath));
          }
        }
        await fetchFiles();
      } else {
        const errData = await res.json();
        addLog('error', `Falha ao renomear: ${errData.error}`);
        alert(`Erro ao renomear: ${errData.error}`);
      }
    } catch (err) {
      addLog('error', `Erro ao renomear: ${err.message}`);
    }
  };

  const handleDeleteNode = async (node) => {
    if (!activeProject || !node) return;
    const confirmMsg = `Tem certeza que deseja deletar o ${node.isDirectory ? 'diretório' : 'arquivo'} "${node.path}"?${node.isDirectory ? ' Todos os arquivos internos serão removidos!' : ''}`;
    if (!window.confirm(confirmMsg)) return;

    try {
      const res = await fetch('/api/file/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectPath: activeProject.project_path,
          filePath: node.path
        })
      });

      if (res.ok) {
        addLog('info', `${node.isDirectory ? 'Diretório' : 'Arquivo'} excluído: ${node.path}`);
        
        if (!node.isDirectory) {
          // Remove from tabs
          setOpenFiles(prev => prev.filter(f => f !== node.path));
          setFileContents(prev => {
            const next = { ...prev };
            delete next[node.path];
            return next;
          });
          if (selectedFile === node.path) {
            setSelectedFile(prev => {
              const remaining = openFiles.filter(f => f !== node.path);
              if (remaining.length > 0) {
                const nextActive = remaining[remaining.length - 1];
                setTimeout(() => {
                  setFileContent(fileContents[nextActive] || '');
                }, 0);
                return nextActive;
              }
              setFileContent('');
              return null;
            });
          }
        } else {
          // Remove all open files inside this directory
          const prefix = `${node.path}/`;
          setOpenFiles(prev => prev.filter(f => !f.startsWith(prefix)));
          setFileContents(prev => {
            const next = {};
            for (const [k, v] of Object.entries(prev)) {
              if (!k.startsWith(prefix)) {
                next[k] = v;
              }
            }
            return next;
          });
          if (selectedFile && selectedFile.startsWith(prefix)) {
            setSelectedFile(prev => {
              const remaining = openFiles.filter(f => !f.startsWith(prefix));
              if (remaining.length > 0) {
                const nextActive = remaining[remaining.length - 1];
                setTimeout(() => {
                  setFileContent(fileContents[nextActive] || '');
                }, 0);
                return nextActive;
              }
              setFileContent('');
              return null;
            });
          }
        }
        await fetchFiles();
      } else {
        const errData = await res.json();
        addLog('error', `Falha ao deletar: ${errData.error}`);
        alert(`Erro ao deletar: ${errData.error}`);
      }
    } catch (err) {
      addLog('error', `Erro ao deletar: ${err.message}`);
    }
  };

  const handleCloseTab = (filePath, e) => {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    
    if (selectedFile === filePath) {
      setFileContents(prev => ({ ...prev, [filePath]: fileContent }));
    }

    setOpenFiles(prev => {
      const remaining = prev.filter(f => f !== filePath);
      
      if (selectedFile === filePath) {
        if (remaining.length > 0) {
          const nextActive = remaining[remaining.length - 1];
          setSelectedFile(nextActive);
          setFileContent(fileContents[nextActive] || '');
        } else {
          setSelectedFile(null);
          setFileContent('');
        }
      }
      return remaining;
    });
  };

  const handleFileSelect = async (filePath) => {
    if (!activeProject) return;
    
    if (selectedFile) {
      setFileContents(prev => ({ ...prev, [selectedFile]: fileContent }));
    }

    setOpenFiles(prev => {
      if (!prev.includes(filePath)) {
        return [...prev, filePath];
      }
      return prev;
    });
    
    setSelectedFile(filePath);

    if (fileContents[filePath] !== undefined) {
      setFileContent(fileContents[filePath]);
      return;
    }

    try {
      const res = await fetch(`/api/file/read?projectPath=${encodeURIComponent(activeProject.project_path)}&filePath=${encodeURIComponent(filePath)}`);
      if (res.ok) {
        const data = await res.json();
        setFileContent(data.content);
        setFileContents(prev => ({ ...prev, [filePath]: data.content }));
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
        setFileContents(prev => ({ ...prev, [selectedFile]: fileContent }));
        fetchGitStatus();
        fetchProblems();
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

  const openEditModal = (e, proj) => {
    e.stopPropagation();
    setEditingProject({
      name: proj.name,
      project_name: proj.project_name || proj.name,
      project_path: proj.project_path || '',
      model: proj.model || '',
      alternative_model: proj.alternative_model || '',
      mode: proj.mode || 'auto',
      description: proj.description || '',
    });
  };

  const handleUpdateProject = async (e) => {
    e.preventDefault();
    if (!editingProject) return;
    try {
      const res = await fetch('/api/opalacoder/update-project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_name: editingProject.name,
          display_name: editingProject.project_name,
          project_path: editingProject.project_path,
          model: editingProject.model,
          alternative_model: editingProject.alternative_model,
          mode: editingProject.mode,
          description: editingProject.description,
        })
      });
      if (res.ok) {
        const updated = await res.json();
        addLog('info', `Projeto '${updated.project_name}' atualizado.`);
        setEditingProject(null);
        // Refresh project list and update active project if it was the edited one
        await fetchProjects();
        if (activeProject && activeProject.name === updated.name) {
          setActiveProject(prev => ({ ...prev, ...updated }));
        }
      } else {
        const err = await res.json();
        addLog('error', `Erro ao atualizar: ${err.error}`);
      }
    } catch (err) {
      addLog('error', `Erro ao atualizar projeto: ${err.message}`);
    }
  };

  const addLog = (type, message) => {
    setTerminalLogs(prev => [...prev, { type, message, timestamp: new Date().toLocaleTimeString() }]);
  };

  const selectTab = (tab) => {
    setActiveBottomTab(tab);
    if (isTerminalCollapsed) {
      setIsTerminalCollapsed(false);
    }
  };


  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    if (!chatInput.trim() || !activeProject || isAgentRunning) return;

    const userText = chatInput;
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: userText }]);
    setIsAgentRunning(true);
    setProblems([]);
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
      setChatMessages(prev => [...prev, { role: 'assistant', content: `🔴 Falha na execução: ${err.message}` }]);
    } finally {
      setIsAgentRunning(false);
      fetchFiles();
      fetchProblems();
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
        setChatMessages(prev => [...prev, { role: 'assistant', content: `🔴 Erro do Agente: ${data.message}` }]);
        break;
      case 'problem':
        addLog('error', `[Problema em ${data.tool}]: ${data.message}`);
        setProblems(prev => [
          ...prev, 
          {
            id: Math.random().toString(),
            tool: data.tool,
            message: data.message,
            severity: data.severity || 'error',
            timestamp: new Date().toLocaleTimeString()
          }
        ]);
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
              style={{ position: 'relative' }}
            >
              <GitBranch size={22} />
              {gitChanges.length > 0 && (
                <span style={{
                  position: 'absolute',
                  top: '4px',
                  right: '4px',
                  background: '#007acc',
                  color: '#ffffff',
                  borderRadius: '50%',
                  width: '16px',
                  height: '16px',
                  fontSize: '9px',
                  fontWeight: 'bold',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 0 4px rgba(0,0,0,0.5)'
                }}>
                  {gitChanges.length}
                </span>
              )}
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
            <button 
              onClick={() => setIsSettingsOpen(true)}
              className="vscode-activitybar-btn" 
              title="Settings"
            >
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
                        {/* Settings (edit) button */}
                        <button 
                          onClick={(e) => openEditModal(e, p)}
                          style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0', padding: '2px 4px' }}
                          title="Configurar projeto"
                        >
                          <Settings size={12} />
                        </button>
                        {/* Delete button */}
                        <button 
                          onClick={(e) => { e.stopPropagation(); handleDeleteProject(p.name); }}
                          style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0', padding: '2px 4px' }}
                          title="Remover projeto"
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
                        handleNodeContextMenu={handleNodeContextMenu}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="vscode-sidebar-content" style={{ padding: '12px', display: 'flex', flexDirection: 'column', height: '100%', gap: '16px' }}>
              <div className="vscode-sidebar-title">SOURCE CONTROL (GIT)</div>
              
              {!activeProject ? (
                <div style={{ fontSize: '12px', color: '#808080', fontStyle: 'italic' }}>
                  Selecione um projeto para ver as alterações Git.
                </div>
              ) : gitChanges.length === 0 ? (
                <div style={{ fontSize: '12px', color: '#808080', fontStyle: 'italic' }}>
                  Sem alterações locais.
                </div>
              ) : (
                <div className="flex flex-col flex-1 overflow-hidden" style={{ gap: '16px' }}>
                  {/* Commit message input */}
                  <form onSubmit={handleGitCommit} className="flex flex-col" style={{ gap: '8px' }}>
                    <input 
                      type="text" 
                      placeholder="Mensagem do Commit..."
                      value={commitMessage}
                      onChange={(e) => setCommitMessage(e.target.value)}
                      required
                      style={{ width: '100%', fontSize: '12px' }}
                    />
                    <button 
                      type="submit" 
                      className="vscode-button"
                      disabled={isCommitting || !commitMessage.trim()}
                      style={{ width: '100%' }}
                    >
                      {isCommitting ? 'Commit...' : 'Commit'}
                    </button>
                  </form>

                  {/* Changes list */}
                  <div className="flex-1 overflow-y-auto" style={{ borderTop: '1px solid var(--vscode-border)', paddingTop: '12px' }}>
                    <div className="vscode-sidebar-section-title" style={{ marginBottom: '8px', padding: 0 }}>Modificações ({gitChanges.length})</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {gitChanges.map((change, i) => {
                        let statusColor = '#cccccc';
                        let statusLabel = change.status;
                        
                        if (change.status === 'M') {
                          statusColor = '#e2b52b'; // Yellow
                          statusLabel = 'M';
                        } else if (change.status === '??' || change.status === 'A') {
                          statusColor = '#73c991'; // Green
                          statusLabel = 'U';
                        } else if (change.status === 'D') {
                          statusColor = '#f48771'; // Red
                          statusLabel = 'D';
                        }

                        return (
                          <div 
                            key={i} 
                            style={{ 
                              display: 'flex', 
                              justifyContent: 'space-between', 
                              alignItems: 'center', 
                              fontSize: '12px', 
                              padding: '4px 6px',
                              borderRadius: '3px',
                              background: 'rgba(255,255,255,0.02)'
                            }}
                          >
                            <span 
                              className="truncate" 
                              title={change.path}
                              style={{ color: '#cccccc', flex: 1, marginRight: '8px' }}
                            >
                              {change.path}
                            </span>
                            <span 
                              style={{ 
                                fontWeight: 'bold', 
                                color: statusColor, 
                                fontSize: '11px', 
                                minWidth: '12px', 
                                textAlign: 'center' 
                              }}
                            >
                              {statusLabel}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
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
                  path={selectedFile}
                  language={getLanguage(selectedFile)}
                  theme={theme === 'light' ? 'light' : 'vs-dark'}
                  value={fileContent}
                  onChange={(val) => setFileContent(val)}
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
                <span 
                  className={`vscode-bottom-tab ${activeBottomTab === 'output' ? 'active' : ''}`}
                  onClick={() => selectTab('output')}
                >
                  OUTPUT (OPALACODER)
                </span>
                <span 
                  className={`vscode-bottom-tab ${activeBottomTab === 'problems' ? 'active' : ''}`}
                  onClick={() => selectTab('problems')}
                >
                  PROBLEMS {problems.length > 0 && <span style={{ marginLeft: '4px', background: '#f48771', color: '#1e1e1e', borderRadius: '10px', padding: '0 6px', fontSize: '10px', fontWeight: 'bold' }}>{problems.length}</span>}
                </span>
                <span 
                  className={`vscode-bottom-tab ${activeBottomTab === 'terminal' ? 'active' : ''}`}
                  onClick={() => selectTab('terminal')}
                >
                  TERMINAL
                </span>
              </div>
              <div className="flex items-center" style={{ gap: '8px' }}>
                {(activeBottomTab === 'output' || activeBottomTab === 'problems') && (
                  <button 
                    onClick={activeBottomTab === 'output' ? () => setTerminalLogs([]) : () => setProblems([])}
                    className="vscode-bottom-panel-clear-btn"
                    title={activeBottomTab === 'output' ? 'Limpar Output' : 'Limpar Problemas'}
                  >
                    <Trash size={12} />
                    <span>Clear</span>
                  </button>
                )}
                <button 
                  onClick={() => setIsTerminalCollapsed(!isTerminalCollapsed)}
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
                >
                  {isTerminalCollapsed ? <Maximize2 size={12} /> : <Minimize2 size={12} />}
                </button>
              </div>
            </div>
            
            {!isTerminalCollapsed && (
              <div style={{ height: 'calc(100% - 30px)', width: '100%' }}>
                {activeBottomTab === 'output' && (
                  <div className="vscode-logs" style={{ height: '100%' }}>
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

                {activeBottomTab === 'problems' && (
                  <div className="vscode-problems-list" style={{ padding: '8px', overflowY: 'auto', height: '100%', color: '#cccccc', fontFamily: 'Consolas, monospace', fontSize: '12px' }}>
                    {problems.length === 0 ? (
                      <div style={{ color: '#808080', fontStyle: 'italic', padding: '8px' }}>Nenhum problema detectado.</div>
                    ) : (
                      problems.map((prob) => (
                        <div key={prob.id} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', borderBottom: '1px solid #2d2d2d', padding: '6px 0' }}>
                          <AlertCircle size={14} className="text-[#f48771]" style={{ flexShrink: 0, marginTop: '2px' }} />
                          <div>
                            <div style={{ fontWeight: 'bold', color: '#f48771', marginBottom: '2px' }}>
                              [{prob.timestamp}] Erro em {prob.tool}:
                            </div>
                            <pre style={{ whiteSpace: 'pre-wrap', margin: 0, color: '#e0e0e0', fontSize: '12px', fontFamily: 'inherit' }}>
                              {prob.message}
                            </pre>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}

                <div style={{ display: activeBottomTab === 'terminal' ? 'block' : 'none', height: '100%', background: '#1e1e1e', overflow: 'hidden' }}>
                  {!activeProject ? (
                    <div style={{ color: '#808080', fontStyle: 'italic', padding: '16px' }}>Defina um projeto/workspace para habilitar o terminal.</div>
                  ) : (
                    <div ref={terminalRef} style={{ width: '100%', height: '100%', padding: '4px' }} />
                  )}
                </div>
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

      {/* Prompt for optional dependencies on startup */}
      {showInstallPrompt && (
        <div className="vscode-modal-overlay">
          <div className="vscode-modal" style={{ maxWidth: '440px', width: '90%' }}>
            <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
              <span className="vscode-sidebar-title" style={{ color: '#ffffff' }}>MÓDULOS OPCIONAIS REQUERIDOS</span>
              <button 
                onClick={() => setShowInstallPrompt(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
              >
                <X size={14} />
              </button>
            </div>
            <div style={{ padding: '16px', color: '#cccccc', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <p style={{ fontSize: '13px', lineHeight: '1.5' }}>
                Os módulos opcionais para embeddings offline (<code>sentence-transformers</code>) não foram encontrados no ambiente.
              </p>
              <p style={{ fontSize: '12px', color: '#888888', lineHeight: '1.4' }}>
                Recomendamos a instalação para habilitar o processamento local de vetores e a indexação de código sem depender de APIs externas.
              </p>
              
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px', borderTop: '1px solid #3c3c3c', paddingTop: '12px' }}>
                <button 
                  onClick={() => setShowInstallPrompt(false)}
                  className="vscode-button"
                  style={{ backgroundColor: '#3c3c3c', color: '#ffffff' }}
                >
                  Ignorar
                </button>
                <button 
                  onClick={() => {
                    setShowInstallPrompt(false);
                    setIsSettingsOpen(true);
                    setSettingsTab('preferences');
                    handleInstallOptionalDeps();
                  }}
                  className="vscode-button"
                >
                  Instalar Agora
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

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
            onClick={() => {
              const p = rightClickedNode
                ? (rightClickedNode.isDirectory ? rightClickedNode.path : rightClickedNode.path.split('/').slice(0, -1).join('/'))
                : '';
              handleCreateNewFile(p);
            }}
          >
            <Plus size={13} style={{ color: '#007acc' }} />
            <span>New File...</span>
          </div>
          {rightClickedNode && (
            <>
              <div 
                className="vscode-context-menu-item"
                onClick={() => handleRenameNode(rightClickedNode)}
              >
                <Edit2 size={13} style={{ color: '#e2b52b' }} />
                <span>Rename...</span>
              </div>
              <div 
                className="vscode-context-menu-item"
                onClick={() => handleDeleteNode(rightClickedNode)}
              >
                <Trash2 size={13} style={{ color: '#f48771' }} />
                <span>Delete</span>
              </div>
            </>
          )}
        </div>
      )}

      {/* Project Settings Edit Modal */}
      {editingProject && (
        <div className="vscode-modal-overlay">
          <div className="vscode-modal" style={{ maxWidth: '520px', width: '92%' }}>
            {/* Header */}
            <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
              <span className="vscode-sidebar-title" style={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Settings size={14} style={{ color: '#007acc' }} />
                CONFIGURAÇÕES DO PROJETO
              </span>
              <button
                onClick={() => setEditingProject(null)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
              >
                <X size={14} />
              </button>
            </div>

            <form onSubmit={handleUpdateProject} className="flex flex-col" style={{ padding: '16px', gap: '14px' }}>
              {/* Internal key (read-only) */}
              <div className="flex flex-col" style={{ gap: '4px' }}>
                <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>ID Interno (somente leitura)</label>
                <input type="text" value={editingProject.name} readOnly
                  style={{ opacity: 0.5, cursor: 'not-allowed' }} />
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
                <input
                  type="text"
                  value={editingProject.project_path}
                  onChange={e => setEditingProject(p => ({ ...p, project_path: e.target.value }))}
                  placeholder="/caminho/absoluto/do/projeto"
                />
              </div>

              {/* Model + mode side by side */}
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
                  <select
                    value={editingProject.mode}
                    onChange={e => setEditingProject(p => ({ ...p, mode: e.target.value }))}
                  >
                    <option value="auto">Auto (Completo)</option>
                    <option value="plan">Plan (Planejar)</option>
                    <option value="edit">Edit (Editar)</option>
                  </select>
                </div>
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

              {/* Actions */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', paddingTop: '12px', borderTop: '1px solid #3c3c3c', marginTop: '4px' }}>
                <button
                  type="button"
                  onClick={() => setEditingProject(null)}
                  className="vscode-button"
                  style={{ backgroundColor: '#3c3c3c', color: '#ffffff' }}
                >
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

      {/* IDE Global Settings Modal */}
      {isSettingsOpen && (
        <div className="vscode-modal-overlay">
          <div className="vscode-modal" style={{ maxWidth: '440px', width: '90%' }}>
            {/* Header */}
            <div className="vscode-sidebar-header" style={{ padding: '10px 16px' }}>
              <span className="vscode-sidebar-title" style={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Settings size={14} style={{ color: '#007acc' }} />
                CONFIGURAÇÕES DA IDE
              </span>
              <button
                onClick={() => setIsSettingsOpen(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#a0a0a0' }}
              >
                <X size={14} />
              </button>
            </div>

            {/* Tab selector */}
            <div style={{ display: 'flex', borderBottom: '1px solid var(--vscode-border)', backgroundColor: 'var(--vscode-tab-inactive-bg)' }}>
              <button 
                onClick={() => setSettingsTab('preferences')}
                style={{
                  flex: 1,
                  padding: '8px',
                  background: settingsTab === 'preferences' ? 'var(--vscode-tab-active-bg)' : 'transparent',
                  border: 'none',
                  borderBottom: settingsTab === 'preferences' ? '2px solid var(--vscode-active-border)' : 'none',
                  color: settingsTab === 'preferences' ? '#ffffff' : '#808080',
                  fontWeight: 'bold',
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  cursor: 'pointer'
                }}
              >
                Preferências
              </button>
              <button 
                onClick={() => setSettingsTab('about')}
                style={{
                  flex: 1,
                  padding: '8px',
                  background: settingsTab === 'about' ? 'var(--vscode-tab-active-bg)' : 'transparent',
                  border: 'none',
                  borderBottom: settingsTab === 'about' ? '2px solid var(--vscode-active-border)' : 'none',
                  color: settingsTab === 'about' ? '#ffffff' : '#808080',
                  fontWeight: 'bold',
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  cursor: 'pointer'
                }}
              >
                Sobre
              </button>
            </div>

            <div className="flex flex-col" style={{ padding: '16px', gap: '14px' }}>
              {settingsTab === 'preferences' ? (
                <>
                  {/* Tema Visual */}
                  <div className="flex flex-col" style={{ gap: '6px' }}>
                    <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Tema de Cor</label>
                    <select 
                      value={theme} 
                      onChange={(e) => setTheme(e.target.value)}
                      style={{ width: '100%' }}
                    >
                      <option value="dark">Escuro (Dark Mode)</option>
                      <option value="light">Claro (Light Mode)</option>
                    </select>
                  </div>

                  {/* Tamanho da Fonte */}
                  <div className="flex flex-col" style={{ gap: '6px' }}>
                    <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Tamanho da Fonte do Editor</label>
                    <input 
                      type="number" 
                      min="10" 
                      max="30"
                      value={editorFontSize} 
                      onChange={(e) => {
                        const val = Number(e.target.value);
                        setEditorFontSize(val);
                        safeSetLocalStorage('editorFontSize', val);
                      }}
                      style={{ width: '100%' }}
                    />
                  </div>

                  {/* Tab Size */}
                  <div className="flex flex-col" style={{ gap: '6px' }}>
                    <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Tamanho do Tab (Espaços)</label>
                    <select 
                      value={editorTabSize} 
                      onChange={(e) => {
                        const val = Number(e.target.value);
                        setEditorTabSize(val);
                        safeSetLocalStorage('editorTabSize', val);
                      }}
                      style={{ width: '100%' }}
                    >
                      <option value={2}>2 Espaços</option>
                      <option value={4}>4 Espaços</option>
                      <option value={8}>8 Espaços</option>
                    </select>
                  </div>

                  {/* Word Wrap */}
                  <div className="flex flex-col" style={{ gap: '6px' }}>
                    <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Quebra Automática de Linha (Word Wrap)</label>
                    <select 
                      value={editorWordWrap} 
                      onChange={(e) => {
                        setEditorWordWrap(e.target.value);
                        safeSetLocalStorage('editorWordWrap', e.target.value);
                      }}
                      style={{ width: '100%' }}
                    >
                      <option value="on">Ativado (On)</option>
                      <option value="off">Desativado (Off)</option>
                    </select>
                  </div>

                  {/* Optional Dependencies */}
                  <div className="flex flex-col" style={{ gap: '6px', borderTop: '1px solid var(--vscode-border)', paddingTop: '12px', marginTop: '6px' }}>
                    <label className="vscode-sidebar-section-title" style={{ padding: 0 }}>Dependências Opcionais</label>
                    <span style={{ fontSize: '11px', color: '#888888', lineHeight: '1.4' }}>
                      Instale recursos extras (Local Embeddings, PyTorch, CUDA, etc.) que otimizam o processamento off-line.
                    </span>
                    <button
                      type="button"
                      className="vscode-button"
                      disabled={isInstallingDeps}
                      onClick={handleInstallOptionalDeps}
                      style={{ width: '100%', marginTop: '6px' }}
                    >
                      {isInstallingDeps ? 'Instalando...' : 'Instalar Recursos Opcionais'}
                    </button>
                    {installDepsStatus && (
                      <span style={{ fontSize: '11px', fontWeight: 'bold', color: installDepsStatus.includes('Erro') || installDepsStatus.includes('Falha') ? '#f48771' : '#73c991', marginTop: '4px' }}>
                        Status: {installDepsStatus}
                      </span>
                    )}
                    {installDepsLog && (
                      <textarea
                        readOnly
                        value={installDepsLog}
                        style={{
                          width: '100%',
                          height: '80px',
                          marginTop: '8px',
                          fontSize: '10px',
                          fontFamily: 'monospace',
                          background: '#151515',
                          color: '#89d4a5',
                          border: '1px solid var(--vscode-border)',
                          padding: '6px',
                          resize: 'none'
                        }}
                      />
                    )}
                  </div>
                </>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', color: '#cccccc' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span className="vscode-sidebar-section-title" style={{ padding: 0 }}>Versão</span>
                    <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#ffffff' }}>0.1.19 alfa</span>
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
              <button 
                onClick={() => setIsSettingsOpen(false)}
                className="vscode-button"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Subcomponente de nó de arquivo para respeitar as Regras de Hooks
function FileNode({ node, selectedFile, handleFileSelect, handleNodeContextMenu }) {
  const isDir = node.isDirectory;
  const [isOpen, setIsOpen] = useState(false);

  if (isDir) {
    return (
      <div className="select-none">
        <div 
          onClick={() => setIsOpen(!isOpen)} 
          className="vscode-tree-node"
          onContextMenu={(e) => handleNodeContextMenu(e, node)}
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
                handleNodeContextMenu={handleNodeContextMenu}
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
      onContextMenu={(e) => handleNodeContextMenu(e, node)}
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
