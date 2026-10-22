import React from 'react';
import { CUEMainPanel } from './components/CUEMainPanel';

const App: React.FC = () => {
  return React.createElement('div', { className: 'cue-module p-2' },
    React.createElement(CUEMainPanel, null)
  );
};

export default App;
