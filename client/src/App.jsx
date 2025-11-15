import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import DataManager from './components/DataManager';
import WebhookManager from './components/WebHookManager';
import { api } from './utility/api';

const App = () => {
  return (
    <Router>
      <Routes>
        {/* Home page */}
        <Route path="/" element={<DataManager api={api}/>} />

        {/* Movement Details page */}
        <Route path="/movementDetails" element={<WebhookManager API_URL={api.backend_url}/>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
};

export default App;
