import React, { useState, useEffect, useRef } from 'react';
import '@xterm/xterm/css/xterm.css';
import { useTranslation } from 'react-i18next';
import i18n from './i18n/index.js';

// Utils
import { safeGetLocalStorage, safeSetLocalStorage } from './utils/storage';

// Hooks
import { useResizing } from './hooks/useResizing';
import { useTerminal } from './hooks/useTerminal';

// Layout components
import ActivityBar from './components/ActivityBar';
import StatusBar from './components/StatusBar';
import ExplorerSidebar from './components/ExplorerSidebar';
import GitSidebar from './components/GitSidebar';
import EditorPanel from './components/EditorPanel';
import ChatPanel from './components/ChatPanel';
import BottomPanel from './components/BottomPanel';
import ContextMenu from './components/ContextMenu';

// Modals
import InstallDepsPrompt from './components/modals/InstallDepsPrompt';
import NewProjectModal from './components/modals/NewProjectModal';
import EditProjectModal from './components/modals/EditProjectModal';
import SettingsModal from './components/modals/SettingsModal';
import ConfirmModal from './components/modals/ConfirmModal';
import DirPickerModal from './components/modals/DirPickerModal';

// ─────────────────────────────────────────────────────────────────────────────
// App
// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  const { t } = useTranslation();

  // ── Projects / files ──────────────────────────────────────────────────────
  const [projects, setProjects] = useState([]);
  const [activeProject, setActiveProject] = useState(null);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');
  const [openFiles, setOpenFiles] = useState([]);
  const [fileContents, setFileContents] = useState({});
  const [rightClickedNode, setRightClickedNode] = useState(null);
  const [isSaving, setIsSaving] = useState(false);

  // ── Chat / agent ──────────────────────────────────────────────────────────
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [isAgentRunning, setIsAgentRunning] = useState(false);
  const [isInlineRunning, setIsInlineRunning] = useState(false);

  // ── Bottom panel ──────────────────────────────────────────────────────────
  const [terminalLogs, setTerminalLogs] = useState([]);
  const [problems, setProblems] = useState([]);
  const [thinkingLogs, setThinkingLogs] = useState([]);
  const [isTerminalCollapsed, setIsTerminalCollapsed] = useState(false);
  const [activeBottomTab, setActiveBottomTab] = useState('output');

  // ── UI state ──────────────────────────────────────────────────────────────
  const [isChatVisible, setIsChatVisible] = useState(true);
  const [activeSidebarTab, setActiveSidebarTab] = useState('explorer');
  const [contextMenu, setContextMenu] = useState(null);
  const [showAdvancedParams, setShowAdvancedParams] = useState(false);
  const [modelConfigMsg, setModelConfigMsg] = useState('');
  const [dirPicker, setDirPicker] = useState(null);

  // ── Git ───────────────────────────────────────────────────────────────────
  const [gitChanges, setGitChanges] = useState([]);
  const [commitMessage, setCommitMessage] = useState('');
  const [isCommitting, setIsCommitting] = useState(false);

  // ── Drag-and-drop ─────────────────────────────────────────────────────────
  const [draggedNode, setDraggedNode] = useState(null);
  const [dragOverPath, setDragOverPath] = useState(null);

  // ── Panel sizing ──────────────────────────────────────────────────────────
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [chatWidth, setChatWidth] = useState(320);
  const [bottomPanelHeight, setBottomPanelHeight] = useState(240);
  const [isEditorMaximized, setIsEditorMaximized] = useState(false);
  const [isBottomMaximized, setIsBottomMaximized] = useState(false);

  // ── Modals ─────────────────────────────────────────────────────────────────
  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [newProjName, setNewProjName] = useState('');
  const [newProjPath, setNewProjPath] = useState('');
  const [newProjDesc, setNewProjDesc] = useState('');
  const [newProjModel, setNewProjModel] = useState('gemini/gemini-2.5-flash');
  const [newProjMode, setNewProjMode] = useState('auto');
  const [newProjModelParams, setNewProjModelParams] = useState({});
  const [newProjApiKey, setNewProjApiKey] = useState('');
  const [newProjApiBase, setNewProjApiBase] = useState('http://localhost:11434/v1');
  const [newProjError, setNewProjError] = useState('');

  const [editingProject, setEditingProject] = useState(null);
  const [confirmRequest, setConfirmRequest] = useState(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [webSearchConfig, setWebSearchConfig] = useState({ enabled: true, mcp_url: '', mcp_tool: 'web_search' });
  const [showInstallPrompt, setShowInstallPrompt] = useState(false);

  // ── IDE settings ──────────────────────────────────────────────────────────
  const [settingsTab, setSettingsTab] = useState('preferences');
  const [theme, setTheme] = useState(() => safeGetLocalStorage('theme', 'dark'));
  const [editorFontSize, setEditorFontSize] = useState(() => Number(safeGetLocalStorage('editorFontSize', 13)));
  const [editorTabSize, setEditorTabSize] = useState(() => Number(safeGetLocalStorage('editorTabSize', 4)));
  const [editorWordWrap, setEditorWordWrap] = useState(() => safeGetLocalStorage('editorWordWrap', 'on'));

  // ── Optional dependencies ─────────────────────────────────────────────────
  const [isInstallingDeps, setIsInstallingDeps] = useState(false);
  const [installDepsStatus, setInstallDepsStatus] = useState('');
  const [installDepsLog, setInstallDepsLog] = useState('');

  // ── Ephemeral Agent Params ────────────────────────────────────────────────
  const [ephemeralParams, setEphemeralParams] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ephemeralParams')) || {}; } catch { return {}; }
  });

  // ── Inline prompt (editor Ctrl+L / context-menu actions) ────────────────
  const [inlinePrompt, setInlinePrompt] = useState(null);
  // Stores the Monaco range that should be replaced after an inline agent reply
  const pendingInlineRangeRef = useRef(null);

  // ── Refs ──────────────────────────────────────────────────────────────────
  const terminalRef = useRef(null);
  const terminalInstanceRef = useRef(null);
  const fitAddonRef = useRef(null);
  const eventSourceRef = useRef(null);
  const chatEndRef = useRef(null);
  const logEndRef = useRef(null);
  const editorRef = useRef(null);
  const monacoRef = useRef(null);
  const saveFileRef = useRef(null);

  // ── Hooks ─────────────────────────────────────────────────────────────────
  const { startResizing } = useResizing({ setSidebarWidth, setChatWidth, setBottomPanelHeight, sidebarWidth, chatWidth, bottomPanelHeight });

  useTerminal({ activeProject, terminalRef, terminalInstanceRef, fitAddonRef, eventSourceRef, activeBottomTab, bottomPanelHeight });

  // ── Effects ───────────────────────────────────────────────────────────────
  useEffect(() => { fetchProjects(); }, []);

  useEffect(() => {
    fetch('/api/settings/web-search')
      .then(r => r.ok ? r.json() : null)
      .then(cfg => { if (cfg) setWebSearchConfig(cfg); })
      .catch(() => { });
  }, []);

  // Restore language from backend on startup (localStorage not reliable in webview)
  useEffect(() => {
    fetch('/api/settings/language')
      .then(r => r.ok ? r.json() : null)
      .then(cfg => {
        if (cfg?.lang) {
          i18n.changeLanguage(cfg.lang);
        } else {
          // No saved preference — push current detected language to backend
          const detected = i18n.language?.startsWith('pt') ? 'pt' : 'en';
          fetch('/api/settings/language', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lang: detected }),
          }).catch(() => { });
        }
      })
      .catch(() => { });
  }, []);

  useEffect(() => {
    if (!editingProject) setShowAdvancedParams(false);
  }, [editingProject]);

  useEffect(() => {
    if (!showNewProjectModal) setNewProjError('');
  }, [showNewProjectModal]);

  // Track the name of the last project for which chat was initialised, so that
  // re-rendering the same project (e.g. after saving its settings) does NOT wipe
  // the chat history. Messages are only reset when switching to a DIFFERENT project.
  const prevProjectNameRef = useRef(null);

  useEffect(() => {
    if (activeProject) {
      fetchFiles();
      fetchProblems();
      if (prevProjectNameRef.current !== activeProject.name) {
        setChatMessages([
          { role: 'assistant', content: t('app.greeting', { projectName: activeProject.project_name || activeProject.name }) }
        ]);
        prevProjectNameRef.current = activeProject.name;
      }
    } else {
      setFiles([]);
      setSelectedFile(null);
      setFileContent('');
      setOpenFiles([]);
      setFileContents({});
      setProblems([]);
      prevProjectNameRef.current = null;
    }
  }, [activeProject]);

  useEffect(() => {
    const disableContextMenu = (e) => e.preventDefault();
    const closeMenu = () => setContextMenu(null);
    document.addEventListener('contextmenu', disableContextMenu);
    document.addEventListener('click', closeMenu);
    return () => {
      document.removeEventListener('contextmenu', disableContextMenu);
      document.removeEventListener('click', closeMenu);
    };
  }, []);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatMessages]);
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [terminalLogs]);

  // Global keyboard shortcuts (Ctrl+S, Ctrl+/- zoom)
  useEffect(() => {
    const handleKeyDown = (e) => {
      const isCtrl = e.ctrlKey || e.metaKey;
      if (isCtrl && e.key === 's') { e.preventDefault(); saveFile(); }
      else if (isCtrl && (e.key === '+' || e.key === '=' || e.code === 'Equal' || e.code === 'NumpadAdd')) {
        e.preventDefault();
        setEditorFontSize(prev => { const v = Math.min(30, prev + 1); safeSetLocalStorage('editorFontSize', v); return v; });
      } else if (isCtrl && (e.key === '-' || e.code === 'Minus' || e.code === 'NumpadSubtract')) {
        e.preventDefault();
        setEditorFontSize(prev => { const v = Math.max(10, prev - 1); safeSetLocalStorage('editorFontSize', v); return v; });
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedFile, fileContent, activeProject]);

  useEffect(() => {
    safeSetLocalStorage('theme', theme);
    if (theme === 'light') document.body.classList.add('light-theme');
    else document.body.classList.remove('light-theme');
  }, [theme]);

  useEffect(() => {
    if (activeProject) fetchGitStatus();
    else setGitChanges([]);
  }, [activeProject]);

  useEffect(() => {
    if (!activeProject) return;
    const interval = setInterval(() => { fetchFiles(); fetchGitStatus(); }, 10000);
    return () => clearInterval(interval);
  }, [activeProject]);

  useEffect(() => {
    if (activeSidebarTab === 'git' && activeProject) fetchGitStatus();
  }, [activeSidebarTab, activeProject]);

  // Un-maximize editor if all files are closed
  useEffect(() => {
    if (openFiles.length === 0 && isEditorMaximized) {
      setIsEditorMaximized(false);
    }
  }, [openFiles, isEditorMaximized]);

  // ── Helpers ───────────────────────────────────────────────────────────────
  const addLog = (type, message) =>
    setTerminalLogs(prev => {
      if (prev.length > 0) {
        const last = prev[prev.length - 1];
        if (last.type === type && (type === 'thought' || type === 'stdout' || type === 'stderr')) {
          return [
            ...prev.slice(0, -1),
            { ...last, message: last.message + message }
          ];
        }
      }
      return [...prev, { type, message, timestamp: new Date().toLocaleTimeString() }];
    });

  // ── API calls ─────────────────────────────────────────────────────────────
  const fetchProjects = async () => {
    try {
      const res = await fetch('/api/opalacoder/list-projects');
      if (res.ok) {
        const data = await res.json();
        setProjects(data.projects || []);
        if (data.projects?.length > 0 && !activeProject) handleSelectProject(data.projects[0]);
      }
    } catch (err) { addLog('error', t('app.failedToLoadProjects', { error: err.message })); }
  };

  const fetchFiles = async () => {
    if (!activeProject) return;
    try {
      const res = await fetch(`/api/files?projectPath=${encodeURIComponent(activeProject.project_path)}`);
      if (res.ok) { const data = await res.json(); setFiles(data.files || []); }
      else { const e = await res.json(); addLog('error', t('app.failedToListFiles', { error: e.error })); }
    } catch (err) { addLog('error', t('app.fileCallError', { error: err.message })); }
  };

  const fetchProblems = async () => {
    if (!activeProject) return;
    try {
      const res = await fetch(`/api/opalacoder/problems?projectPath=${encodeURIComponent(activeProject.project_path)}`);
      if (res.ok) { const data = await res.json(); setProblems(data.problems || []); }
    } catch (err) { console.error('Failed to fetch problems', err); }
  };

  const fetchGitStatus = async () => {
    if (!activeProject) return;
    try {
      const res = await fetch(`/api/git/status?projectPath=${encodeURIComponent(activeProject.project_path)}`);
      if (res.ok) { const data = await res.json(); setGitChanges(data.files || []); }
    } catch (err) { console.error('Failed to fetch git status', err); }
  };

  const handleSelectProject = (proj) => {
    setActiveProject(proj);
    addLog('info', t('app.projectSelected', { name: proj.project_name || proj.name }));
  };

  const handleGitCommit = async (e) => {
    if (e) e.preventDefault();
    if (!activeProject || !commitMessage.trim() || isCommitting) return;
    setIsCommitting(true);
    addLog('info', t('app.commitCreating', { message: commitMessage }));
    try {
      const res = await fetch('/api/git/commit', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectPath: activeProject.project_path, message: commitMessage }),
      });
      if (res.ok) { addLog('info', t('app.commitSuccess')); setCommitMessage(''); fetchGitStatus(); }
      else { const data = await res.json(); addLog('error', t('app.commitFailed', { error: data.error || t('app.unknownError') })); }
    } catch (err) { addLog('error', t('app.commitError', { error: err.message })); }
    finally { setIsCommitting(false); }
  };

  const handleStageFile = async (filePath) => {
    if (!activeProject) return;
    try {
      await fetch('/api/git/stage', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectPath: activeProject.project_path, filePath, action: 'stage' }),
      });
      fetchGitStatus();
    } catch (err) { addLog('error', t('app.stageError', { error: err.message })); }
  };

  const handleUnstageFile = async (filePath) => {
    if (!activeProject) return;
    try {
      await fetch('/api/git/stage', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectPath: activeProject.project_path, filePath, action: 'unstage' }),
      });
      fetchGitStatus();
    } catch (err) { addLog('error', t('app.unstageError', { error: err.message })); }
  };

  const handleDiscardFile = async (filePath) => {
    if (!activeProject) return;
    try {
      const res = await fetch('/api/git/discard', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectPath: activeProject.project_path, filePath }),
      });
      if (res.ok) { addLog('info', `Alterações descartadas: ${filePath}`); fetchGitStatus(); fetchFiles(); }
      else { const d = await res.json(); addLog('error', `Erro ao descartar: ${d.error}`); }
    } catch (err) { addLog('error', `Erro ao descartar alterações: ${err.message}`); }
  };

  const handleInstallOptionalDeps = async () => {
    if (isInstallingDeps) return;
    setIsInstallingDeps(true);
    setInstallDepsStatus('Instalando...');
    setInstallDepsLog('Iniciando pip install...\n');
    try {
      const response = await fetch('/api/settings/install-dependencies', { method: 'POST' });
      if (!response.ok) throw new Error('Falha ao iniciar instalação');
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
            if (data.output) setInstallDepsLog(prev => prev + data.output);
            if (data.status === 'success') setInstallDepsStatus('Instalado com Sucesso!');
            else if (data.status === 'error') setInstallDepsStatus('Erro na Instalação');
          } catch (e) { /* ignore chunk parsing errors */ }
        }
      }
    } catch (err) {
      setInstallDepsStatus('Falha ao conectar');
      setInstallDepsLog(prev => prev + `\nErro: ${err.message}\n`);
    } finally { setIsInstallingDeps(false); }
  };

  // ── File operations ────────────────────────────────────────────────────────
  const handleFileSelect = async (filePath) => {
    if (!activeProject) return;
    if (selectedFile) setFileContents(prev => ({ ...prev, [selectedFile]: fileContent }));
    setOpenFiles(prev => prev.includes(filePath) ? prev : [...prev, filePath]);
    setSelectedFile(filePath);
    if (fileContents[filePath] !== undefined) { setFileContent(fileContents[filePath]); return; }
    try {
      const res = await fetch(`/api/file/read?projectPath=${encodeURIComponent(activeProject.project_path)}&filePath=${encodeURIComponent(filePath)}`);
      if (res.ok) { const data = await res.json(); setFileContent(data.content); setFileContents(prev => ({ ...prev, [filePath]: data.content })); }
      else addLog('error', `Erro ao ler arquivo: ${filePath}`);
    } catch (err) { addLog('error', `Erro de leitura: ${err.message}`); }
  };

  const saveFile = async () => {
    if (!activeProject || !selectedFile) return;
    setIsSaving(true);
    try {
      const res = await fetch('/api/file/write', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectPath: activeProject.project_path, filePath: selectedFile, content: fileContent }),
      });
      if (res.ok) { addLog('info', `Arquivo salvo: ${selectedFile}`); setFileContents(prev => ({ ...prev, [selectedFile]: fileContent })); fetchGitStatus(); fetchProblems(); }
      else addLog('error', `Erro ao salvar arquivo: ${selectedFile}`);
    } catch (err) { addLog('error', `Erro de escrita: ${err.message}`); }
    finally { setIsSaving(false); }
  };

  useEffect(() => { saveFileRef.current = saveFile; }, [saveFile]);

  const handleCloseTab = (filePath, e) => {
    if (e) { e.stopPropagation(); e.preventDefault(); }
    if (selectedFile === filePath) setFileContents(prev => ({ ...prev, [filePath]: fileContent }));
    setOpenFiles(prev => {
      const remaining = prev.filter(f => f !== filePath);
      if (selectedFile === filePath) {
        if (remaining.length > 0) { const next = remaining[remaining.length - 1]; setSelectedFile(next); setFileContent(fileContents[next] || ''); }
        else { setSelectedFile(null); setFileContent(''); }
      }
      return remaining;
    });
  };

  const handleCreateNewFile = async (parentPath) => {
    if (!activeProject) return;
    const filename = window.prompt('Nome do novo arquivo (ex: src/utils.py):', parentPath ? `${parentPath}/` : '');
    if (!filename) return;
    try {
      const res = await fetch('/api/file/write', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ projectPath: activeProject.project_path, filePath: filename, content: '' }) });
      if (res.ok) { addLog('info', `Arquivo criado: ${filename}`); await fetchFiles(); await handleFileSelect(filename); }
      else { const e = await res.json(); addLog('error', `Falha ao criar arquivo: ${e.error}`); alert(`Erro ao criar arquivo: ${e.error}`); }
    } catch (err) { addLog('error', `Erro na chamada de criação de arquivo: ${err.message}`); }
  };

  const handleCreateNewDir = async (parentPath) => {
    if (!activeProject) return;
    const dirname = window.prompt('Nome do novo diretório (ex: src/components):', parentPath ? `${parentPath}/` : '');
    if (!dirname) return;
    try {
      const res = await fetch('/api/file/mkdir', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ projectPath: activeProject.project_path, dirPath: dirname }) });
      if (res.ok) { addLog('info', `Diretório criado: ${dirname}`); await fetchFiles(); }
      else { const e = await res.json(); addLog('error', `Falha ao criar diretório: ${e.error}`); alert(`Erro ao criar diretório: ${e.error}`); }
    } catch (err) { addLog('error', `Erro na chamada de criação de diretório: ${err.message}`); }
  };

  const handleRenameNode = async (node) => {
    if (!activeProject || !node) return;
    const newPath = window.prompt(`Digite o novo caminho/nome para "${node.path}":`, node.path);
    if (!newPath || newPath === node.path) return;
    try {
      const res = await fetch('/api/file/rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ projectPath: activeProject.project_path, oldPath: node.path, newPath }) });
      if (res.ok) {
        addLog('info', `${node.isDirectory ? 'Diretório' : 'Arquivo'} renomeado de ${node.path} para ${newPath}`);
        if (!node.isDirectory) {
          setOpenFiles(prev => prev.map(f => f === node.path ? newPath : f));
          setFileContents(prev => { const n = { ...prev }; n[newPath] = n[node.path]; delete n[node.path]; return n; });
          if (selectedFile === node.path) setSelectedFile(newPath);
        } else {
          const prefix = `${node.path}/`;
          setOpenFiles(prev => prev.map(f => f.startsWith(prefix) ? f.replace(node.path, newPath) : f));
          setFileContents(prev => { const n = {}; for (const [k, v] of Object.entries(prev)) n[k.startsWith(prefix) ? k.replace(node.path, newPath) : k] = v; return n; });
          if (selectedFile?.startsWith(prefix)) setSelectedFile(prev => prev.replace(node.path, newPath));
        }
        await fetchFiles();
      } else { const e = await res.json(); addLog('error', `Falha ao renomear: ${e.error}`); alert(`Erro ao renomear: ${e.error}`); }
    } catch (err) { addLog('error', `Erro ao renomear: ${err.message}`); }
  };

  const handleDeleteNode = async (node) => {
    if (!activeProject || !node) return;
    const msg = `Tem certeza que deseja deletar o ${node.isDirectory ? 'diretório' : 'arquivo'} "${node.path}"?${node.isDirectory ? ' Todos os arquivos internos serão removidos!' : ''}`;
    if (!window.confirm(msg)) return;
    try {
      const res = await fetch('/api/file/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ projectPath: activeProject.project_path, filePath: node.path }) });
      if (res.ok) {
        addLog('info', `${node.isDirectory ? 'Diretório' : 'Arquivo'} excluído: ${node.path}`);
        if (!node.isDirectory) {
          setOpenFiles(prev => prev.filter(f => f !== node.path));
          setFileContents(prev => { const n = { ...prev }; delete n[node.path]; return n; });
          if (selectedFile === node.path) { const rem = openFiles.filter(f => f !== node.path); if (rem.length) { setSelectedFile(rem[rem.length - 1]); setFileContent(fileContents[rem[rem.length - 1]] || ''); } else { setSelectedFile(null); setFileContent(''); } }
        } else {
          const prefix = `${node.path}/`;
          setOpenFiles(prev => prev.filter(f => !f.startsWith(prefix)));
          setFileContents(prev => { const n = {}; for (const [k, v] of Object.entries(prev)) if (!k.startsWith(prefix)) n[k] = v; return n; });
          if (selectedFile?.startsWith(prefix)) { const rem = openFiles.filter(f => !f.startsWith(prefix)); if (rem.length) { setSelectedFile(rem[rem.length - 1]); setFileContent(fileContents[rem[rem.length - 1]] || ''); } else { setSelectedFile(null); setFileContent(''); } }
        }
        await fetchFiles();
      } else { const e = await res.json(); addLog('error', `Falha ao deletar: ${e.error}`); alert(`Erro ao deletar: ${e.error}`); }
    } catch (err) { addLog('error', `Erro ao deletar: ${err.message}`); }
  };

  const handleMoveNode = async (oldPath, targetDirPath, isDirectory) => {
    if (!activeProject) return;
    const nodeName = oldPath.split('/').pop();
    const newPath = targetDirPath ? `${targetDirPath}/${nodeName}` : nodeName;
    if (oldPath === newPath) return;
    if (isDirectory && (newPath === oldPath || newPath.startsWith(`${oldPath}/`))) { addLog('error', 'Não é possível mover um diretório para dentro dele mesmo.'); return; }
    try {
      const res = await fetch('/api/file/rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ projectPath: activeProject.project_path, oldPath, newPath }) });
      if (res.ok) { addLog('info', `${isDirectory ? 'Diretório' : 'Arquivo'} movido de ${oldPath} para ${newPath}`); await fetchFiles(); }
      else { const e = await res.json(); addLog('error', `Falha ao mover: ${e.error}`); }
    } catch (err) { addLog('error', `Erro ao mover: ${err.message}`); }
  };

  // ── Project CRUD ──────────────────────────────────────────────────────────
  const handleCreateProject = async (e) => {
    e.preventDefault();
    if (!newProjName || !newProjPath) return;
    setNewProjError('');
    try {
      const res = await fetch('/api/opalacoder/create-project', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: newProjName, project_path: newProjPath, description: newProjDesc, model: newProjModel, mode: newProjMode, api_key: newProjApiKey, api_base: newProjApiBase, model_params: Object.keys(newProjModelParams).length ? newProjModelParams : undefined }),
      });
      if (res.ok) {
        addLog('info', `Projeto '${newProjName}' registrado.`);
        setShowNewProjectModal(false); setNewProjName(''); setNewProjPath(''); setNewProjDesc(''); setNewProjApiKey(''); setNewProjApiBase('http://localhost:11434/v1');
        fetchProjects();
      } else { const err = await res.json(); setNewProjError(err.error || 'Erro ao criar projeto.'); addLog('error', `Erro ao criar projeto: ${err.error}`); }
    } catch (err) { setNewProjError(err.message || 'Erro ao criar projeto.'); addLog('error', `Erro ao criar: ${err.message}`); }
  };

  const handleDeleteProject = async (projName) => {
    if (!confirm(`Remover projeto '${projName}'?`)) return;
    try {
      const res = await fetch('/api/opalacoder/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_name: projName }) });
      if (res.ok) { addLog('info', `Projeto removido: ${projName}`); if (activeProject?.name === projName) setActiveProject(null); fetchProjects(); }
    } catch (err) { addLog('error', `Erro ao excluir: ${err.message}`); }
  };

  const openEditModal = async (e, proj) => {
    e.stopPropagation();
    let fresh = proj;
    try {
      const res = await fetch('/api/opalacoder/list-projects');
      if (res.ok) { const { projects: list } = await res.json(); const found = list.find(p => p.name === proj.name); if (found) fresh = found; }
    } catch (_) { }
    setModelConfigMsg('');
    setEditingProject({ name: fresh.name, project_name: fresh.project_name || fresh.name, project_path: fresh.project_path || '', model: fresh.model || '', alternative_model: fresh.alternative_model || '', mode: fresh.mode || 'auto', description: fresh.description || '', model_params: fresh.model_params || {}, api_key: fresh.api_key || '', api_base: fresh.api_base || '' });
  };

  const handleUpdateProject = async (e) => {
    e.preventDefault();
    if (!editingProject) return;
    try {
      const res = await fetch('/api/opalacoder/update-project', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: editingProject.name, display_name: editingProject.project_name, project_path: editingProject.project_path, model: editingProject.model, alternative_model: editingProject.alternative_model, mode: editingProject.mode, description: editingProject.description, model_params: editingProject.model_params, api_key: editingProject.api_key, api_base: editingProject.api_base }),
      });
      if (res.ok) {
        const updated = await res.json();
        addLog('info', `Projeto '${updated.project_name}' atualizado.`);
        setEditingProject(null);
        await fetchProjects();
        if (activeProject?.name === updated.name) setActiveProject(prev => ({ ...prev, ...updated }));
      } else { const err = await res.json(); addLog('error', `Erro ao atualizar: ${err.error}`); }
    } catch (err) { addLog('error', `Erro ao atualizar projeto: ${err.message}`); }
  };

  // ── Model config ──────────────────────────────────────────────────────────
  const loadModelConfig = async (projectPath, model, applyFn) => {
    setModelConfigMsg('');
    if (!projectPath || !model) { setModelConfigMsg('⚠️ Defina o caminho do projeto e o modelo antes de carregar.'); return; }
    try {
      const res = await fetch('/api/opalacoder/model-config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ projectPath, model }) });
      const data = await res.json();
      if (!data.found) { setModelConfigMsg(data.message); return; }
      applyFn(data);
      setModelConfigMsg('✅ Configuração refinada carregada.');
    } catch (e) { setModelConfigMsg(`⚠️ Erro ao carregar: ${e.message}`); }
  };

  // ── Dir picker ────────────────────────────────────────────────────────────
  const openDirPicker = async (target, startPath) => {
    const path = startPath || '~';
    try {
      const res = await fetch('/api/fs/dirs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) });
      const data = await res.json();
      setDirPicker({ target, current: data.current, dirs: data.dirs || [] });
    } catch (e) { setDirPicker({ target, current: path, dirs: [] }); }
  };

  const navigateDirPicker = async (path) => {
    try {
      const res = await fetch('/api/fs/dirs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) });
      const data = await res.json();
      setDirPicker(prev => ({ ...prev, current: data.current, dirs: data.dirs || [] }));
    } catch (e) { }
  };

  const confirmDirPicker = () => {
    if (!dirPicker) return;
    if (dirPicker.target === 'new') setNewProjPath(dirPicker.current);
    else setEditingProject(p => ({ ...p, project_path: dirPicker.current }));
    setDirPicker(null);
  };

  // ── Context menu ──────────────────────────────────────────────────────────
  const handleWorkspaceContextMenu = (e) => {
    if (!activeProject) return;
    e.preventDefault(); e.stopPropagation();
    setRightClickedNode(null);
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  const handleNodeContextMenu = (e, node) => {
    if (!activeProject) return;
    e.preventDefault(); e.stopPropagation();
    setRightClickedNode(node);
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  // ── Agent ─────────────────────────────────────────────────────────────────
  const handleInterruptAgent = async () => {
    try {
      const res = await fetch('/api/opalacoder/interrupt', { method: 'POST' });
      if (res.ok) addLog('info', 'Sinal de interrupção enviado ao agente.');
      else addLog('error', 'Falha ao enviar sinal de interrupção.');
    } catch (err) { addLog('error', `Erro ao interromper: ${err.message}`); }
  };

  const handleAgentEvent = (eventObj) => {
    const { event, ...data } = eventObj;
    switch (event) {
      case 'server_ready': addLog('info', 'Agente pronto.'); break;
      case 'agent_started': addLog('info', `Agente ${data.agent} iniciado.`); break;
      case 'thought':
        addLog('thought', data.content);
        setThinkingLogs(prev => {
          if (prev.length > 0) {
            const last = prev[prev.length - 1];
            if (last.type === 'THINKING') {
              return [...prev.slice(0, -1), { ...last, content: last.content + data.content }];
            }
          }
          return [...prev, { timestamp: new Date().toLocaleTimeString(), type: 'THINKING', content: data.content }];
        });
        break;
      case 'reflection':
        addLog('thought', data.content);
        setThinkingLogs(prev => {
          if (prev.length > 0) {
            const last = prev[prev.length - 1];
            if (last.type === 'REFLECTION') {
              return [...prev.slice(0, -1), { ...last, content: last.content + data.content }];
            }
          }
          return [...prev, { timestamp: new Date().toLocaleTimeString(), type: 'REFLECTION', content: data.content }];
        });
        break;
      case 'cancelled': addLog('warning', data.message || 'Execução cancelada.'); setChatMessages(prev => [...prev, { role: 'assistant', content: `⚠️ Interrompido: ${data.message || 'A execução do agente foi parada.'}` }]); break;
      case 'tool_call': addLog('tool_call', `Chamando: ${data.tool} (${JSON.stringify(data.arguments)})`); break;
      case 'tool_result': addLog('tool_result', `Sucesso: ${data.tool}`); break;
      case 'agent_response':
        addLog('info', 'Resposta recebida.');
        setChatMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.role === 'assistant' && last.content === data.response) return prev;
          return [...prev, { role: 'assistant', content: data.response }];
        });
        // ── Auto-replace: if there is a pending inline selection range, extract
        //    the first fenced code block from the response and apply it.
        if (pendingInlineRangeRef.current && editorRef.current && monacoRef.current) {
          const range = pendingInlineRangeRef.current;
          pendingInlineRangeRef.current = null;
          try {
            const codeBlockMatch = data.response.match(/```(?:\w+)?\n([\s\S]*?)```/);
            if (codeBlockMatch) {
              const newCode = codeBlockMatch[1].replace(/\n$/, '');
              const monacoRange = new monacoRef.current.Range(
                range.startLineNumber,
                range.startColumn,
                range.endLineNumber,
                range.endColumn,
              );
              editorRef.current.executeEdits('opalacoder-inline', [{
                range: monacoRange,
                text: newCode,
                forceMoveMarkers: true,
              }]);
              addLog('info', `[Inline] Substituição aplicada nas linhas ${range.startLineNumber}–${range.endLineNumber}.`);
            }
          } catch (replaceErr) {
            addLog('error', `[Inline] Falha ao aplicar substituição: ${replaceErr.message}`);
          }
        }
        break;
      case 'agent_finished': addLog('info', 'Processamento concluído.'); break;
      case 'input_request':
        setConfirmRequest({ id: data.id, prompt: data.prompt, options: data.options || ['yes', 'no'], default: data.default || 'yes' });
        addLog('info', `🔔 Aguardando confirmação: ${data.prompt}`);
        break;
      case 'error': addLog('error', data.message); setChatMessages(prev => [...prev, { role: 'assistant', content: `🔴 Erro do Agente: ${data.message}` }]); break;
      case 'problem':
        addLog('error', `[Problema em ${data.tool}]: ${data.message}`);
        setProblems(prev => [...prev, { id: Math.random().toString(), tool: data.tool, message: data.message, severity: data.severity || 'error', timestamp: new Date().toLocaleTimeString() }]);
        break;
      default: addLog('info', `Evento: ${event}`);
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
    addLog('info', `Iniciando: "${userText}"`);

    if (userText.trim().startsWith('/')) {
      try {
        const res = await fetch('/api/opalacoder/slash-command', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: userText.trim(), project_name: activeProject.name, project_path: activeProject.project_path }),
        });
        const result = await res.json();
        if (result.status === 'confirm') {
          setConfirmRequest({ id: result.id, prompt: result.prompt, options: result.options || ['yes', 'no'], default: result.default || 'yes', isSlashCommand: true });
          addLog('info', `🔔 Aguardando confirmação: ${result.prompt}`);
        } else if (result.status === 'done') {
          setChatMessages(prev => [...prev, { role: 'assistant', content: (result.messages || []).join('\n') || 'Comando executado.' }]);
        } else {
          setChatMessages(prev => [...prev, { role: 'assistant', content: `🔴 Erro: ${result.error || 'desconhecido'}` }]);
        }
      } catch (err) {
        addLog('error', `Falha no comando: ${err.message}`);
        setChatMessages(prev => [...prev, { role: 'assistant', content: `🔴 Falha: ${err.message}` }]);
      } finally { setIsAgentRunning(false); fetchFiles(); }
      return;
    }

    let selectedText = '';
    if (editorRef.current) {
      try { const model = editorRef.current.getModel(); const sel = editorRef.current.getSelection(); if (model && sel) selectedText = model.getValueInRange(sel); } catch (e) { }
    }

    try {
      const res = await fetch('/api/opalacoder/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'run', agent: 'chat_orchestrator', prompt: userText, project_name: activeProject.name, project_path: activeProject.project_path, model: activeProject.model, current_file: selectedFile || '', editor_content: fileContent || '', selected_text: selectedText || '' }),
      });
      if (!res.body) { addLog('error', 'ReadableStream não suportado pelo backend.'); setIsAgentRunning(false); return; }
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
          try { handleAgentEvent(JSON.parse(line)); } catch (e) { addLog('stdout', line); }
        }
      }
      if (buffer.trim()) { try { handleAgentEvent(JSON.parse(buffer)); } catch (e) { addLog('stdout', buffer); } }
    } catch (err) {
      addLog('error', `Falha na execução: ${err.message}`);
      setChatMessages(prev => [...prev, { role: 'assistant', content: `🔴 Falha na execução: ${err.message}` }]);
    } finally { setIsAgentRunning(false); fetchFiles(); fetchProblems(); }
  };

  const sendConfirmResponse = async (value) => {
    if (!confirmRequest) return;
    const { id, prompt, isSlashCommand } = confirmRequest;
    setConfirmRequest(null);
    addLog('info', `✅ Confirmação: "${prompt}" → ${value}`);
    try {
      if (isSlashCommand) {
        const res = await fetch('/api/opalacoder/slash-command/continue', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, value }) });
        const result = await res.json();
        if (result.status === 'done') setChatMessages(prev => [...prev, { role: 'assistant', content: (result.messages || []).join('\n') || 'Comando executado.' }]);
      } else {
        await fetch('/api/opalacoder/input_response', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, value }) });
      }
    } catch (err) { addLog('error', `Erro ao enviar confirmação: ${err.message}`); }
  };

  // ── Editor mount ──────────────────────────────────────────────────────────
  const handleEditorDidMount = (editor, monaco) => {
    editorRef.current = editor;
    if (monaco) monacoRef.current = monaco;
    editor.onKeyDown((e) => {
      const ev = e.browserEvent;
      const isCtrl = ev.ctrlKey || ev.metaKey;
      if (isCtrl && (ev.key === '+' || ev.key === '=' || ev.code === 'Equal' || ev.code === 'NumpadAdd')) {
        ev.preventDefault(); ev.stopPropagation();
        setEditorFontSize(prev => { const v = Math.min(30, prev + 1); safeSetLocalStorage('editorFontSize', v); return v; });
      } else if (isCtrl && (ev.key === '-' || ev.code === 'Minus' || ev.code === 'NumpadSubtract')) {
        ev.preventDefault(); ev.stopPropagation();
        setEditorFontSize(prev => { const v = Math.max(10, prev - 1); safeSetLocalStorage('editorFontSize', v); return v; });
      } else if (isCtrl && ev.key === 's') {
        ev.preventDefault(); ev.stopPropagation();
        if (saveFileRef.current) saveFileRef.current();
      }
    });
  };

  // ── Inline submit — called by InlinePromptOverlay ─────────────────────────
  /**
   * Builds a context-prefixed prompt and sends it to the agent.
   * Also stores the current selection range so that auto-replace can fire
   * when the agent returns the modified code.
   */
  const handleInlineSubmit = async (instruction) => {
    if (!inlinePrompt || !activeProject) return;
    const { startLine, endLine, selectedText, mode } = inlinePrompt;

    const hasSelection = selectedText && selectedText.trim().length > 0;

    let verb;
    if (mode === 'refine') verb = instruction;
    else if (mode === 'fix') verb = instruction;
    else verb = instruction;

    const ext = (selectedFile || '').split('.').pop() || '';
    const fence = ext ? `\`\`\`${ext}` : '\`\`\`';

    const fullPrompt = hasSelection
      ? `${verb}\n\n${fence}\n${selectedText}\n\`\`\``
      : instruction;
    setChatInput('');
    setIsInlineRunning(true);
    addLog('info', `Iniciando edição inline: "${instruction}"`);

    const systemPrompt = "You are an expert developer performing an inline code edit. " +
      "Return ONLY the modified code snippet inside a single markdown code block. " +
      "Do NOT include greetings, conversational filler, or explanations. " +
      "If you need context, use your read-only memory tools.";

    try {
      const res = await fetch('/api/opalacoder/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command: 'run',
          agent: 'inline_editor',
          model: activeProject.model,
          project_name: activeProject.name,
          project_path: activeProject.project_path,
          system_prompt: systemPrompt,
          tools: ["read_file", "search_code", "get_file_overview"],
          prompt: fullPrompt,
          current_file: selectedFile || '',
          editor_content: fileContent || '',
          selected_text: selectedText || '',
          model_params: ephemeralParams
        }),
      });

      if (!res.body) {
        addLog('error', 'ReadableStream não suportado no background.');
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let agentResponse = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            if (data.event === 'agent_response' && data.response) {
              agentResponse = data.response;
            } else if (data.event === 'error') {
              addLog('error', `Inline Agent Error: ${data.message}`);
            }
          } catch (e) {
            // ignore non-json logs
          }
        }
      }

      if (buffer.trim()) {
        try {
          const data = JSON.parse(buffer);
          if (data.event === 'agent_response' && data.response) agentResponse = data.response;
        } catch (e) { }
      }

      if (agentResponse && hasSelection && editorRef.current && monacoRef.current) {
        // Extract code block
        const regex = /```(?:\w+)?\n([\s\S]*?)```/;
        const match = regex.exec(agentResponse);
        const codeToInsert = match ? match[1].replace(/\n$/, '') : agentResponse.trim();

        // Calculate end column dynamically
        const model = editorRef.current.getModel();
        const endCol = model ? model.getLineMaxColumn(endLine) : 1;

        const range = new monacoRef.current.Range(startLine, 1, endLine, endCol);
        editorRef.current.executeEdits('opalacoder_inline', [{
          range: range,
          text: codeToInsert,
          forceMoveMarkers: true,
        }]);
        addLog('info', 'Edição inline aplicada com sucesso.');
      }

    } catch (err) {
      addLog('error', `Falha na edição inline: ${err.message}`);
    } finally {
      setInlinePrompt(null);
      setIsInlineRunning(false);
      fetchFiles();
      fetchProblems();
    }
  };

  /**
   * Variant of handleSendMessage that accepts an explicit prompt string.
   * Used by handleInlineSubmit to bypass the chatInput state timing.
   * @param {string} userText   - The full prompt to send to the agent.
   * @param {string} [capturedSelectedText] - The text captured at submit time
   *   (avoids re-reading Monaco selection which may be gone by now).
   */
  const handleSendMessageWithPrompt = async (userText, capturedSelectedText) => {
    if (!userText.trim() || !activeProject || isAgentRunning) return;
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: userText }]);
    setIsAgentRunning(true);
    setProblems([]);
    addLog('info', `Iniciando: "${userText.slice(0, 80)}${userText.length > 80 ? '…' : ''}"`)

    // Use the captured text if provided; otherwise try reading Monaco
    let selectedText = capturedSelectedText ?? '';
    if (!selectedText && editorRef.current) {
      try {
        const model = editorRef.current.getModel();
        const sel = editorRef.current.getSelection();
        if (model && sel) selectedText = model.getValueInRange(sel);
      } catch (e) { }
    }

    try {
      const res = await fetch('/api/opalacoder/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'run', agent: 'chat_orchestrator', prompt: userText, project_name: activeProject.name, project_path: activeProject.project_path, model: activeProject.model, current_file: selectedFile || '', editor_content: fileContent || '', selected_text: selectedText || '', model_params: ephemeralParams }),
      });
      if (!res.body) { addLog('error', 'ReadableStream não suportado pelo backend.'); setIsAgentRunning(false); return; }
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
          try { handleAgentEvent(JSON.parse(line)); } catch (e) { addLog('stdout', line); }
        }
      }
      if (buffer.trim()) { try { handleAgentEvent(JSON.parse(buffer)); } catch (e) { addLog('stdout', buffer); } }
    } catch (err) {
      addLog('error', `Falha na execução: ${err.message}`);
      setChatMessages(prev => [...prev, { role: 'assistant', content: `🔴 Falha na execução: ${err.message}` }]);
    } finally { setIsAgentRunning(false); fetchFiles(); fetchProblems(); }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="vscode-app">
      <div className="vscode-main">

        {/* Activity Bar */}
        <ActivityBar
          activeSidebarTab={activeSidebarTab}
          setActiveSidebarTab={(tab) => {
            setActiveSidebarTab(tab);
            if (isEditorMaximized) setIsEditorMaximized(false);
          }}
          isChatVisible={isChatVisible}
          setIsChatVisible={(val) => {
            setIsChatVisible(val);
            if (isEditorMaximized) setIsEditorMaximized(false);
          }}
          gitChangesCount={gitChanges.length}
          onOpenSettings={() => setIsSettingsOpen(true)}
        />

        {/* Left Sidebar */}
        {!isEditorMaximized && activeSidebarTab && (
          <aside className="vscode-sidebar" style={{ width: `${sidebarWidth}px` }}>
            {activeSidebarTab === 'explorer' ? (
              <ExplorerSidebar
                projects={projects}
                activeProject={activeProject}
                handleSelectProject={handleSelectProject}
                onNewProject={() => { setShowNewProjectModal(true); setModelConfigMsg(''); setNewProjModelParams({}); }}
                files={files}
                selectedFile={selectedFile}
                handleFileSelect={handleFileSelect}
                handleNodeContextMenu={handleNodeContextMenu}
                handleWorkspaceContextMenu={handleWorkspaceContextMenu}
                draggedNode={draggedNode}
                setDraggedNode={setDraggedNode}
                dragOverPath={dragOverPath}
                setDragOverPath={setDragOverPath}
                handleMoveNode={handleMoveNode}
                fetchFiles={fetchFiles}
                openEditModal={openEditModal}
                handleDeleteProject={handleDeleteProject}
              />
            ) : (
              <GitSidebar
                activeProject={activeProject}
                gitChanges={gitChanges}
                fetchGitStatus={fetchGitStatus}
                commitMessage={commitMessage}
                setCommitMessage={setCommitMessage}
                isCommitting={isCommitting}
                handleGitCommit={handleGitCommit}
                onStageFile={handleStageFile}
                onUnstageFile={handleUnstageFile}
                onDiscardFile={handleDiscardFile}
              />
            )}
          </aside>
        )}

        {/* Left resize handle */}
        {!isEditorMaximized && activeSidebarTab && (
          <div className="vscode-resizer-horizontal" onMouseDown={(e) => startResizing(e, 'left')} />
        )}

        {/* Center — Editor + Bottom Panel */}
        <main className="vscode-editor-panel">
          {!isBottomMaximized && (
            <EditorPanel
              selectedFile={selectedFile}
              openFiles={openFiles}
              fileContent={fileContent}
              fileContents={fileContents}
              isSaving={isSaving}
              theme={theme}
              editorFontSize={editorFontSize}
              editorTabSize={editorTabSize}
              editorWordWrap={editorWordWrap}
              handleFileSelect={handleFileSelect}
              handleCloseTab={handleCloseTab}
              saveFile={saveFile}
              handleEditorDidMount={handleEditorDidMount}
              setFileContent={setFileContent}
              isMaximized={isEditorMaximized}
              onToggleMaximize={() => setIsEditorMaximized(!isEditorMaximized)}
              inlinePrompt={inlinePrompt}
              setInlinePrompt={setInlinePrompt}
              onInlineSubmit={handleInlineSubmit}
              isInlineRunning={isInlineRunning}
              onInlineCancel={() => {
                fetch('/api/opalacoder/interrupt', { method: 'POST' }).catch(() => {});
                setIsInlineRunning(false);
              }}
              onToggleTerminal={() => {
                if (isTerminalCollapsed) {
                  setIsTerminalCollapsed(false);
                  setActiveBottomTab('terminal');
                } else if (activeBottomTab === 'terminal') {
                  setIsTerminalCollapsed(true);
                } else {
                  setActiveBottomTab('terminal');
                }
              }}
            />
          )}

          {!isEditorMaximized && (
            <BottomPanel
              activeBottomTab={activeBottomTab}
              setActiveBottomTab={setActiveBottomTab}
              isTerminalCollapsed={isTerminalCollapsed}
              setIsTerminalCollapsed={setIsTerminalCollapsed}
              terminalLogs={terminalLogs}
              setTerminalLogs={setTerminalLogs}
              problems={problems}
              setProblems={setProblems}
              thinkingLogs={thinkingLogs}
              setThinkingLogs={setThinkingLogs}
              bottomPanelHeight={bottomPanelHeight}
              activeProject={activeProject}
              terminalRef={terminalRef}
              terminalInstanceRef={terminalInstanceRef}
              logEndRef={logEndRef}
              startResizing={startResizing}
              isBottomMaximized={isBottomMaximized}
              onToggleMaximizeBottom={() => setIsBottomMaximized(!isBottomMaximized)}
            />
          )}
        </main>

        {/* Right resize handle */}
        {!isEditorMaximized && isChatVisible && (
          <div className="vscode-resizer-horizontal" onMouseDown={(e) => startResizing(e, 'right')} />
        )}

        {/* Chat Panel */}
        {!isEditorMaximized && (
          <ChatPanel
            chatMessages={chatMessages}
            chatInput={chatInput}
            setChatInput={setChatInput}
            isAgentRunning={isAgentRunning}
            activeProject={activeProject}
            isChatVisible={isChatVisible}
            setIsChatVisible={setIsChatVisible}
            chatWidth={chatWidth}
            handleSendMessage={handleSendMessage}
            handleInterruptAgent={handleInterruptAgent}
            onClearChat={() => {
              const currentProjName = activeProject ? (activeProject.project_name || activeProject.name) : '';
              setChatMessages(currentProjName ? [
                { role: 'assistant', content: t('app.greeting', { projectName: currentProjName }) }
              ] : []);
            }}
            chatEndRef={chatEndRef}
            webSearchConfig={webSearchConfig}
            setWebSearchConfig={setWebSearchConfig}
          />
        )}
      </div>

      {/* Status Bar */}
      <StatusBar activeProject={activeProject} isAgentRunning={isAgentRunning} />

      {/* ── Overlays / Modals ── */}

      {showInstallPrompt && (
        <InstallDepsPrompt
          onClose={() => setShowInstallPrompt(false)}
          onInstall={() => { setShowInstallPrompt(false); setIsSettingsOpen(true); setSettingsTab('preferences'); handleInstallOptionalDeps(); }}
        />
      )}

      {showNewProjectModal && (
        <NewProjectModal
          onClose={() => setShowNewProjectModal(false)}
          onSubmit={handleCreateProject}
          newProjName={newProjName} setNewProjName={setNewProjName}
          newProjPath={newProjPath} setNewProjPath={setNewProjPath}
          newProjDesc={newProjDesc} setNewProjDesc={setNewProjDesc}
          newProjModel={newProjModel} setNewProjModel={setNewProjModel}
          newProjMode={newProjMode} setNewProjMode={setNewProjMode}
          newProjApiKey={newProjApiKey} setNewProjApiKey={setNewProjApiKey}
          newProjApiBase={newProjApiBase} setNewProjApiBase={setNewProjApiBase}
          newProjError={newProjError}
          modelConfigMsg={modelConfigMsg}
          onLoadModelConfig={() => loadModelConfig(newProjPath, newProjModel, (cfg) => { if (cfg.model_params) setNewProjModelParams(cfg.model_params); if (cfg.model) setNewProjModel(cfg.model); })}
          onOpenDirPicker={openDirPicker}
        />
      )}

      {editingProject && (
        <EditProjectModal
          editingProject={editingProject}
          setEditingProject={setEditingProject}
          onClose={() => setEditingProject(null)}
          onSubmit={handleUpdateProject}
          showAdvancedParams={showAdvancedParams}
          setShowAdvancedParams={setShowAdvancedParams}
          modelConfigMsg={modelConfigMsg}
          onLoadModelConfig={() => loadModelConfig(editingProject.project_path, editingProject.model, (cfg) => setEditingProject(p => ({ ...p, model_params: cfg.model_params || p.model_params, model: cfg.model || p.model })))}
          onOpenDirPicker={openDirPicker}
        />
      )}

      {isSettingsOpen && (
        <SettingsModal
          onClose={() => setIsSettingsOpen(false)}
          settingsTab={settingsTab}
          setSettingsTab={setSettingsTab}
          theme={theme} setTheme={setTheme}
          editorFontSize={editorFontSize} setEditorFontSize={setEditorFontSize}
          editorTabSize={editorTabSize} setEditorTabSize={setEditorTabSize}
          editorWordWrap={editorWordWrap} setEditorWordWrap={setEditorWordWrap}
          isInstallingDeps={isInstallingDeps}
          installDepsStatus={installDepsStatus}
          installDepsLog={installDepsLog}
          onInstallDeps={handleInstallOptionalDeps}
          ephemeralParams={ephemeralParams}
          setEphemeralParams={setEphemeralParams}
          onLanguageChange={(lang) => {
            fetch('/api/settings/language', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ lang }),
            }).catch(() => { });
          }}
        />
      )}

      <ConfirmModal confirmRequest={confirmRequest} onConfirm={sendConfirmResponse} />

      <DirPickerModal
        dirPicker={dirPicker}
        onNavigate={navigateDirPicker}
        onConfirm={confirmDirPicker}
        onClose={() => setDirPicker(null)}
      />

      <ContextMenu
        contextMenu={contextMenu}
        rightClickedNode={rightClickedNode}
        handleCreateNewFile={handleCreateNewFile}
        handleCreateNewDir={handleCreateNewDir}
        handleRenameNode={handleRenameNode}
        handleDeleteNode={handleDeleteNode}
      />
    </div>
  );
}
