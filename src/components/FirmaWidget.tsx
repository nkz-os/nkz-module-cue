import React, { useState, useRef } from 'react';

interface FirmaWidgetProps {
  onCertLoaded: (certB64: string, password: string) => void;
  onClear: () => void;
  certLoaded: boolean;
  loading?: boolean;
}

export const FirmaWidget: React.FC<FirmaWidgetProps> = ({
  onCertLoaded,
  onClear,
  certLoaded,
  loading,
}) => {
  const [fileName, setFileName] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: any) => {
    const file = e.target?.files?.[0];
    setError(null);

    if (!file) {
      setFileName(null);
      onClear();
      return;
    }

    const ext = file.name.split('.').pop()?.toLowerCase();
    if (ext !== 'p12' && ext !== 'pfx') {
      setError('Solo se admiten archivos PKCS#12 (.p12 o .pfx)');
      setFileName(null);
      if (fileRef.current) fileRef.current.value = '';
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setError('El archivo no puede superar 10 MB');
      setFileName(null);
      if (fileRef.current) fileRef.current.value = '';
      return;
    }

    setFileName(file.name);

    // Read file as base64
    const reader = new FileReader();
    reader.onload = () => {
      const b64 = (reader.result as string).split(',')[1];
      if (b64 && password) {
        onCertLoaded(b64, password);
      }
    };
    reader.onerror = () => {
      setError('Error al leer el archivo');
      setFileName(null);
    };
    reader.readAsDataURL(file);
  };

  const handlePasswordChange = (e: any) => {
    const pwd = e.target.value;
    setPassword(pwd);
    // Also trigger reload if file already selected
    if (fileName && fileRef.current?.files?.[0] && pwd) {
      const reader = new FileReader();
      const file = fileRef.current.files[0];
      reader.onload = () => {
        const b64 = (reader.result as string).split(',')[1];
        if (b64) onCertLoaded(b64, pwd);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleClear = () => {
    setFileName(null);
    setPassword('');
    setError(null);
    if (fileRef.current) fileRef.current.value = '';
    onClear();
  };

  // Loaded state — show green badge
  if (certLoaded && fileName) {
    return React.createElement('div', { className: 'bg-green-50 border border-green-200 rounded p-3' },
      React.createElement('div', { className: 'flex items-center gap-2' },
        React.createElement('span', { className: 'text-green-600 text-sm font-medium' }, '✓ Certificado cargado'),
        React.createElement('span', { className: 'text-green-500 text-xs' }, fileName),
        !loading && React.createElement('button', {
          onClick: handleClear,
          className: 'ml-auto text-xs text-red-500 hover:text-red-700 underline'
        }, 'Quitar')
      ),
      loading && React.createElement('div', { className: 'text-green-500 text-xs mt-1' }, 'Certificado en memoria RAM del servidor...')
    );
  }

  // Default state — file picker + password
  return React.createElement('div', { className: 'bg-yellow-50 border border-yellow-200 rounded p-3 space-y-3' },
    React.createElement('div', { className: 'text-sm font-medium text-yellow-800' }, 'Firma electrónica (AutoFirma)'),

    error && React.createElement('div', { className: 'bg-red-50 text-red-600 text-xs p-2 rounded' }, error),

    // File input
    React.createElement('div', null,
      React.createElement('label', { className: 'block text-xs text-yellow-700 mb-1' }, 'Certificado digital (.p12 / .pfx)'),
      React.createElement('input', {
        ref: fileRef,
        type: 'file',
        accept: '.p12,.pfx',
        onChange: handleFileChange,
        className: 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-medium file:bg-yellow-600 file:text-white hover:file:bg-yellow-700'
      })
    ),

    // Password
    fileName && React.createElement('div', null,
      React.createElement('label', { className: 'block text-xs text-yellow-700 mb-1' }, 'Contraseña del certificado'),
      React.createElement('input', {
        type: 'password',
        value: password,
        onChange: handlePasswordChange,
        placeholder: 'Contraseña del certificado...',
        className: 'border border-yellow-300 rounded px-3 py-2 w-full text-sm'
      })
    ),

    fileName && !password && React.createElement('div', { className: 'text-xs text-yellow-600' },
      'Introduzca la contraseña para activar el certificado'
    ),

    React.createElement('p', { className: 'text-xs text-yellow-600' },
      'El certificado se transmite cifrado (HTTPS) y se elimina de la memoria del servidor tras el envío. Nunca se almacena en disco.'
    )
  );
};
