import React from 'react';
import { Copy, Clipboard, CheckSquare } from 'lucide-react';

export default function TextContextMenu({ menu, onCopy, onCut, onPaste, onSelectAll }) {
  if (!menu) return null;

  return (
    <div
      id="text-context-menu"
      className="vscode-context-menu"
      style={{ top: `${menu.y}px`, left: `${menu.x}px` }}
    >
      <div className="vscode-context-menu-item" onPointerDown={(e) => { e.stopPropagation(); onCopy(); }}>
        <Copy size={13} />
        <span>Copy</span>
      </div>
<div className="vscode-context-menu-item" onPointerDown={(e) => { e.stopPropagation(); onPaste(); }}>
        <Clipboard size={13} />
        <span>Paste</span>
      </div>
      {onSelectAll && (
        <div className="vscode-context-menu-item" onPointerDown={(e) => { e.stopPropagation(); onSelectAll(); }}>
          <CheckSquare size={13} />
          <span>Select All</span>
        </div>
      )}
    </div>
  );
}
