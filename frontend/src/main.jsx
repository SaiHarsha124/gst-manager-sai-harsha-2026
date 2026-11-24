import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";

import {
  LayoutDashboard,
  Users,
  FileText,
  ShieldCheck,
  History,
  Download,
  Menu,
  X,
  Plus,
  Trash2,
  Check,
  XCircle,
  RefreshCw,
  Search,
  Building2,
  ClipboardList,
  Activity,
  AlertCircle,
  Settings,
  UserCircle,
  KeyRound,
  Lock,
} from "lucide-react";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

import "./style.css";

const API = "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: API,
  timeout: 10000,
});

// ====================================================
// JWT AUTHENTICATION
// ====================================================

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("gst_admin_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      !error.config?.url?.includes("/api/auth/login")
    ) {
      sessionStorage.removeItem("gst_admin_token");
      sessionStorage.removeItem("gst_admin_username");

      window.dispatchEvent(new Event("gst-auth-expired"));
    }

    return Promise.reject(error);
  }
);

// ====================================================
// MAIN APPLICATION
// ====================================================

function App() {
  const [token, setToken] = useState(
    sessionStorage.getItem("gst_admin_token")
  );

  const [username, setUsername] = useState(
    sessionStorage.getItem("gst_admin_username") || ""
  );

  const [authLoading, setAuthLoading] = useState(true);

  const [page, setPage] = useState("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [backendOnline, setBackendOnline] = useState(false);
  const [loading, setLoading] = useState(true);

  const [analytics, setAnalytics] = useState({
    total_clients: 0,
    total_requests: 0,
    pending_requests: 0,
    approved_requests: 0,
    rejected_requests: 0,
    completed_requests: 0,
    gst_checks: 0,
    valid_gst_checks: 0,
  });

  const [clients, setClients] = useState([]);
  const [requests, setRequests] = useState([]);
  const [history, setHistory] = useState([]);

  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const [loginMessage, setLoginMessage] = useState("");

  const [adminProfile, setAdminProfile] = useState(null);

  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });

  const [passwordLoading, setPasswordLoading] = useState(false);

  const [clientForm, setClientForm] = useState({
    name: "",
    gstin: "",
    email: "",
    phone: "",
    state: "",
  });

  const [requestForm, setRequestForm] = useState({
    client_name: "",
    email: "",
    gstin: "",
    message: "",
  });

  const [gstin, setGstin] = useState("");
  const [verification, setVerification] = useState(null);

  // ==================================================
  // NOTIFICATIONS
  // ==================================================

  function notify(message) {
    setNotice(message);

    setTimeout(() => {
      setNotice("");
    }, 3500);
  }

  // ==================================================
  // LOGIN
  // ==================================================

  async function handleLogin(usernameInput, passwordInput) {
    try {
      const response = await api.post("/api/auth/login", {
        username: usernameInput,
        password: passwordInput,
      });

      const accessToken = response.data.access_token;

      sessionStorage.setItem("gst_admin_token", accessToken);

      sessionStorage.setItem(
        "gst_admin_username",
        response.data.username
      );

      setToken(accessToken);
      setUsername(response.data.username);
      setPage("dashboard");
      setLoading(true);
      setLoginMessage("");

      return true;
    } catch (error) {
      return (
        error.response?.data?.detail ||
        "Invalid username or password"
      );
    }
  }

  // ==================================================
  // LOGOUT
  // ==================================================

  function handleLogout(message = "") {
    sessionStorage.removeItem("gst_admin_token");
    sessionStorage.removeItem("gst_admin_username");

    setToken(null);
    setUsername("");
    setBackendOnline(false);
    setLoading(false);
    setPage("dashboard");
    setAdminProfile(null);

    setPasswordForm({
      current_password: "",
      new_password: "",
      confirm_password: "",
    });

    setLoginMessage(message);
  }

  // ==================================================
  // VERIFY EXISTING SESSION
  // ==================================================

  useEffect(() => {
    let active = true;

    async function checkAuthentication() {
      const savedToken = sessionStorage.getItem("gst_admin_token");

      if (!savedToken) {
        if (active) {
          setToken(null);
          setAuthLoading(false);
          setLoading(false);
        }

        return;
      }

      try {
        const response = await api.get("/api/auth/me");

        if (active) {
          setUsername(
            response.data.username ||
              sessionStorage.getItem("gst_admin_username") ||
              ""
          );

          setAdminProfile(response.data);
          setToken(savedToken);
        }
      } catch (error) {
        sessionStorage.removeItem("gst_admin_token");
        sessionStorage.removeItem("gst_admin_username");

        if (active) {
          setToken(null);
          setUsername("");
          setLoading(false);
        }
      } finally {
        if (active) {
          setAuthLoading(false);
        }
      }
    }

    checkAuthentication();

    return () => {
      active = false;
    };
  }, []);

  // ==================================================
  // LOAD DATA AFTER LOGIN
  // ==================================================

  async function loadData() {
    try {
      const results = await Promise.all([
        api.get("/api/analytics"),
        api.get("/api/clients"),
        api.get("/api/requests"),
        api.get("/api/gst/history"),
      ]);

      setAnalytics(results[0].data);
      setClients(results[1].data);
      setRequests(results[2].data);
      setHistory(results[3].data);

      setBackendOnline(true);
    } catch (error) {
      setBackendOnline(false);

      console.error("Backend connection error:", error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!token) return;

    loadData();

    const timer = setInterval(loadData, 15000);

    return () => clearInterval(timer);
  }, [token]);

  // ==================================================
  // LOAD ADMIN PROFILE
  // ==================================================

  async function loadAdminProfile() {
    try {
      const response = await api.get("/api/auth/me");

      setAdminProfile(response.data);
      setUsername(response.data.username);
    } catch (error) {
      console.error("Unable to load admin profile:", error);
    }
  }

  useEffect(() => {
    if (token && page === "settings") {
      loadAdminProfile();
    }
  }, [page, token]);

  // ==================================================
  // CHANGE ADMIN PASSWORD
  // ==================================================

  async function changePassword(event) {
    event.preventDefault();

    const {
      current_password,
      new_password,
      confirm_password,
    } = passwordForm;

    if (!current_password || !new_password || !confirm_password) {
      notify("Please fill in all password fields");
      return;
    }

    if (new_password.length < 12) {
      notify("New password must contain at least 12 characters");
      return;
    }

    if (new_password !== confirm_password) {
      notify("New passwords do not match");
      return;
    }

    if (current_password === new_password) {
      notify("New password must be different");
      return;
    }

    setPasswordLoading(true);

    try {
      await api.post("/api/auth/change-password", {
        current_password,
        new_password,
      });

      setPasswordForm({
        current_password: "",
        new_password: "",
        confirm_password: "",
      });

      handleLogout(
        "Password changed successfully. Please log in again."
      );

    } catch (error) {
      notify(
        error.response?.data?.detail ||
          "Unable to change password"
      );
    } finally {
      setPasswordLoading(false);
    }
  }

  // ==================================================
  // AUTOMATIC SESSION EXPIRY
  // ==================================================

  useEffect(() => {
    function handleExpiredSession() {
      handleLogout(
        "Your session expired. Please log in again."
      );
    }

    window.addEventListener(
      "gst-auth-expired",
      handleExpiredSession
    );

    return () => {
      window.removeEventListener(
        "gst-auth-expired",
        handleExpiredSession
      );
    };
  }, []);

  // ==================================================
  // CLIENT MANAGEMENT
  // ==================================================

  async function addClient(event) {
    event.preventDefault();

    try {
      await api.post("/api/clients", {
        ...clientForm,
        gstin: clientForm.gstin.toUpperCase(),
      });

      setClientForm({
        name: "",
        gstin: "",
        email: "",
        phone: "",
        state: "",
      });

      notify("Client added successfully");

      loadData();
    } catch (error) {
      notify(
        error.response?.data?.detail ||
          "Unable to add client"
      );
    }
  }

  async function deleteClient(id) {
    if (!window.confirm("Delete this client?")) return;

    try {
      await api.delete(`/api/clients/${id}`);

      notify("Client deleted successfully");

      loadData();
    } catch (error) {
      notify("Unable to delete client");
    }
  }

  // ==================================================
  // REQUEST MANAGEMENT
  // ==================================================

  async function addRequest(event) {
    event.preventDefault();

    try {
      await api.post("/api/requests", requestForm);

      setRequestForm({
        client_name: "",
        email: "",
        gstin: "",
        message: "",
      });

      notify("Request created successfully");

      loadData();
    } catch (error) {
      notify(
        error.response?.data?.detail ||
          "Unable to create request"
      );
    }
  }

  async function updateRequest(id, status) {
    try {
      await api.post(`/api/requests/${id}/action`, {
        status,
      });

      notify(`Request ${status.toLowerCase()}`);

      loadData();
    } catch (error) {
      notify("Unable to update request");
    }
  }

  async function deleteRequest(id) {
    if (!window.confirm("Delete this request?")) return;

    try {
      await api.delete(`/api/requests/${id}`);

      notify("Request deleted");

      loadData();
    } catch (error) {
      notify("Unable to delete request");
    }
  }

  // ==================================================
  // GST VERIFICATION
  // ==================================================

  async function verifyGST(event) {
    event.preventDefault();

    setVerification(null);

    try {
      const response = await api.post("/api/gst/verify", {
        gstin: gstin.toUpperCase(),
      });

      setVerification(response.data);

      notify("GSTIN format check completed");

      loadData();
    } catch (error) {
      notify(
        error.response?.data?.detail ||
          "Verification failed"
      );
    }
  }

  async function deleteHistory(id) {
    if (!window.confirm("Delete this history record?")) return;

    try {
      await api.delete(`/api/gst/history/${id}`);

      notify("History deleted");

      loadData();
    } catch (error) {
      notify("Unable to delete history");
    }
  }

  async function clearHistory() {
    if (!window.confirm("Clear all GST history?")) return;

    try {
      await api.delete("/api/gst/history");

      notify("GST history cleared");

      loadData();
    } catch (error) {
      notify("Unable to clear history");
    }
  }

  // ==================================================
  // CSV EXPORT
  // ==================================================

  async function exportCSV(type) {
    try {
      const response = await api.get(
        `/api/export/${type}`,
        {
          responseType: "blob",
        }
      );

      const url = window.URL.createObjectURL(
        new Blob([response.data])
      );

      const link = document.createElement("a");

      link.href = url;
      link.download = `${type}.csv`;

      document.body.appendChild(link);

      link.click();

      link.remove();

      window.URL.revokeObjectURL(url);

      notify("CSV downloaded successfully");
    } catch (error) {
      notify("Export failed");
    }
  }

  // ==================================================
  // SIDEBAR
  // ==================================================

  const navigation = [
    {
      id: "dashboard",
      label: "Dashboard",
      icon: LayoutDashboard,
    },
    {
      id: "clients",
      label: "Clients",
      icon: Users,
    },
    {
      id: "requests",
      label: "Demo Requests",
      icon: FileText,
    },
    {
      id: "verify",
      label: "GST Verification",
      icon: ShieldCheck,
    },
    {
      id: "history",
      label: "Verification History",
      icon: History,
    },
    {
      id: "settings",
      label: "Admin Settings",
      icon: Settings,
    },
  ];

  function navigate(id) {
    setPage(id);
    setSidebarOpen(false);
    setNotice("");
  }

  // ==================================================
  // PAGE TITLES
  // ==================================================

  const pageTitle = {
    dashboard: "Dashboard",
    clients: "Client Management",
    requests: "Demo Requests",
    verify: "GST Verification",
    history: "Verification History",
    settings: "Admin Settings",
  };

  // ==================================================
  // DASHBOARD
  // ==================================================

  function Dashboard() {
    const chartData = [
      {
        name: "Pending",
        value: analytics.pending_requests,
      },
      {
        name: "Approved",
        value: analytics.approved_requests,
      },
      {
        name: "Completed",
        value: analytics.completed_requests,
      },
      {
        name: "Rejected",
        value: analytics.rejected_requests,
      },
    ];

    return (
      <>
        <div className="welcome">
          <div>
            <h2>Welcome to GST Manager 👋</h2>

            <p>
              Manage your clients, requests and GSTIN
              format checks from one place.
            </p>
          </div>

          <button
            className="secondary-btn"
            onClick={loadData}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>

        <div className="stats-grid">
          <StatCard
            title="Total Clients"
            value={analytics.total_clients}
            icon={<Users />}
            color="blue"
          />

          <StatCard
            title="Total Requests"
            value={analytics.total_requests}
            icon={<ClipboardList />}
            color="purple"
          />

          <StatCard
            title="Pending Requests"
            value={analytics.pending_requests}
            icon={<Activity />}
            color="orange"
          />

          <StatCard
            title="GST Checks"
            value={analytics.gst_checks}
            icon={<ShieldCheck />}
            color="green"
          />
        </div>

        <div className="dashboard-grid">
          <div className="panel chart-panel">
            <div className="panel-heading">
              <div>
                <h3>Request Analytics</h3>
                <p>Request status overview</p>
              </div>
            </div>

            <div className="chart">
              <ResponsiveContainer
                width="100%"
                height="100%"
              >
                <BarChart data={chartData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    vertical={false}
                  />

                  <XAxis dataKey="name" />

                  <YAxis allowDecimals={false} />

                  <Tooltip />

                  <Bar
                    dataKey="value"
                    fill="#4f46e5"
                    radius={[6, 6, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <div>
                <h3>Request Summary</h3>
                <p>Current request status</p>
              </div>
            </div>

            <SummaryRow
              label="Pending"
              value={analytics.pending_requests}
            />

            <SummaryRow
              label="Approved"
              value={analytics.approved_requests}
            />

            <SummaryRow
              label="Completed"
              value={analytics.completed_requests}
            />

            <SummaryRow
              label="Rejected"
              value={analytics.rejected_requests}
            />

            <div className="summary-total">
              <span>Valid GSTIN formats</span>

              <strong>
                {analytics.valid_gst_checks}
              </strong>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <div>
              <h3>Recent Clients</h3>
              <p>Latest registered clients</p>
            </div>

            <button
              className="text-btn"
              onClick={() => navigate("clients")}
            >
              View all
            </button>
          </div>

          <ClientTable
            items={clients.slice(0, 5)}
            onDelete={deleteClient}
          />
        </div>
      </>
    );
  }

  // ==================================================
  // CLIENTS PAGE
  // ==================================================

  function ClientsPage() {
    const filtered = clients.filter((item) => {
      const query = search.toLowerCase();

      return (
        item.name.toLowerCase().includes(query) ||
        item.gstin.toLowerCase().includes(query) ||
        item.email.toLowerCase().includes(query)
      );
    });

    return (
      <>
        <div className="panel">
          <div className="panel-heading">
            <div>
              <h3>Add New Client</h3>
              <p>Enter client information</p>
            </div>
          </div>

          <form
            className="form-grid"
            onSubmit={addClient}
          >
            <Input
              label="Client Name"
              value={clientForm.name}
              onChange={(v) =>
                setClientForm({
                  ...clientForm,
                  name: v,
                })
              }
              required
            />

            <Input
              label="GSTIN"
              value={clientForm.gstin}
              onChange={(v) =>
                setClientForm({
                  ...clientForm,
                  gstin: v.toUpperCase(),
                })
              }
              maxLength={15}
              required
            />

            <Input
              label="Email"
              type="email"
              value={clientForm.email}
              onChange={(v) =>
                setClientForm({
                  ...clientForm,
                  email: v,
                })
              }
            />

            <Input
              label="Phone"
              value={clientForm.phone}
              onChange={(v) =>
                setClientForm({
                  ...clientForm,
                  phone: v,
                })
              }
            />

            <Input
              label="State"
              value={clientForm.state}
              onChange={(v) =>
                setClientForm({
                  ...clientForm,
                  state: v,
                })
              }
            />

            <div className="form-action">
              <button className="primary-btn">
                <Plus size={16} />
                Add Client
              </button>
            </div>
          </form>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <div>
              <h3>All Clients</h3>
              <p>
                {clients.length} clients registered
              </p>
            </div>

            <button
              className="secondary-btn"
              onClick={() => exportCSV("clients")}
            >
              <Download size={16} />
              Export CSV
            </button>
          </div>

          <SearchBox
            value={search}
            onChange={setSearch}
            placeholder="Search clients..."
          />

          <ClientTable
            items={filtered}
            onDelete={deleteClient}
          />
        </div>
      </>
    );
  }

  // ==================================================
  // REQUESTS PAGE
  // ==================================================

  function RequestsPage() {
    return (
      <>
        <div className="panel">
          <div className="panel-heading">
            <div>
              <h3>Create Demo Request</h3>
              <p>Register a new demo request</p>
            </div>
          </div>

          <form
            className="form-grid"
            onSubmit={addRequest}
          >
            <Input
              label="Client Name"
              value={requestForm.client_name}
              onChange={(v) =>
                setRequestForm({
                  ...requestForm,
                  client_name: v,
                })
              }
              required
            />

            <Input
              label="Email"
              type="email"
              value={requestForm.email}
              onChange={(v) =>
                setRequestForm({
                  ...requestForm,
                  email: v,
                })
              }
            />

            <Input
              label="GSTIN"
              value={requestForm.gstin}
              onChange={(v) =>
                setRequestForm({
                  ...requestForm,
                  gstin: v.toUpperCase(),
                })
              }
              maxLength={15}
            />

            <div className="field full-width">
              <label>Message</label>

              <textarea
                value={requestForm.message}
                onChange={(e) =>
                  setRequestForm({
                    ...requestForm,
                    message: e.target.value,
                  })
                }
                placeholder="Enter request details"
              />
            </div>

            <div className="form-action">
              <button className="primary-btn">
                <Plus size={16} />
                Create Request
              </button>
            </div>
          </form>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <div>
              <h3>All Requests</h3>
              <p>
                {requests.length} total requests
              </p>
            </div>

            <button
              className="secondary-btn"
              onClick={() => exportCSV("requests")}
            >
              <Download size={16} />
              Export CSV
            </button>
          </div>

          <RequestTable
            items={requests}
            onUpdate={updateRequest}
            onDelete={deleteRequest}
          />
        </div>
      </>
    );
  }

  // ==================================================
  // GST VERIFICATION PAGE
  // ==================================================

  function VerifyPage() {
    return (
      <div className="verify-container">
        <div className="panel verify-panel">
          <div className="verify-icon">
            <ShieldCheck size={34} />
          </div>

          <h2>GSTIN Format Verification</h2>

          <p>
            Enter a 15-character GSTIN to check whether
            its format matches the expected structure.
          </p>

          <form onSubmit={verifyGST}>
            <div className="field">
              <label>GSTIN Number</label>

              <input
                value={gstin}
                onChange={(e) =>
                  setGstin(e.target.value.toUpperCase())
                }
                placeholder="Enter GSTIN"
                maxLength={15}
                required
              />
            </div>

            <button className="primary-btn verify-btn">
              <ShieldCheck size={17} />
              Verify GSTIN Format
            </button>
          </form>

          {verification && (
            <div
              className={`verification-result ${
                verification.valid ? "success" : "failure"
              }`}
            >
              {verification.valid ? (
                <Check size={24} />
              ) : (
                <XCircle size={24} />
              )}

              <div>
                <strong>{verification.result}</strong>
                <p>{verification.message}</p>
              </div>
            </div>
          )}

          <div className="info-box">
            <AlertCircle size={18} />

            <span>
              This is a format-only check. It does not
              confirm GST registration or live status
              with the government GST portal.
            </span>
          </div>
        </div>
      </div>
    );
  }

  // ==================================================
  // HISTORY PAGE
  // ==================================================

  function HistoryPage() {
    return (
      <div className="panel">
        <div className="panel-heading">
          <div>
            <h3>GST Verification History</h3>

            <p>
              {history.length} verification records
            </p>
          </div>

          <button
            className="danger-btn"
            onClick={clearHistory}
          >
            <Trash2 size={16} />
            Clear History
          </button>
        </div>

        <HistoryTable
          items={history}
          onDelete={deleteHistory}
        />
      </div>
    );
  }

  // ==================================================
  // ADMIN SETTINGS PAGE
  // ==================================================

  function SettingsPage() {
    return (
      <>
        <div className="panel">
          <div className="panel-heading">
            <div>
              <h3>
                <UserCircle
                  size={20}
                  style={{ verticalAlign: "middle", marginRight: 8 }}
                />
                Administrator Profile
              </h3>

              <p>Your administrator account information</p>
            </div>
          </div>

          <div className="profile-card">
            <div className="profile-avatar">
              <UserCircle size={42} />
            </div>

            <div className="profile-details">
              <h3>{adminProfile?.username || username}</h3>

              <p>Administrator</p>

              <span className="status-pill completed">
                Active Account
              </span>

              <div className="profile-meta">
                <span>
                  Account ID: {adminProfile?.id ?? "Loading..."}
                </span>

                <span>
                  Created:{" "}
                  {adminProfile?.created_at
                    ? new Date(
                        adminProfile.created_at
                      ).toLocaleDateString()
                    : "Loading..."}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <div>
              <h3>
                <KeyRound
                  size={20}
                  style={{ verticalAlign: "middle", marginRight: 8 }}
                />
                Change Password
              </h3>

              <p>
                Update your administrator password securely.
              </p>
            </div>
          </div>

          <form
            className="form-grid"
            onSubmit={changePassword}
          >
            <div className="field full-width">
              <label>Current Password</label>

              <input
                type="password"
                autoComplete="current-password"
                value={passwordForm.current_password}
                onChange={(e) =>
                  setPasswordForm({
                    ...passwordForm,
                    current_password: e.target.value,
                  })
                }
                placeholder="Enter current password"
                required
              />
            </div>

            <div className="field full-width">
              <label>New Password</label>

              <input
                type="password"
                autoComplete="new-password"
                value={passwordForm.new_password}
                onChange={(e) =>
                  setPasswordForm({
                    ...passwordForm,
                    new_password: e.target.value,
                  })
                }
                placeholder="Minimum 12 characters"
                minLength={12}
                maxLength={200}
                required
              />

              <small>
                Use at least 12 characters with a mixture
                of letters, numbers and symbols.
              </small>
            </div>

            <div className="field full-width">
              <label>Confirm New Password</label>

              <input
                type="password"
                autoComplete="new-password"
                value={passwordForm.confirm_password}
                onChange={(e) =>
                  setPasswordForm({
                    ...passwordForm,
                    confirm_password: e.target.value,
                  })
                }
                placeholder="Confirm your new password"
                minLength={12}
                maxLength={200}
                required
              />
            </div>

            <div className="form-action">
              <button
                type="submit"
                className="primary-btn"
                disabled={passwordLoading}
              >
                <Lock size={16} />

                {passwordLoading
                  ? "Updating Password..."
                  : "Change Password"}
              </button>
            </div>
          </form>

          <div className="info-box">
            <AlertCircle size={18} />

            <span>
              After changing your password, your current
              session and previously issued access tokens
              will be invalidated. You must log in again
              using your new password.
            </span>
          </div>
        </div>
      </>
    );
  }

  // ==================================================
  // MAIN RENDER
  // ==================================================

  if (authLoading) {
    return (
      <div className="loading">
        <RefreshCw className="spin" />
        Checking administrator session...
      </div>
    );
  }

  if (!token) {
    return (
      <LoginScreen
        onLogin={handleLogin}
        initialMessage={loginMessage}
      />
    );
  }

  return (
    <div className="app-layout">
      {sidebarOpen && (
        <div
          className="mobile-overlay"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`sidebar ${
          sidebarOpen ? "open" : ""
        }`}
      >
        <div className="brand">
          <div className="brand-icon">
            <Building2 size={24} />
          </div>

          <div>
            <h2>GST Manager</h2>
            <span>Management System</span>
          </div>

          <button
            className="close-sidebar"
            onClick={() => setSidebarOpen(false)}
          >
            <X />
          </button>
        </div>

        <div className="nav-label">MENU</div>

        <nav>
          {navigation.map((item) => {
            const Icon = item.icon;

            return (
              <button
                key={item.id}
                className={`nav-item ${
                  page === item.id ? "active" : ""
                }`}
                onClick={() => navigate(item.id)}
              >
                <Icon size={19} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-bottom">
          <div
            className={`connection ${
              backendOnline ? "online" : "offline"
            }`}
          >
            <span className="connection-dot" />

            {backendOnline
              ? "Backend Connected"
              : "Backend Disconnected"}
          </div>

          <p>GST Manager v4.0.0</p>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="menu-button"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu />
            </button>

            <div>
              <h1>{pageTitle[page]}</h1>
              <p>GST Management Dashboard</p>
            </div>
          </div>

          <div className="topbar-right">
            <div
              className={`status-badge ${
                backendOnline ? "online" : "offline"
              }`}
            >
              <span className="connection-dot" />

              {backendOnline ? "Online" : "Offline"}
            </div>

            <span
              style={{
                fontSize: "13px",
                fontWeight: 600,
              }}
            >
              Admin: {username}
            </span>

            <button
              className="secondary-btn"
              onClick={handleLogout}
            >
              Logout
            </button>
          </div>
        </header>

        <div className="content">
          {notice && (
            <div className="notification">
              {notice}
            </div>
          )}

          {!backendOnline && (
            <div className="error-banner">
              <AlertCircle size={18} />

              <span>
                Backend connection failed. Start the
                FastAPI server on port 8000.
              </span>

              <button onClick={loadData}>
                Retry
              </button>
            </div>
          )}

          {loading ? (
            <div className="loading">
              <RefreshCw className="spin" />
              Loading dashboard...
            </div>
          ) : (
            <>
              {page === "dashboard" && <Dashboard />}

              {page === "clients" && <ClientsPage />}

              {page === "requests" && <RequestsPage />}

              {page === "verify" && <VerifyPage />}

              {page === "history" && <HistoryPage />}

              {page === "settings" && <SettingsPage />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

// ====================================================
// LOGIN SCREEN
// ====================================================

function LoginScreen({ onLogin, initialMessage = "" }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState("");
  const [message, setMessage] = useState(initialMessage);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();

    setError("");
    setMessage("");
    setSubmitting(true);

    const result = await onLogin(username, password);

    if (result !== true) {
      setError(String(result));
    }

    setSubmitting(false);
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        background: "#f1f5f9",
        padding: "20px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
          background: "#fff",
          padding: "36px",
          borderRadius: "16px",
          boxShadow: "0 10px 35px rgba(0,0,0,0.08)",
        }}
      >
        <div
          style={{
            textAlign: "center",
            marginBottom: "28px",
          }}
        >
          <ShieldCheck
            size={42}
            color="#4f46e5"
          />

          <h2 style={{ marginBottom: "8px" }}>
            GST Manager
          </h2>

          <p style={{ color: "#64748b" }}>
            Administrator Login
          </p>
        </div>

        {message && (
          <div
            style={{
              color: "#166534",
              background: "#f0fdf4",
              padding: "12px",
              borderRadius: "8px",
              marginBottom: "16px",
              fontSize: "14px",
            }}
          >
            {message}
          </div>
        )}

        <form onSubmit={submit}>
          <div className="field">
            <label>Username</label>

            <input
              type="text"
              value={username}
              onChange={(e) =>
                setUsername(e.target.value)
              }
              placeholder="Enter admin username"
              autoComplete="username"
              required
            />
          </div>

          <div
            className="field"
            style={{ marginTop: "18px" }}
          >
            <label>Password</label>

            <input
              type="password"
              value={password}
              onChange={(e) =>
                setPassword(e.target.value)
              }
              placeholder="Enter admin password"
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <div
              style={{
                color: "#dc2626",
                background: "#fef2f2",
                padding: "12px",
                borderRadius: "8px",
                marginTop: "16px",
                fontSize: "14px",
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            className="primary-btn"
            disabled={submitting}
            style={{
              width: "100%",
              justifyContent: "center",
              marginTop: "24px",
              padding: "13px",
            }}
          >
            {submitting
              ? "Signing in..."
              : "Sign In"}
          </button>
        </form>

        <p
          style={{
            textAlign: "center",
            marginTop: "24px",
            fontSize: "12px",
            color: "#94a3b8",
          }}
        >
          GST Manager · Secure Admin Access
        </p>
      </div>
    </div>
  );
}

// ====================================================
// REUSABLE COMPONENTS
// ====================================================

function StatCard({ title, value, icon, color }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${color}`}>
        {icon}
      </div>

      <div>
        <p>{title}</p>
        <h2>{value}</h2>
      </div>
    </div>
  );
}

function SummaryRow({ label, value }) {
  return (
    <div className="summary-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  type = "text",
  required = false,
  maxLength,
}) {
  return (
    <div className="field">
      <label>{label}</label>

      <input
        type={type}
        value={value}
        onChange={(e) =>
          onChange(e.target.value)
        }
        required={required}
        maxLength={maxLength}
        placeholder={`Enter ${label.toLowerCase()}`}
      />
    </div>
  );
}

function SearchBox({
  value,
  onChange,
  placeholder,
}) {
  return (
    <div className="search-box">
      <Search size={18} />

      <input
        value={value}
        onChange={(e) =>
          onChange(e.target.value)
        }
        placeholder={placeholder}
      />
    </div>
  );
}

function EmptyState({ message }) {
  return (
    <div className="empty-state">
      <FileText size={28} />
      <p>{message}</p>
    </div>
  );
}

// ====================================================
// CLIENT TABLE
// ====================================================

function ClientTable({ items, onDelete }) {
  if (!items.length) {
    return (
      <EmptyState message="No clients found" />
    );
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Client</th>
            <th>GSTIN</th>
            <th>Email</th>
            <th>State</th>
            <th>Action</th>
          </tr>
        </thead>

        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>#{item.id}</td>

              <td className="bold-cell">
                {item.name}
              </td>

              <td>{item.gstin}</td>

              <td>{item.email || "-"}</td>

              <td>{item.state || "-"}</td>

              <td>
                <button
                  className="icon-btn delete"
                  onClick={() =>
                    onDelete(item.id)
                  }
                  title="Delete client"
                >
                  <Trash2 size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ====================================================
// REQUEST TABLE
// ====================================================

function RequestTable({
  items,
  onUpdate,
  onDelete,
}) {
  if (!items.length) {
    return (
      <EmptyState message="No requests found" />
    );
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Client</th>
            <th>Email</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>

        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>#{item.id}</td>

              <td className="bold-cell">
                {item.client_name}
              </td>

              <td>{item.email || "-"}</td>

              <td>
                <span
                  className={`status-pill ${item.status.toLowerCase()}`}
                >
                  {item.status}
                </span>
              </td>

              <td>
                <div className="action-group">
                  {item.status !== "Approved" &&
                    item.status !== "Completed" && (
                      <button
                        className="icon-btn approve"
                        title="Approve"
                        onClick={() =>
                          onUpdate(item.id, "Approved")
                        }
                      >
                        <Check size={16} />
                      </button>
                    )}

                  {item.status !== "Rejected" &&
                    item.status !== "Completed" && (
                      <button
                        className="icon-btn reject"
                        title="Reject"
                        onClick={() =>
                          onUpdate(item.id, "Rejected")
                        }
                      >
                        <XCircle size={16} />
                      </button>
                    )}

                  {item.status === "Approved" && (
                    <button
                      className="icon-btn approve"
                      title="Complete"
                      onClick={() =>
                        onUpdate(item.id, "Completed")
                      }
                    >
                      <Check size={16} />
                    </button>
                  )}

                  <button
                    className="icon-btn delete"
                    title="Delete"
                    onClick={() =>
                      onDelete(item.id)
                    }
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ====================================================
// HISTORY TABLE
// ====================================================

function HistoryTable({ items, onDelete }) {
  if (!items.length) {
    return (
      <EmptyState message="No verification history found" />
    );
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>GSTIN</th>
            <th>Result</th>
            <th>Message</th>
            <th>Date</th>
            <th>Action</th>
          </tr>
        </thead>

        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>#{item.id}</td>

              <td className="bold-cell">
                {item.gstin}
              </td>

              <td>
                <span
                  className={`status-pill ${
                    item.result === "Format valid"
                      ? "completed"
                      : "rejected"
                  }`}
                >
                  {item.result}
                </span>
              </td>

              <td>{item.message}</td>

              <td>
                {item.checked_at
                  ? new Date(
                      item.checked_at
                    ).toLocaleString()
                  : "-"}
              </td>

              <td>
                <button
                  className="icon-btn delete"
                  onClick={() =>
                    onDelete(item.id)
                  }
                >
                  <Trash2 size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ====================================================
// APPLICATION ENTRY
// ====================================================

createRoot(
  document.getElementById("root")
).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
