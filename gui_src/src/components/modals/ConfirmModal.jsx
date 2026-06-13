import React from 'react';
import { useTranslation } from 'react-i18next';

// Modal displayed when the backend emits an input_request (Yes/No confirmation).
export default function ConfirmModal({ confirmRequest, onConfirm }) {
  const { t } = useTranslation();

  if (!confirmRequest) return null;

  return (
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
            {t('confirmModal.title')}
          </span>
        </div>

        {/* Prompt text */}
        <p style={{ fontSize: '14px', color: '#e0e0f0', lineHeight: 1.6, marginBottom: '24px', margin: '0 0 24px 0' }}>
          {confirmRequest.prompt}
        </p>

        {/* Buttons */}
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          {(confirmRequest.options || ['no', 'yes']).map(opt => {
            if (opt === 'cancel') {
              return (
                <button
                  key="cancel"
                  onClick={() => onConfirm('cancel')}
                  style={{
                    padding: '8px 20px', borderRadius: '8px', border: '1px solid #4c4c6c',
                    background: 'transparent', color: '#a0a0c0', cursor: 'pointer',
                    fontSize: '13px', fontWeight: 600, transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => { e.target.style.background = '#2c2c3c'; e.target.style.color = '#e0e0f0'; }}
                  onMouseLeave={e => { e.target.style.background = 'transparent'; e.target.style.color = '#a0a0c0'; }}
                >
                  Cancelar
                </button>
              );
            }
            if (opt === 'no') {
              return (
                <button
                  key="no"
                  id="confirm-no-btn"
                  onClick={() => onConfirm('no')}
                  style={{
                    padding: '8px 20px', borderRadius: '8px', border: '1px solid #4c4c6c',
                    background: 'transparent', color: '#a0a0c0', cursor: 'pointer',
                    fontSize: '13px', fontWeight: 600, transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => { e.target.style.background = '#2c2c3c'; e.target.style.color = '#e0e0f0'; }}
                  onMouseLeave={e => { e.target.style.background = 'transparent'; e.target.style.color = '#a0a0c0'; }}
                >
                  {t('confirmModal.no')}
                </button>
              );
            }
            if (opt === 'yes') {
              return (
                <button
                  key="yes"
                  id="confirm-yes-btn"
                  onClick={() => onConfirm('yes')}
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
                  {t('confirmModal.yes')}
                </button>
              );
            }
            return null;
          })}
        </div>
      </div>
    </div>
  );
}
