import React from 'react';

const App: React.FC = () => {
  return React.createElement('div', { className: 'p-4' },
    React.createElement('h1', { className: 'text-xl font-bold' }, 'CUE — Cuaderno de Campo'),
    React.createElement('p', { className: 'text-gray-600 mt-2' }, 'Módulo SIEX. Seleccione una sección del panel de contexto.')
  );
};

export default App;
