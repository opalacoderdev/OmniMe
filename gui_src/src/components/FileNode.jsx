import React, { useState } from 'react';
import { Folder, File, ChevronRight, ChevronDown } from 'lucide-react';

// Recursive file/directory tree node with drag-and-drop support.
export default function FileNode({
  node,
  selectedFile,
  handleFileSelect,
  handleNodeContextMenu,
  draggedNode,
  setDraggedNode,
  dragOverPath,
  setDragOverPath,
  handleMoveNode,
}) {
  const isDir = node.isDirectory;
  const [isOpen, setIsOpen] = useState(false);

  const handleDragStart = (e) => {
    e.stopPropagation();
    setDraggedNode({ path: node.path, isDirectory: node.isDirectory });
    e.dataTransfer.setData('text/plain', node.path);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDir) return;
    if (draggedNode && draggedNode.path !== node.path) {
      setDragOverPath(node.path);
      e.dataTransfer.dropEffect = 'move';
    }
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (dragOverPath === node.path) {
      setDragOverPath(null);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverPath(null);
    if (!isDir) return;
    if (draggedNode && draggedNode.path !== node.path) {
      handleMoveNode(draggedNode.path, node.path, draggedNode.isDirectory);
    }
  };

  const isDragOver = dragOverPath === node.path;
  const style = isDragOver ? { backgroundColor: '#2d2d2d', border: '1px dashed #007acc' } : {};

  if (isDir) {
    return (
      <div
        className="select-none"
        draggable="true"
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div
          onClick={() => setIsOpen(!isOpen)}
          className="vscode-tree-node"
          style={style}
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
                draggedNode={draggedNode}
                setDraggedNode={setDraggedNode}
                dragOverPath={dragOverPath}
                setDragOverPath={setDragOverPath}
                handleMoveNode={handleMoveNode}
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
      draggable="true"
      onDragStart={handleDragStart}
      onContextMenu={(e) => handleNodeContextMenu(e, node)}
    >
      <File size={13} style={{ color: '#a0a0a0' }} />
      <span className="truncate">{node.name}</span>
    </div>
  );
}
