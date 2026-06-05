import { useEffect, useRef } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';

// Hook that initialises an xterm.js terminal and connects it to the backend SSE stream.
export function useTerminal({ activeProject, terminalRef, terminalInstanceRef, fitAddonRef, eventSourceRef, activeBottomTab, bottomPanelHeight, isTerminalCollapsed }) {
  const promptDrawnRef = useRef(false);
  // Written on every render so the ResizeObserver callback (a closure created
  // once at mount) always reads the latest value without a stale-closure race.
  const isCollapsedRef = useRef(isTerminalCollapsed);
  isCollapsedRef.current = isTerminalCollapsed;

  // Initialise / tear-down terminal when the active project changes.
  useEffect(() => {
    if (!activeProject) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      return;
    }

    if (!terminalRef.current) return;

    // Reset the prompt-drawn flag whenever the terminal is (re)created.
    promptDrawnRef.current = false;

    const term = new XTerm({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Consolas, "Courier New", monospace',
      theme: {
        background: '#1e1e1e',
        foreground: '#cccccc',
      },
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);

    terminalRef.current.innerHTML = '';
    term.open(terminalRef.current);
    try { fitAddon.fit(); } catch (e) { /* ignore */ }

    terminalInstanceRef.current = term;
    fitAddonRef.current = fitAddon;

    // Connect to SSE terminal stream.
    const projectPath = activeProject.project_path;
    const url = `/api/terminal/stream?projectPath=${encodeURIComponent(projectPath)}`;
    const evs = new EventSource(url);
    eventSourceRef.current = evs;

    evs.onmessage = (event) => {
      try {
        const raw = atob(event.data);
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
        term.write(bytes);
      } catch (err) {
        console.error('Error decoding terminal stream data', err);
      }
    };

    evs.onerror = () => {
      term.write('\r\n\x1b[31m[OpalaCoder] Conexão com o terminal perdida. Reconectando...\x1b[0m\r\n');
    };

    // Forward keystrokes to the backend.
    term.onData((data) => {
      fetch('/api/terminal/input', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'input', text: data, projectPath: activeProject.project_path }),
      }).catch(err => console.error('Failed to send terminal input', err));
    });

    // Resize observer keeps the terminal sized correctly.
    const resizeObserver = new ResizeObserver(() => {
      if (fitAddon && !isCollapsedRef.current) {
        try {
          fitAddon.fit();
          const { cols, rows } = term;
          fetch('/api/terminal/input', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'resize', cols, rows, projectPath: activeProject.project_path }),
          }).catch(err => console.error('Failed to send terminal resize', err));
        } catch (e) { /* ignore */ }
      }
    });
    resizeObserver.observe(terminalRef.current);

    return () => {
      resizeObserver.disconnect();
      if (evs) evs.close();
      term.dispose();
      terminalInstanceRef.current = null;
      fitAddonRef.current = null;
    };
  }, [activeProject]);

  // Re-fit the terminal when the terminal tab becomes visible, the panel is expanded, or resized.
  useEffect(() => {
    if (activeBottomTab === 'terminal' && !isTerminalCollapsed && terminalInstanceRef.current && fitAddonRef.current && activeProject) {
      setTimeout(() => {
        try {
          fitAddonRef.current.fit();
          const { cols, rows } = terminalInstanceRef.current;
          fetch('/api/terminal/input', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'resize', cols, rows, projectPath: activeProject.project_path }),
          }).catch(err => console.error('Failed to send terminal resize', err));

          terminalInstanceRef.current.focus();

          // On the first time the terminal becomes visible, the shell may not have
          // redrawn its prompt after the initial resize (the tab was hidden during
          // creation so xterm.js had no valid dimensions). Sending Ctrl+L forces
          // bash/zsh to redraw the prompt without executing any command.
          if (!promptDrawnRef.current) {
            promptDrawnRef.current = true;
            fetch('/api/terminal/input', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ action: 'input', text: '\x0c', projectPath: activeProject.project_path }),
            }).catch(err => console.error('Failed to send prompt redraw', err));
          }
        } catch (e) { /* ignore */ }
      }, 50);
    }
  }, [activeBottomTab, bottomPanelHeight, activeProject, isTerminalCollapsed]);
}
