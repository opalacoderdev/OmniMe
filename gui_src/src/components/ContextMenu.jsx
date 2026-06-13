import React from 'react';
import { Plus, FolderPlus, Edit2, Trash2, Copy, ClipboardPaste } from 'lucide-react';
import { useTranslation } from 'react-i18next';

// Floating right-click context menu for the file explorer.
export default function ContextMenu({
  contextMenu,
  rightClickedNode,
  handleCreateNewFile,
  handleCreateNewDir,
  handleRenameNode,
  handleDeleteNode,
  handleCopyNode,
  handlePasteNode,
  clipboardNode,
}) {
  const { t } = useTranslation();

  if (!contextMenu) return null;

  const parentPath = rightClickedNode
    ? (rightClickedNode.isDirectory
        ? rightClickedNode.path
        : rightClickedNode.path.replace(/\\/g, '/').split('/').slice(0, -1).join('/'))
    : '';

  return (
    <div
      className="vscode-context-menu"
      style={{ top: `${contextMenu.y}px`, left: `${contextMenu.x}px` }}
    >
      <div
        className="vscode-context-menu-item"
        onClick={() => handleCreateNewFile(parentPath)}
      >
        <Plus size={13} style={{ color: '#007acc' }} />
        <span>{t('contextMenu.newFile')}</span>
      </div>
      <div
        className="vscode-context-menu-item"
        onClick={() => handleCreateNewDir(parentPath)}
      >
        <FolderPlus size={13} style={{ color: '#007acc' }} />
        <span>{t('contextMenu.newDir')}</span>
      </div>
      {rightClickedNode && (
        <>
          <div
            className="vscode-context-menu-item"
            onClick={() => handleCopyNode(rightClickedNode)}
          >
            <Copy size={13} style={{ color: '#888' }} />
            <span>{t('contextMenu.copy', 'Copiar')}</span>
          </div>
          <div
            className="vscode-context-menu-item"
            onClick={() => handleRenameNode(rightClickedNode)}
          >
            <Edit2 size={13} style={{ color: '#e2b52b' }} />
            <span>{t('contextMenu.rename')}</span>
          </div>
          <div
            className="vscode-context-menu-item"
            onClick={() => handleDeleteNode(rightClickedNode)}
          >
            <Trash2 size={13} style={{ color: '#f48771' }} />
            <span>{t('contextMenu.delete')}</span>
          </div>
        </>
      )}
      {clipboardNode && (
        <div
          className="vscode-context-menu-item"
          onClick={() => handlePasteNode(parentPath)}
        >
          <ClipboardPaste size={13} style={{ color: '#007acc' }} />
          <span>{t('contextMenu.paste', 'Colar')}</span>
        </div>
      )}
    </div>
  );
}
