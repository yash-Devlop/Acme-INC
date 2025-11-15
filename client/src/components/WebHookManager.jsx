import React, { useState, useEffect } from 'react';
import { Webhook, Plus, Edit2, Trash2, TestTube, Check, X, Loader2, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const WebhookManager = ({ API_URL }) => {
  const [webhooks, setWebhooks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState(null);
  const [testing, setTesting] = useState(null);
  const [testResult, setTestResult] = useState(null);
  
  const [formData, setFormData] = useState({
    name: '',
    url: '',
    event_type: 'product.created',
    enabled: true,
    secret_key: '',
  });

  const eventTypes = [
    { value: 'product.created', label: 'Product Created' },
    { value: 'product.updated', label: 'Product Updated' },
    { value: 'product.deleted', label: 'Product Deleted' },
    { value: 'product.status_changed', label: 'Status Changed' },
    { value: 'csv.uploaded', label: 'CSV Uploaded' },
  ];

  const navigate = useNavigate();
  const goToDataManager = () => navigate('/');

  useEffect(() => {
    fetchWebhooks();
  }, []);

  const fetchWebhooks = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/webhooks`);
      const data = await response.json();
      setWebhooks(data.webhooks || []);
    } catch (error) {
      console.error('Failed to fetch webhooks:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const url = editingWebhook 
        ? `${API_URL}/webhooks/${editingWebhook.id}`
        : `${API_URL}/webhooks`;
      
      const method = editingWebhook ? 'PATCH' : 'POST';
      
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (response.ok) {
        fetchWebhooks();
        setShowModal(false);
        resetForm();
      }
    } catch (error) {
      console.error('Failed to save webhook:', error);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this webhook?')) return;
    try {
      const response = await fetch(`${API_URL}/webhooks/${id}`, {
        method: 'DELETE',
      });
      if (response.ok) fetchWebhooks();
    } catch (error) {
      console.error('Failed to delete webhook:', error);
    }
  };

  const handleTest = async (id) => {
    setTesting(id);
    setTestResult(null);
    try {
      const response = await fetch(`${API_URL}/webhooks/${id}/test`, { method: 'POST' });
      const result = await response.json();
      setTestResult(result);
      setTimeout(() => setTestResult(null), 5000);
    } catch (error) {
      setTestResult({ success: false, error: error.message });
    } finally {
      setTesting(null);
    }
  };

  const toggleEnabled = async (webhook) => {
    try {
      await fetch(`${API_URL}/webhooks/${webhook.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !webhook.enabled }),
      });
      fetchWebhooks();
    } catch (error) {
      console.error('Failed to toggle webhook:', error);
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      url: '',
      event_type: 'product.created',
      enabled: true,
      secret_key: '',
    });
    setEditingWebhook(null);
  };

  const openEditModal = (webhook) => {
    setEditingWebhook(webhook);
    setFormData({
      name: webhook.name,
      url: webhook.url,
      event_type: webhook.event_type,
      enabled: webhook.enabled,
      secret_key: webhook.secret_key || '',
    });
    setShowModal(true);
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      {/* Header with Back Button */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-4">
          <button
            onClick={goToDataManager}
            className="flex items-center gap-2 px-3 py-2 bg-gray-200 hover:bg-gray-300 rounded-lg"
          >
            <ArrowLeft size={20} />
            Back to Data Manager
          </button>
          <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
            <Webhook size={28} />
            Webhook Management
          </h2>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 flex items-center gap-2"
        >
          <Plus size={20} />
          Add Webhook
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center p-8">
          <Loader2 className="animate-spin h-8 w-8 text-blue-600" />
        </div>
      ) : webhooks.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <Webhook size={48} className="mx-auto mb-4 opacity-50" />
          <p>No webhooks configured yet</p>
        </div>
      ) : (
        <div className="space-y-4">
          {webhooks.map((webhook) => (
            <div key={webhook.id} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="font-semibold text-lg">{webhook.name}</h3>
                    <button
                      onClick={() => toggleEnabled(webhook)}
                      className={`px-3 py-1 rounded-full text-xs font-semibold ${
                        webhook.enabled
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {webhook.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                  </div>
                  <p className="text-sm text-gray-600 mb-1">
                    <strong>URL:</strong> {webhook.url}
                  </p>
                  <p className="text-sm text-gray-600 mb-1">
                    <strong>Event:</strong> {webhook.event_type}
                  </p>
                  {webhook.last_triggered_at && (
                    <div className="flex gap-4 text-xs text-gray-500 mt-2">
                      <span>Last triggered: {new Date(webhook.last_triggered_at).toLocaleString()}</span>
                      {webhook.last_status_code && (
                        <span className={webhook.last_status_code === 200 ? 'text-green-600' : 'text-red-600'}>
                          Status: {webhook.last_status_code}
                        </span>
                      )}
                      {webhook.last_response_time && <span>Response time: {webhook.last_response_time}ms</span>}
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleTest(webhook.id)}
                    disabled={testing === webhook.id}
                    className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg disabled:opacity-50"
                    title="Test webhook"
                  >
                    {testing === webhook.id ? (
                      <Loader2 className="animate-spin h-5 w-5" />
                    ) : (
                      <TestTube size={20} />
                    )}
                  </button>
                  <button
                    onClick={() => openEditModal(webhook)}
                    className="p-2 text-gray-600 hover:bg-gray-50 rounded-lg"
                    title="Edit webhook"
                  >
                    <Edit2 size={20} />
                  </button>
                  <button
                    onClick={() => handleDelete(webhook.id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg"
                    title="Delete webhook"
                  >
                    <Trash2 size={20} />
                  </button>
                </div>
              </div>

              {testResult && testing === null && (
                <div className={`mt-3 p-3 rounded-lg ${testResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                  <div className="flex items-center gap-2">
                    {testResult.success ? (
                      <Check className="text-green-600" size={20} />
                    ) : (
                      <X className="text-red-600" size={20} />
                    )}
                    <span className="font-semibold">
                      {testResult.success ? 'Test Successful' : 'Test Failed'}
                    </span>
                  </div>
                  {testResult.success ? (
                    <div className="text-sm mt-2">
                      <p>Status Code: {testResult.status_code}</p>
                      <p>Response Time: {testResult.response_time}ms</p>
                    </div>
                  ) : (
                    <p className="text-sm mt-2">{testResult.error}</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full">
            <h3 className="text-xl font-bold mb-4">
              {editingWebhook ? 'Edit Webhook' : 'Add New Webhook'}
            </h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Name</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Webhook URL</label>
                <input
                  type="url"
                  value={formData.url}
                  onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  placeholder="https://example.com/webhook"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Event Type</label>
                <select
                  value={formData.event_type}
                  onChange={(e) => setFormData({ ...formData, event_type: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                >
                  {eventTypes.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Secret Key (Optional)</label>
                <input
                  type="text"
                  value={formData.secret_key}
                  onChange={(e) => setFormData({ ...formData, secret_key: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  placeholder="For webhook signature verification"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="w-4 h-4"
                />
                <label className="text-sm">Enable webhook</label>
              </div>
              <div className="flex justify-end gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    resetForm();
                  }}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  {editingWebhook ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default WebhookManager;
