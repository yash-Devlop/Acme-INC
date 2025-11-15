import React, { useState, useEffect, useCallback } from 'react';
import { Upload, Search, Plus, Trash2, X, Check, AlertCircle, ChevronLeft, ChevronRight, Loader2, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

// Toast
const Toast = ({ message, type, onClose }) => {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000);
    return () => clearTimeout(timer);
  }, [onClose]);

  const bgColor = type === 'success' ? 'bg-green-500' : type === 'error' ? 'bg-red-500' : 'bg-blue-500';

  return (
    <div className={`fixed top-4 right-4 ${bgColor} text-white px-6 py-3 rounded-lg shadow-lg flex items-center gap-2 z-60`}>
      {type === 'success' ? <Check size={20} /> : <AlertCircle size={20} />}
      {message}
      <button onClick={onClose} className="ml-2"><X size={16} /></button>
    </div>
  );
};

const ModalBackdrop = ({ children, onClose }) => {
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, []);

  return (
    <div
      className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50 p-4 overflow-hidden"
      onClick={onClose}
    >
      <div
        className="relative animate-in fade-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
};

const DataManager = ({ api }) => {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [totalPages, setTotalPages] = useState(1);
  const [totalProducts, setTotalProducts] = useState(0);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedProducts, setSelectedProducts] = useState([]);

  const [deleteDialog, setDeleteDialog] = useState({ open: false, sku: null, multiple: false });
  const [deleteAllDialog, setDeleteAllDialog] = useState(false);
  const [addDialog, setAddDialog] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState(null);

  const [newProduct, setNewProduct] = useState({
    sku: '',
    name: '',
    description: '',
    status: 1
  });

  const navigate = useNavigate()
  const goToWebhookManager = () => {
    navigate('/movementDetails');
  }
  const API_URL = api.backend_url

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
  };

  // Fetch products
  const fetchProducts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString(),
      });

      if (search) params.append('search', search);
      if (statusFilter !== '') params.append('status', statusFilter);

      const response = await fetch(`${API_URL}/products?${params}`);
      const result = await response.json();

      setProducts(result.data || []);
      setTotalPages(result.total_pages || 1);
      setTotalProducts(result.total || 0);
    } catch (error) {
      showToast('Failed to fetch products', 'error');
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, statusFilter, API_URL]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  // Handle CSV upload with WebSocket progress

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);

    const formData = new FormData();
    formData.append('file', file);

    // Connect to WebSocket for REAL-TIME progress updates
    const wsUrl = API_URL.replace('http://', 'ws://').replace('https://', 'wss://');
    let ws = null;
    let progressUpdateInterval = null;

    try {
      // Create WebSocket connection
      ws = new WebSocket(`${wsUrl}/ws/upload_progress`);

      // Track connection state
      let isConnected = false;

      ws.onopen = () => {
        console.log('WebSocket connected for progress tracking');
        isConnected = true;

        // Send periodic pings to keep connection alive and request updates
        progressUpdateInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 500); // Ping every 500ms for smooth updates
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Backend sends progress as float (0.0 - 1.0)
          // Convert to percentage (0 - 100)
          const progressValue = parseFloat(data.progress) || 0;
          const progressPercentage = progressValue * 100;

          console.log(`Progress update: ${progressPercentage.toFixed(1)}%`);

          // Update progress bar smoothly
          setUploadProgress(Math.min(progressPercentage, 100));

        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('WebSocket connection closed');
        isConnected = false;
        if (progressUpdateInterval) {
          clearInterval(progressUpdateInterval);
        }
      };

      // Wait a bit for WebSocket to connect
      await new Promise(resolve => setTimeout(resolve, 200));

      console.log('Starting file upload...');
      const response = await fetch(`${API_URL}/upload_products_csv`, {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();

        // Ensure progress reaches 100%
        setUploadProgress(100);

        console.log('Upload completed successfully');
        showToast('CSV uploaded successfully!');

        // Refresh product list
        fetchProducts();
        setSelectedProducts([]);

      } else {
        const error = await response.json();
        console.error('Upload failed:', error.detail);
        showToast(`Upload failed: ${error.detail}`, 'error');
        setUploadProgress(0);
      }

    } catch (error) {
      console.error('Upload error:', error);
      showToast('Upload failed: Network error', 'error');
      setUploadProgress(0);

    } finally {
      // Clean up WebSocket connection
      if (progressUpdateInterval) {
        clearInterval(progressUpdateInterval);
      }

      if (ws) {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      }

      setUploading(false);

      // Reset progress after a delay
      setTimeout(() => {
        setUploadProgress(0);
      }, 2000);

      // Clear file input
      event.target.value = '';
    }
  };

  // Add product manually
  const handleAddProduct = async () => {
    if (!newProduct.sku || !newProduct.name) {
      showToast('SKU and Name are required', 'error');
      return;
    }

    try {
      const response = await fetch(`${API_URL}/add_product`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProduct),
      });

      if (response.ok) {
        showToast('Product added successfully!');
        setAddDialog(false);
        setNewProduct({ sku: '', name: '', description: '', status: 1 });
        fetchProducts();
      } else {
        const error = await response.json();
        showToast(`Failed to add product: ${error.detail}`, 'error');
      }
    } catch (error) {
      showToast('Failed to add product', 'error');
      console.error(error);
    }
  };

  // Update product status
  const handleStatusChange = async (sku, newStatus) => {
    try {
      const response = await fetch(`${API_URL}/products/${sku}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });

      if (response.ok) {
        showToast('Status updated successfully!');
        fetchProducts();
      } else {
        showToast('Failed to update status', 'error');
      }
    } catch (error) {
      showToast('Failed to update status', 'error');
      console.error(error);
    }
  };

  // Delete single product
  const handleDeleteProduct = async (sku) => {
    setDeleting(true);
    try {
      const response = await fetch(`${API_URL}/products/${sku}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        showToast('Product deleted successfully!');
        fetchProducts();
        setSelectedProducts(prev => prev.filter(s => s !== sku));
      } else {
        showToast('Failed to delete product', 'error');
      }
    } catch (error) {
      showToast('Failed to delete product', 'error');
      console.error(error);
    } finally {
      setDeleting(false);
      setDeleteDialog({ open: false, sku: null, multiple: false });
    }
  };

  // Delete multiple products
  const handleDeleteMultiple = async () => {
    setDeleting(true);
    try {
      const response = await fetch(`${API_URL}/delete_by_sku`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skus: selectedProducts }),
      });

      if (response.ok) {
        showToast(`${selectedProducts.length} products deleted successfully!`);
        setSelectedProducts([]);
        fetchProducts();
      } else {
        showToast('Failed to delete products', 'error');
      }
    } catch (error) {
      showToast('Failed to delete products', 'error');
      console.error(error);
    } finally {
      setDeleting(false);
      setDeleteDialog({ open: false, sku: null, multiple: false });
    }
  };

  // Delete all products
  const handleDeleteAll = async () => {
    setDeleting(true);
    try {
      const response = await fetch(`${API_URL}/delete_all_products`, {
        method: 'DELETE',
      });

      if (response.ok) {
        showToast('All products deleted successfully!');
        setSelectedProducts([]);
        fetchProducts();
      } else {
        showToast('Failed to delete all products', 'error');
      }
    } catch (error) {
      showToast('Failed to delete all products', 'error');
      console.error(error);
    } finally {
      setDeleting(false);
      setDeleteAllDialog(false);
    }
  };

  // Handle row selection
  const handleSelectProduct = (sku) => {
    setSelectedProducts(prev =>
      prev.includes(sku)
        ? prev.filter(s => s !== sku)
        : [...prev, sku]
    );
  };

  const handleSelectAll = () => {
    if (selectedProducts.length === products.length && products.length > 0) {
      setSelectedProducts([]);
    } else {
      setSelectedProducts(products.map(p => p.sku));
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      <div className="max-w-7xl mx-auto">
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h1 className="text-3xl font-bold text-gray-800 mb-6">Product Management System</h1>

          {/* Action Buttons */}
          <div className="flex flex-wrap gap-3 mb-4 items-center w-full">
            <label className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 cursor-pointer flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
              <Upload size={20} />
              Upload CSV
              <input
                type="file"
                className="hidden"
                accept=".csv"
                onChange={handleFileUpload}
                disabled={uploading}
              />
            </label>

            <button
              className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 flex items-center gap-2"
              onClick={() => setAddDialog(true)}
            >
              <Plus size={20} />
              Add Product
            </button>

            <button
              className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={selectedProducts.length === 0}
              onClick={() => setDeleteDialog({ open: true, multiple: true })}
            >
              <Trash2 size={20} />
              Delete Selected ({selectedProducts.length})
            </button>

            <button
              className="bg-red-800 text-white px-4 py-2 rounded-lg hover:bg-red-900 flex items-center gap-2"
              onClick={() => setDeleteAllDialog(true)}
            >
              <Trash2 size={20} />
              Delete All
            </button>

            {/* Move this button to the right */}
            <button
              className="ml-auto bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 flex items-center gap-2"
              onClick={goToWebhookManager}
            >
              <Settings size={20} />
              Webhook Manager
            </button>
          </div>

          {/* Upload Progress */}
          {uploading && (
            <div className="mb-4">
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div
                  className="bg-blue-600 h-2.5 rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="text-sm text-gray-600 mt-2 text-center font-medium">
                Uploading... {uploadProgress.toFixed(1)}%
              </p>
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap gap-3 mb-4">
            <div className="flex-1 min-w-[300px] relative">
              <Search className="absolute left-3 top-3 text-gray-400" size={20} />
              <input
                type="text"
                placeholder="Search by SKU, name, or description"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">All Status</option>
              <option value="1">Active</option>
              <option value="0">Inactive</option>
            </select>

            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value={25}>25 per page</option>
              <option value={50}>50 per page</option>
              <option value={100}>100 per page</option>
              <option value={200}>200 per page</option>
            </select>
          </div>

          <p className="text-sm text-gray-600 mb-3">
            Total Products: {totalProducts.toLocaleString()} | Page {page} of {totalPages}
          </p>
        </div>

        {/* Products Table */}
        <div className="bg-white rounded-lg shadow-md overflow-hidden">
          {loading ? (
            <div className="flex justify-center items-center p-12">
              <Loader2 className="animate-spin h-12 w-12 text-blue-600" />
            </div>
          ) : products.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <p className="text-lg">No products found</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-100 sticky top-0">
                    <tr>
                      <th className="px-4 py-3 text-left">
                        <input
                          type="checkbox"
                          checked={selectedProducts.length === products.length && products.length > 0}
                          onChange={handleSelectAll}
                          className="w-4 h-4 cursor-pointer"
                        />
                      </th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-700">SKU</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-700">Name</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-700">Description</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-700">Status</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-700">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.map((product, idx) => (
                      <tr key={product.sku} className={`border-t hover:bg-gray-50 transition-colors ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}>
                        <td className="px-4 py-3">
                          <input
                            type="checkbox"
                            checked={selectedProducts.includes(product.sku)}
                            onChange={() => handleSelectProduct(product.sku)}
                            className="w-4 h-4 cursor-pointer"
                          />
                        </td>
                        <td className="px-4 py-3 font-medium text-gray-900">{product.sku}</td>
                        <td className="px-4 py-3 text-gray-700">{product.name}</td>
                        <td className="px-4 py-3 max-w-xs truncate text-gray-600" title={product.description}>
                          {product.description}
                        </td>
                        <td className="px-4 py-3">
                          <select
                            value={product.status}
                            onChange={(e) => handleStatusChange(product.sku, Number(e.target.value))}
                            className={`px-3 py-1 rounded-full text-sm font-semibold cursor-pointer ${product.status === 1
                              ? 'bg-green-100 text-green-800'
                              : 'bg-red-100 text-red-800'
                              }`}
                          >
                            <option value={1}>Active</option>
                            <option value={0}>Inactive</option>
                          </select>
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => setDeleteDialog({ open: true, sku: product.sku, multiple: false })}
                            className="text-red-600 hover:text-red-800 transition-colors"
                            title="Delete product"
                          >
                            <Trash2 size={18} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="flex justify-center items-center gap-2 p-4 border-t bg-gray-50">
                <button
                  onClick={() => setPage(1)}
                  disabled={page === 1}
                  className="px-3 py-1 rounded border border-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 transition-colors"
                >
                  First
                </button>
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 rounded border border-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 flex items-center gap-1 transition-colors"
                >
                  <ChevronLeft size={16} /> Prev
                </button>
                <span className="px-4 py-1 font-medium text-gray-700">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-3 py-1 rounded border border-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 flex items-center gap-1 transition-colors"
                >
                  Next <ChevronRight size={16} />
                </button>
                <button
                  onClick={() => setPage(totalPages)}
                  disabled={page === totalPages}
                  className="px-3 py-1 rounded border border-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 transition-colors"
                >
                  Last
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Add Product Modal */}
      {addDialog && (
        <ModalBackdrop onClose={() => !deleting && setAddDialog(false)}>
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full">
            <h2 className="text-2xl font-bold mb-4 text-gray-800">Add New Product</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700">SKU *</label>
                <input
                  type="text"
                  value={newProduct.sku}
                  onChange={(e) => setNewProduct({ ...newProduct, sku: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Enter SKU"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700">Name *</label>
                <input
                  type="text"
                  value={newProduct.name}
                  onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Enter product name"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700">Description</label>
                <textarea
                  value={newProduct.description}
                  onChange={(e) => setNewProduct({ ...newProduct, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                  rows={3}
                  placeholder="Enter product description"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700">Status</label>
                <select
                  value={newProduct.status}
                  onChange={(e) => setNewProduct({ ...newProduct, status: Number(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value={1}>Active</option>
                  <option value={0}>Inactive</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => {
                  setAddDialog(false);
                  setNewProduct({ sku: '', name: '', description: '', status: 1 });
                }}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleAddProduct}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
              >
                Add Product
              </button>
            </div>
          </div>
        </ModalBackdrop>
      )}

      {/* Delete Confirmation Modal */}
      {deleteDialog.open && (
        <ModalBackdrop onClose={() => !deleting && setDeleteDialog({ open: false, sku: null, multiple: false })}>
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full">
            <h2 className="text-2xl font-bold mb-4 text-gray-800">Confirm Delete</h2>
            <p className="text-gray-600 mb-6">
              {deleteDialog.multiple
                ? `Are you sure you want to delete ${selectedProducts.length} selected product${selectedProducts.length > 1 ? 's' : ''}?`
                : `Are you sure you want to delete product "${deleteDialog.sku}"?`}
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteDialog({ open: false, sku: null, multiple: false })}
                disabled={deleting}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteDialog.multiple ? handleDeleteMultiple() : handleDeleteProduct(deleteDialog.sku)}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {deleting ? (
                  <>
                    <Loader2 className="animate-spin h-4 w-4" />
                    Deleting...
                  </>
                ) : (
                  'Delete'
                )}
              </button>
            </div>
          </div>
        </ModalBackdrop>
      )}

      {/* Delete All Confirmation Modal */}
      {deleteAllDialog && (
        <ModalBackdrop onClose={() => !deleting && setDeleteAllDialog(false)}>
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full">
            <div className="flex items-center gap-3 mb-4">
              <div className="bg-red-100 p-3 rounded-full">
                <AlertCircle className="h-6 w-6 text-red-600" />
              </div>
              <h2 className="text-2xl font-bold text-red-600">Confirm Delete All</h2>
            </div>
            <p className="text-gray-600 mb-2">
              Are you sure you want to delete <strong className="text-red-600">ALL {totalProducts.toLocaleString()} products</strong>?
            </p>
            <p className="text-red-600 font-semibold mb-6 text-sm">
              This action cannot be undone!
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteAllDialog(false)}
                disabled={deleting}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteAll}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {deleting ? (
                  <>
                    <Loader2 className="animate-spin h-4 w-4" />
                    Deleting...
                  </>
                ) : (
                  'Delete All'
                )}
              </button>
            </div>
          </div>
        </ModalBackdrop>
      )}
    </div>
  );
};

export default DataManager;
