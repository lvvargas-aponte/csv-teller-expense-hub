import React, { useState, useEffect } from 'react';
import {
  Container,
  Row,
  Col,
  Card,
  Button,
  Table,
  Alert,
  Spinner,
  Nav,
  Navbar,
  Badge,
  Form,
  Modal,
  ButtonGroup
} from 'react-bootstrap';
import axios from 'axios';
import 'bootstrap/dist/css/bootstrap.min.css';

const API_BASE_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

function App() {
  const [allTransactions, setAllTransactions] = useState([]);
  const [filteredTransactions, setFilteredTransactions] = useState([]);
  const [accessToken, setAccessToken] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [uploadingCSV, setUploadingCSV] = useState(false);
  const [sendingToSheet, setSendingToSheet] = useState(false);

  // Person names from backend config
  const [personNames, setPersonNames] = useState({
    person_1: 'Person 1',
    person_2: 'Person 2'
  });

  // Edit modal state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState(null);
  const [editForm, setEditForm] = useState({
    is_shared: false,
    who: '',
    what: '',
    person_1_owes: 0,
    person_2_owes: 0,
    notes: ''
  });

  // Filter state
  const [filterSource, setFilterSource] = useState('all');
  const [filterShared, setFilterShared] = useState('all');

  // Fetch person names from backend config
  const fetchPersonNames = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/config/person-names`);
      setPersonNames(response.data);
    } catch (err) {
      console.warn('Failed to fetch person names, using defaults');
    }
  };

  // Fetch all transactions
  const fetchAllTransactions = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_BASE_URL}/api/transactions/all`);
      setAllTransactions(response.data);
      applyFilters(response.data);
    } catch (err) {
      setError('Failed to fetch transactions: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  // Apply filters
  const applyFilters = (transactions = allTransactions) => {
    let filtered = [...transactions];

    if (filterSource !== 'all') {
      filtered = filtered.filter(t => t.source === filterSource);
    }

    if (filterShared === 'shared') {
      filtered = filtered.filter(t => t.is_shared);
    } else if (filterShared === 'personal') {
      filtered = filtered.filter(t => !t.is_shared);
    }

    setFilteredTransactions(filtered);
  };

  useEffect(() => {
    applyFilters();
  }, [filterSource, filterShared, allTransactions]);

  // Handle CSV upload
  const handleCSVUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      setUploadingCSV(true);
      const response = await axios.post(`${API_BASE_URL}/api/upload-csv`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setError(null);
      alert(`Success! Parsed ${response.data.count} transactions from ${file.name}`);
      fetchAllTransactions();
    } catch (err) {
      setError('Failed to upload CSV: ' + err.response?.data?.detail || err.message);
    } finally {
      setUploadingCSV(false);
      event.target.value = '';
    }
  };

  // Open edit modal
  const openEditModal = (transaction) => {
    setEditingTransaction(transaction);
    setEditForm({
      is_shared: transaction.is_shared || false,
      who: transaction.who || '',
      what: transaction.what || '',
      person_1_owes: transaction.person_1_owes || transaction.valeria_owes || 0,
      person_2_owes: transaction.person_2_owes || transaction.christy_owes || 0,
      notes: transaction.notes || ''
    });
    setShowEditModal(true);
  };

  // Save transaction edits
  const saveTransaction = async () => {
    try {
      await axios.put(`${API_BASE_URL}/api/transactions/${editingTransaction.id}`, editForm);
      setShowEditModal(false);
      fetchAllTransactions();
    } catch (err) {
      setError('Failed to update transaction: ' + err.message);
    }
  };

  // Quick mark as shared (50/50 split)
  const quickMarkShared = async (transaction) => {
    const amount = Math.abs(parseFloat(transaction.amount));
    const halfAmount = (amount / 2).toFixed(2);

    try {
      await axios.put(`${API_BASE_URL}/api/transactions/${transaction.id}`, {
        is_shared: true,
        person_1_owes: parseFloat(halfAmount),
        person_2_owes: parseFloat(halfAmount),
        who: '',
        what: '',
        notes: ''
      });
      fetchAllTransactions();
    } catch (err) {
      setError('Failed to update transaction: ' + err.message);
    }
  };

  // Export to Google Sheets format
  const exportToGoogleSheets = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/export/google-sheet`);

      // Create CSV content
      const headers = response.data.headers.join(',');
      const rows = response.data.rows.map(row =>
          response.data.headers.map(header => {
            const value = row[header];
            return typeof value === 'string' && value.includes(',') ? `"${value}"` : value;
          }).join(',')
      );

      const csvContent = [headers, ...rows].join('\n');

      // Download CSV
      const blob = new Blob([csvContent], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `shared_expenses_${new Date().toISOString().split('T')[0]}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError('Failed to export: ' + err.message);
    }
  };

  // Send directly to Google Sheet
  const sendToGoogleSheet = async () => {
    if (!window.confirm('Send all shared expenses to Google Sheet? This will clear them from the review queue.')) {
      return;
    }

    try {
      setSendingToSheet(true);
      const response = await axios.post(`${API_BASE_URL}/api/send-to-gsheet`);
      alert(`✅ Success! Sent ${response.data.count} transactions to Google Sheet`);
      fetchAllTransactions(); // Refresh to show cleared transactions
    } catch (err) {
      setError('Failed to send to Google Sheet: ' + err.response?.data?.detail || err.message);
    } finally {
      setSendingToSheet(false);
    }
  };

  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(Math.abs(parseFloat(amount)));
  };

  // Format date
  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString();
  };

  const getSourceBadgeColor = (source) => {
    const colors = {
      'discover': 'warning',
      'barclays': 'info',
      'teller': 'success',
      'unknown': 'secondary'
    };
    return colors[source] || 'secondary';
  };

  useEffect(() => {
    fetchPersonNames();
    fetchAllTransactions();
  }, []);

  return (
      <div className="App">
        <Navbar bg="dark" variant="dark" className="mb-4">
          <Container>
            <Navbar.Brand>Shared Expense Tracker</Navbar.Brand>
            <Nav className="ms-auto">
              <Button
                  variant="success"
                  size="sm"
                  className="me-2"
                  onClick={sendToGoogleSheet}
                  disabled={filteredTransactions.filter(t => t.is_shared).length === 0 || sendingToSheet}
              >
                {sendingToSheet ? <Spinner size="sm" /> : '📊 Send to GSheet'}
              </Button>
              <Button
                  variant="outline-light"
                  size="sm"
                  onClick={exportToGoogleSheets}
                  disabled={filteredTransactions.filter(t => t.is_shared).length === 0}
              >
                Export CSV
              </Button>
            </Nav>
          </Container>
        </Navbar>

        <Container>
          {error && (
              <Alert variant="warning" dismissible onClose={() => setError(null)}>
                {error}
              </Alert>
          )}

          {/* Upload Section */}
          <Row className="mb-4">
            <Col>
              <Card>
                <Card.Body>
                  <Row className="align-items-center">
                    <Col md={6}>
                      <h5 className="mb-0">Upload Bank Statements</h5>
                      <small className="text-muted">Supports Discover and Barclays CSV files</small>
                    </Col>
                    <Col md={6} className="text-md-end">
                      <Form.Group>
                        <Form.Label className="btn btn-primary mb-0">
                          {uploadingCSV ? (
                              <><Spinner size="sm" className="me-2" /> Uploading...</>
                          ) : (
                              <>Upload CSV</>
                          )}
                          <Form.Control
                              type="file"
                              accept=".csv"
                              onChange={handleCSVUpload}
                              disabled={uploadingCSV}
                              hidden
                          />
                        </Form.Label>
                      </Form.Group>
                    </Col>
                  </Row>
                </Card.Body>
              </Card>
            </Col>
          </Row>

          {/* Filters */}
          <Row className="mb-3">
            <Col md={6}>
              <Form.Group>
                <Form.Label>Filter by Source</Form.Label>
                <Form.Select value={filterSource} onChange={(e) => setFilterSource(e.target.value)}>
                  <option value="all">All Sources</option>
                  <option value="discover">Discover</option>
                  <option value="barclays">Barclays</option>
                  <option value="teller">Teller.io</option>
                </Form.Select>
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group>
                <Form.Label>Filter by Type</Form.Label>
                <Form.Select value={filterShared} onChange={(e) => setFilterShared(e.target.value)}>
                  <option value="all">All Transactions</option>
                  <option value="shared">Shared Only</option>
                  <option value="personal">Personal Only</option>
                </Form.Select>
              </Form.Group>
            </Col>
          </Row>

          {/* Summary Stats */}
          <Row className="mb-3">
            <Col md={4}>
              <Card className="text-center">
                <Card.Body>
                  <h6 className="text-muted">Total Transactions</h6>
                  <h3>{filteredTransactions.length}</h3>
                </Card.Body>
              </Card>
            </Col>
            <Col md={4}>
              <Card className="text-center">
                <Card.Body>
                  <h6 className="text-muted">Shared Expenses</h6>
                  <h3>{filteredTransactions.filter(t => t.is_shared).length}</h3>
                </Card.Body>
              </Card>
            </Col>
            <Col md={4}>
              <Card className="text-center">
                <Card.Body>
                  <h6 className="text-muted">Total Shared Amount</h6>
                  <h3>
                    {formatCurrency(
                        filteredTransactions
                            .filter(t => t.is_shared)
                            .reduce((sum, t) => sum + Math.abs(parseFloat(t.amount)), 0)
                    )}
                  </h3>
                </Card.Body>
              </Card>
            </Col>
          </Row>

          {/* Transactions Table */}
          <Row>
            <Col>
              <Card>
                <Card.Header>
                  <h5 className="mb-0">Review Transactions</h5>
                </Card.Header>
                <Card.Body>
                  {loading ? (
                      <div className="text-center py-5">
                        <Spinner animation="border" />
                      </div>
                  ) : filteredTransactions.length > 0 ? (
                      <Table striped bordered hover responsive>
                        <thead>
                        <tr>
                          <th>Date</th>
                          <th>Description</th>
                          <th>Amount</th>
                          <th>Source</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                        </thead>
                        <tbody>
                        {filteredTransactions.map((transaction) => (
                            <tr key={transaction.id} className={transaction.is_shared ? 'table-success' : ''}>
                              <td>{formatDate(transaction.date)}</td>
                              <td>
                                {transaction.description}
                                {transaction.is_shared && transaction.what && (
                                    <div><small className="text-muted">What: {transaction.what}</small></div>
                                )}
                              </td>
                              <td className="text-danger">
                                {formatCurrency(transaction.amount)}
                              </td>
                              <td>
                                <Badge bg={getSourceBadgeColor(transaction.source)}>
                                  {transaction.source}
                                </Badge>
                              </td>
                              <td>
                                {transaction.is_shared ? (
                                    <div>
                                      <Badge bg="success">Shared</Badge>
                                      <div className="mt-1">
                                        <small>{personNames.person_1}: {formatCurrency(transaction.person_1_owes || transaction.valeria_owes || 0)}</small>
                                        <br/>
                                        <small>{personNames.person_2}: {formatCurrency(transaction.person_2_owes || transaction.christy_owes || 0)}</small>
                                      </div>
                                    </div>
                                ) : (
                                    <Badge bg="secondary">Personal</Badge>
                                )}
                              </td>
                              <td>
                                <ButtonGroup size="sm">
                                  <Button
                                      variant="outline-success"
                                      onClick={() => quickMarkShared(transaction)}
                                      disabled={transaction.is_shared}
                                  >
                                    50/50
                                  </Button>
                                  <Button
                                      variant="outline-primary"
                                      onClick={() => openEditModal(transaction)}
                                  >
                                    Edit
                                  </Button>
                                </ButtonGroup>
                              </td>
                            </tr>
                        ))}
                        </tbody>
                      </Table>
                  ) : (
                      <Alert variant="info">
                        No transactions found. Upload a CSV file to get started!
                      </Alert>
                  )}
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </Container>

        {/* Edit Modal */}
        <Modal show={showEditModal} onHide={() => setShowEditModal(false)} size="lg">
          <Modal.Header closeButton>
            <Modal.Title>Edit Transaction</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {editingTransaction && (
                <>
                  <div className="mb-3">
                    <strong>{editingTransaction.description}</strong>
                    <div className="text-muted">
                      {formatDate(editingTransaction.date)} • {formatCurrency(editingTransaction.amount)}
                    </div>
                  </div>

                  <Form>
                    <Form.Check
                        type="checkbox"
                        label="This is a shared expense"
                        checked={editForm.is_shared}
                        onChange={(e) => setEditForm({...editForm, is_shared: e.target.checked})}
                        className="mb-3"
                    />

                    {editForm.is_shared && (
                        <>
                          <Row>
                            <Col md={6}>
                              <Form.Group className="mb-3">
                                <Form.Label>Who</Form.Label>
                                <Form.Control
                                    type="text"
                                    value={editForm.who}
                                    onChange={(e) => setEditForm({...editForm, who: e.target.value})}
                                    placeholder="Who paid?"
                                />
                              </Form.Group>
                            </Col>
                            <Col md={6}>
                              <Form.Group className="mb-3">
                                <Form.Label>What</Form.Label>
                                <Form.Control
                                    type="text"
                                    value={editForm.what}
                                    onChange={(e) => setEditForm({...editForm, what: e.target.value})}
                                    placeholder="What was purchased?"
                                />
                              </Form.Group>
                            </Col>
                          </Row>

                          <Row>
                            <Col md={6}>
                              <Form.Group className="mb-3">
                                <Form.Label>{personNames.person_1} Owes</Form.Label>
                                <Form.Control
                                    type="number"
                                    step="0.01"
                                    value={editForm.person_1_owes}
                                    onChange={(e) => setEditForm({...editForm, person_1_owes: parseFloat(e.target.value) || 0})}
                                />
                              </Form.Group>
                            </Col>
                            <Col md={6}>
                              <Form.Group className="mb-3">
                                <Form.Label>{personNames.person_2} Owes</Form.Label>
                                <Form.Control
                                    type="number"
                                    step="0.01"
                                    value={editForm.person_2_owes}
                                    onChange={(e) => setEditForm({...editForm, person_2_owes: parseFloat(e.target.value) || 0})}
                                />
                              </Form.Group>
                            </Col>
                          </Row>

                          <Form.Group className="mb-3">
                            <Form.Label>Notes</Form.Label>
                            <Form.Control
                                as="textarea"
                                rows={2}
                                value={editForm.notes}
                                onChange={(e) => setEditForm({...editForm, notes: e.target.value})}
                                placeholder="Additional notes..."
                            />
                          </Form.Group>
                        </>
                    )}
                  </Form>
                </>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setShowEditModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={saveTransaction}>
              Save Changes
            </Button>
          </Modal.Footer>
        </Modal>
      </div>
  );
}

export default App;