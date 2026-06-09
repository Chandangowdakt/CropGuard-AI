const { useState, useEffect, useCallback, useRef, useContext, createContext, useMemo } = React;

const API_BASE = (() => {
  const { origin, port } = window.location;
  if (origin === "file://" || port === "5500") {
    return "http://localhost:8001";
  }
  return origin;
})();

// ── API helpers ───────────────────────────────────────────────────────────────
function getToken() {
  return localStorage.getItem("cropguard_token");
}

function setAuth(token, user) {
  localStorage.setItem("cropguard_token", token);
  localStorage.setItem("cropguard_user", JSON.stringify(user));
}

function clearAuth() {
  localStorage.removeItem("cropguard_token");
  localStorage.removeItem("cropguard_user");
}

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("cropguard_user"));
  } catch {
    return null;
  }
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearAuth();
    window.location.reload();
    throw new Error("Session expired — please log in again");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data.detail === "string" ? data.detail : data.detail?.[0]?.msg || "Request failed";
    throw new Error(msg);
  }
  return data;
}

// ── UI primitives ─────────────────────────────────────────────────────────────
function Spinner({ label = "Loading…" }) {
  return (
    <div className="spinner-wrap">
      <div className="spinner" />
      <span>{label}</span>
    </div>
  );
}

// ── Toasts ────────────────────────────────────────────────────────────────────
const ToastContext = createContext(null);

function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const pushToast = useCallback((toast) => {
    const id = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const t = { id, type: toast.type || "info", message: toast.message || "" };
    setToasts((prev) => [...prev, t]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, 4000);
  }, []);

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-relevant="additions removals">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`} role="status">
            <div className="toast-msg">{t.message}</div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function useToast() {
  return useContext(ToastContext) || { pushToast: () => {} };
}

// ── Skeletons (dashboard shimmer) ──────────────────────────────────────────────
function Skeleton({ className = "", style = {} }) {
  return <div className={`skeleton ${className}`} style={style} />;
}

function StatCardSkeleton({ variant = "stat-green" }) {
  return (
    <div className={`stat-card ${variant} stat-skeleton`}>
      <div className="stat-icon"><Skeleton className="sk-circle" /></div>
      <h4><Skeleton className="sk-line" style={{ width: "70%" }} /></h4>
      <div className="stat-value"><Skeleton className="sk-line sk-big" style={{ width: "55%" }} /></div>
    </div>
  );
}

function CardSkeleton({ titleWidth = "55%", lines = 4 }) {
  return (
    <div className="card">
      <div className="card-title"><Skeleton className="sk-line" style={{ width: titleWidth }} /></div>
      <div className="sk-body">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} className="sk-line" style={{ width: `${90 - i * 8}%` }} />
        ))}
      </div>
    </div>
  );
}

function ClassBadge({ cls }) {
  const map = {
    healthy: "badge-healthy",
    diseased: "badge-diseased",
    pest_affected: "badge-pest",
    water_stressed: "badge-water",
    uncertain: "badge-uncertain",
  };
  return <span className={`badge ${map[cls] || "badge-healthy"}`}>{(cls || "").replace(/_/g, " ")}</span>;
}

function AlertThumb({ alertId }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let objectUrl = null;
    let cancelled = false;
    const token = getToken();
    fetch(`${API_BASE}/api/alerts/${alertId}/image`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (blob && !cancelled) {
          objectUrl = URL.createObjectURL(blob);
          setSrc(objectUrl);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [alertId]);
  if (!src) return <span className="thumb-placeholder">📷</span>;
  return <img className="thumb" src={src} alt="" />;
}

function ErrorBox({ message }) {
  if (!message) return null;
  return <div className="alert-error">{message}</div>;
}

const INDIAN_STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
  "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
  "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal",
  "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
  "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
];

const CROP_OPTIONS = [
  { value: "chrysanthemum", label: "Chrysanthemum" },
  { value: "rose", label: "Rose" },
  { value: "marigold", label: "Marigold" },
  { value: "tomato", label: "Tomato" },
  { value: "other", label: "Other" },
];

function formatCrop(crop) {
  const found = CROP_OPTIONS.find((c) => c.value === (crop || "").toLowerCase());
  if (found) return found.label;
  return (crop || "Crop").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function healthScoreClass(score) {
  if (score >= 70) return "health-good";
  if (score >= 40) return "health-warn";
  return "health-bad";
}

function formatTimestamp(ts) {
  if (!ts) return "Never scanned";
  return new Date(ts).toLocaleString();
}

function DetectionThumb({ detectionId }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let objectUrl = null;
    let cancelled = false;
    const token = getToken();
    fetch(`${API_BASE}/api/detections/${detectionId}/image`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (blob && !cancelled) {
          objectUrl = URL.createObjectURL(blob);
          setSrc(objectUrl);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [detectionId]);
  if (!src) return <span className="thumb-placeholder">📷</span>;
  return <img className="thumb" src={src} alt="" />;
}

function HealthScoreBadge({ score }) {
  return (
    <span className={`health-score ${healthScoreClass(score)}`}>
      {Math.round(score)}% health
    </span>
  );
}

// ── PAGE 1: Auth ──────────────────────────────────────────────────────────────
function AuthPage({ onSuccess }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function loginRequest(email, password) {
    let res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (res.status === 422) {
      res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: email, password }),
      });
    }
    const data = await res.json();
    if (!res.ok) {
      const msg = typeof data.detail === "string" ? data.detail : "Login failed";
      throw new Error(msg);
    }
    return data;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      let data;
      if (mode === "login") {
        data = await loginRequest(email, password);
      } else {
        data = await api("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({ name, email, password, role: "farmer" }),
        });
      }
      setAuth(data.access_token, data.user);
      onSuccess(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card fade-in">
        <div className="auth-logo">
          <div className="icon">🌿</div>
          <h1>CropGuard <span style={{ color: "var(--secondary)" }}>AI</span></h1>
          <p>Smart plantation monitoring for Indian farmers</p>
        </div>

        <div className="auth-toggle">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Sign In</button>
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Register</button>
        </div>

        <ErrorBox message={error} />

        <form onSubmit={handleSubmit}>
          {mode === "register" && (
            <div className="form-group">
              <label>Full name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ramesh Kumar" required />
            </div>
          )}
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="farmer@cropguard.ai" required />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required minLength={6} />
          </div>
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Please wait…" : mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        {mode === "login" && (
          <p style={{ textAlign: "center", marginTop: 16, fontSize: "0.82rem", color: "var(--muted)" }}>
            Demo: farmer@cropguard.ai / farmer123
          </p>
        )}
      </div>
    </div>
  );
}

// ── Dashboard sections ────────────────────────────────────────────────────────
function StatsRow({ farms, detectionsToday, activeAlerts, healthScore, loading }) {
  if (loading) {
    return (
      <div className="stats-row fade-in">
        <StatCardSkeleton variant="stat-green" />
        <StatCardSkeleton variant="stat-blue" />
        <StatCardSkeleton variant="stat-red" />
        <StatCardSkeleton variant="stat-gold" />
      </div>
    );
  }
  return (
    <div className="stats-row fade-in">
      <div className="stat-card stat-green">
        <div className="stat-icon">🏡</div>
        <h4>Total Farms</h4>
        <div className="stat-value">{farms}</div>
      </div>
      <div className="stat-card stat-blue">
        <div className="stat-icon">📷</div>
        <h4>Detections Today</h4>
        <div className="stat-value">{detectionsToday}</div>
      </div>
      <div className="stat-card stat-red">
        <div className="stat-icon">🔔</div>
        <h4>Active Alerts</h4>
        <div className="stat-value">{activeAlerts}</div>
      </div>
      <div className="stat-card stat-gold">
        <div className="stat-icon">💚</div>
        <h4>Health Score</h4>
        <div className="stat-value">{healthScore}%</div>
      </div>
    </div>
  );
}

function HealthChart({ summary, loading }) {
  const classes = [
    { key: "healthy", label: "Healthy", color: "var(--secondary)" },
    { key: "diseased", label: "Diseased", color: "var(--danger)" },
    { key: "pest_affected", label: "Pest", color: "var(--warning)" },
    { key: "water_stressed", label: "Water Stressed", color: "var(--water)" },
  ];
  const counts = summary?.class_counts || {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;

  if (loading) return <CardSkeleton titleWidth="60%" lines={5} />;

  return (
    <div className="card fade-in-delay">
      <div className="card-title">📊 Farm Health Overview</div>
      <div className="health-chart">
        {classes.map((c) => {
          const n = counts[c.key] || 0;
          const pct = Math.round((n / total) * 100);
          return (
            <div className="bar-row" key={c.key}>
              <div className="bar-label">{c.label}</div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${Math.max(pct, n ? 8 : 0)}%`, background: c.color }}>
                  {pct}%
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {total <= 1 && !counts.healthy && (
        <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 12 }}>No detections yet — upload a photo to analyse.</p>
      )}
    </div>
  );
}

function DiseaseRiskBadge({ risk, compact = false }) {
  const map = {
    LOW: "risk-low",
    MEDIUM: "risk-medium",
    HIGH: "risk-high",
  };
  const cls = map[risk] || "risk-low";
  const label = risk || "LOW";
  return (
    <span className={`disease-risk-badge ${cls}`}>
      {compact ? label : `Disease Risk: ${label}`}
    </span>
  );
}

function WeatherWidget({ farmId, farmName }) {
  const [weather, setWeather] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadWeather = useCallback(async () => {
    if (!farmId) return;
    setLoading(true);
    setError("");
    try {
      const data = await api(`/api/farms/${farmId}/weather`);
      setWeather(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [farmId]);

  useEffect(() => {
    loadWeather();
    const interval = setInterval(loadWeather, 600000);
    return () => clearInterval(interval);
  }, [loadWeather]);

  const displayName = farmName || weather?.farm_name || "Farm";
  const locationLabel = displayName.includes("Hosahalli") ? displayName.split(" ")[0] : displayName;

  if (loading && !weather) {
    return (
      <div className="card weather-widget">
        <div className="card-title"><Skeleton className="sk-line" style={{ width: "75%" }} /></div>
        <div className="weather-stats">
          <div className="weather-temp">
            <Skeleton className="sk-line sk-temp" style={{ width: "70%", margin: "0 auto 8px" }} />
            <Skeleton className="sk-line" style={{ width: "55%", margin: "0 auto" }} />
          </div>
          <div className="weather-metric"><Skeleton className="sk-line" style={{ width: "85%" }} /></div>
          <div className="weather-metric"><Skeleton className="sk-line" style={{ width: "85%" }} /></div>
          <div className="weather-metric"><Skeleton className="sk-line" style={{ width: "85%" }} /></div>
        </div>
        <Skeleton className="sk-line" style={{ width: "60%" }} />
        <Skeleton className="sk-line" style={{ width: "42%", marginTop: 8 }} />
      </div>
    );
  }

  return (
    <div className="card weather-widget fade-in-delay">
      <div className="card-title">🌤 Weather &amp; Disease Risk — {locationLabel}</div>
      <ErrorBox message={error} />
      {weather && (
        <>
          <div className="weather-stats">
            <div className="weather-temp">
              <div className="weather-temp-value">{Math.round(weather.temperature)}°C</div>
              <div className="weather-temp-label">Temperature</div>
            </div>
            <div className="weather-metric">
              <span className="weather-icon">💧</span>
              <div>
                <div className="weather-metric-value">{Math.round(weather.humidity)}%</div>
                <div className="weather-metric-label">Humidity</div>
              </div>
            </div>
            <div className="weather-metric">
              <span className="weather-icon">🌧</span>
              <div>
                <div className="weather-metric-value">{weather.rainfall}mm</div>
                <div className="weather-metric-label">Rainfall</div>
              </div>
            </div>
            <div className="weather-metric">
              <span className="weather-icon">💨</span>
              <div>
                <div className="weather-metric-value">{Math.round(weather.windspeed)} km/h</div>
                <div className="weather-metric-label">Wind</div>
              </div>
            </div>
          </div>
          <div className={`weather-risk-banner risk-${(weather.disease_risk || "LOW").toLowerCase()}`}>
            <DiseaseRiskBadge risk={weather.disease_risk} compact />
            <span className="weather-risk-text">Disease risk level for your crop</span>
          </div>
          <p className="weather-tip">High humidity increases fungal disease risk</p>
          <p className="weather-updated">
            Last updated: {weather.updated_at ? new Date(weather.updated_at).toLocaleString() : "—"}
          </p>
        </>
      )}
    </div>
  );
}

function timeAgo(ts) {
  if (!ts) return "";
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return new Date(ts).toLocaleDateString();
}

function alertStripClass(cls) {
  if (cls === "diseased") return "strip-diseased";
  if (cls === "pest_affected") return "strip-pest";
  if (cls === "water_stressed") return "strip-water";
  return "strip-default";
}

async function markAlertRead(id) {
  try {
    await api(`/api/alerts/${id}/read`, { method: "PUT" });
  } catch {
    await api(`/api/alerts/${id}/read`, { method: "POST" });
  }
}

function ImageModal({ alert, farm, onClose }) {
  const [src, setSrc] = useState(null);

  useEffect(() => {
    let objectUrl = null;
    let cancelled = false;
    const token = getToken();
    fetch(`${API_BASE}/api/alerts/${alert.id}/image`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (blob && !cancelled) {
          objectUrl = URL.createObjectURL(blob);
          setSrc(objectUrl);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [alert.id]);

  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="image-modal-overlay" onClick={onClose}>
      <div className="image-modal-content fade-in" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="image-modal-close" onClick={onClose}>×</button>
        {src ? (
          <img src={src} alt="Flagged detection" className="image-modal-img" />
        ) : (
          <div className="image-modal-loading"><Spinner label="Loading image…" /></div>
        )}
        <div className="image-modal-info">
          <div><strong>{farm?.name || `Farm #${alert.farm_id}`}</strong> · {formatCrop(farm?.crop_type)}</div>
          <div style={{ marginTop: 8 }}>
            <ClassBadge cls={alert.class_name} />{" "}
            <strong>{alert.confidence.toFixed(1)}%</strong> confidence
          </div>
          <div style={{ marginTop: 6, color: "var(--muted)", fontSize: "0.88rem" }}>
            {new Date(alert.timestamp).toLocaleString()} ({timeAgo(alert.timestamp)})
          </div>
        </div>
      </div>
    </div>
  );
}

const ALERT_FILTERS = [
  { id: "all", label: "All" },
  { id: "unread", label: "Unread" },
  { id: "diseased", label: "Diseased" },
  { id: "pest", label: "Pest" },
  { id: "water_stressed", label: "Water Stressed" },
];

function AlertStatsPanel({ stats, loading }) {
  if (loading) return <Spinner label="Loading alert stats…" />;
  const counts = stats?.class_counts || {};
  return (
    <div className="alert-mini-stats">
      <div className="alert-mini-stat stat-diseased">
        <div className="mini-label">Diseased today</div>
        <div className="mini-value">{counts.diseased || 0}</div>
      </div>
      <div className="alert-mini-stat stat-pest">
        <div className="mini-label">Pest today</div>
        <div className="mini-value">{counts.pest_affected || 0}</div>
      </div>
      <div className="alert-mini-stat stat-water">
        <div className="mini-label">Water stress today</div>
        <div className="mini-value">{counts.water_stressed || 0}</div>
      </div>
      <div className="alert-mini-stat stat-week">
        <div className="mini-label">Total this week</div>
        <div className="mini-value">{stats?.total_week ?? 0}</div>
      </div>
    </div>
  );
}

function AlertsPage({ farms, onMarkRead, onMarkAllRead, onRefresh }) {
  const [filter, setFilter] = useState("all");
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalAlert, setModalAlert] = useState(null);
  const [markingAll, setMarkingAll] = useState(false);

  const farmMap = Object.fromEntries(farms.map((f) => [f.id, f]));
  const unreadCount = alerts.filter((a) => !a.is_read).length;

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [list, statsData] = await Promise.all([
        api(`/api/alerts/?filter=${filter}`),
        api("/api/alerts/stats").catch(() => null),
      ]);
      setAlerts(list);
      setStats(statsData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { loadAlerts(); }, [loadAlerts]);

  async function handleMarkRead(id) {
    try {
      await markAlertRead(id);
      await loadAlerts();
      if (onMarkRead) onMarkRead();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleMarkAllRead() {
    setMarkingAll(true);
    setError("");
    try {
      try {
        await api("/api/alerts/mark-all-read", { method: "PUT" });
      } catch {
        await api("/api/alerts/mark-all-read", { method: "POST" });
      }
      await loadAlerts();
      if (onMarkAllRead) onMarkAllRead();
    } catch (err) {
      setError(err.message);
    } finally {
      setMarkingAll(false);
    }
  }

  const displayCount = filter === "unread" ? unreadCount : alerts.length;

  return (
    <div className="alerts-page fade-in">
      <div className="alerts-page-header">
        <div>
          <h2>Alerts &amp; Notifications</h2>
          <p>Monitor plantation health warnings across your farms</p>
        </div>
        <div className="alerts-header-actions">
          <span className="alerts-count-badge">{displayCount} alert{displayCount !== 1 ? "s" : ""}</span>
          <button
            className="btn btn-outline btn-sm"
            onClick={handleMarkAllRead}
            disabled={markingAll || !alerts.some((a) => !a.is_read)}
          >
            {markingAll ? "Marking…" : "Mark all read"}
          </button>
        </div>
      </div>

      <AlertStatsPanel stats={stats} loading={loading && !stats} />
      <ErrorBox message={error} />

      <div className="alert-filters">
        {ALERT_FILTERS.map((f) => (
          <button
            key={f.id}
            className={`filter-btn ${filter === f.id ? "active" : ""}`}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <Spinner label="Loading alerts…" />
      ) : alerts.length === 0 ? (
        <div className="card alerts-empty">
          <div className="icon">✅</div>
          <h3>No alerts found</h3>
          <p>{filter === "all" ? "Your plantations look healthy!" : `No ${filter.replace("_", " ")} alerts.`}</p>
        </div>
      ) : (
        <div className="alerts-list">
          {alerts.map((a) => {
            const farm = farmMap[a.farm_id];
            return (
              <div className={`alert-card ${!a.is_read ? "unread" : ""}`} key={a.id}>
                <div className={`alert-strip ${alertStripClass(a.class_name)}`} />
                <div className="alert-card-body">
                  <div className="alert-card-top">
                    <div>
                      <div className="alert-farm-name">{farm?.name || `Farm #${a.farm_id}`}</div>
                      <div className="alert-crop">{formatCrop(farm?.crop_type)}</div>
                    </div>
                    <div className="alert-card-meta">
                      <ClassBadge cls={a.class_name} />
                      <div className="alert-confidence">{a.confidence.toFixed(1)}%</div>
                      <div className="alert-time">{timeAgo(a.timestamp)}</div>
                    </div>
                  </div>
                  <div className="alert-card-bottom">
                    <button type="button" className="alert-thumb-btn" onClick={() => setModalAlert(a)}>
                      <AlertThumb alertId={a.id} />
                    </button>
                    <div className="alert-card-btns">
                      <button className="btn btn-sm btn-outline" onClick={() => setModalAlert(a)}>View Image</button>
                      {!a.is_read && (
                        <button className="btn btn-sm btn-primary" onClick={() => handleMarkRead(a.id)}>Mark Read</button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {modalAlert && (
        <ImageModal
          alert={modalAlert}
          farm={farmMap[modalAlert.farm_id]}
          onClose={() => setModalAlert(null)}
        />
      )}
    </div>
  );
}

function NotificationBell({ unreadCount, farms, onViewAll, onRefresh }) {
  const [open, setOpen] = useState(false);
  const [dropdownAlerts, setDropdownAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);

  const farmMap = Object.fromEntries(farms.map((f) => [f.id, f]));

  const loadDropdown = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api("/api/alerts/?filter=unread");
      setDropdownAlerts(list.slice(0, 5));
    } catch {
      setDropdownAlerts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) loadDropdown();
  }, [open, loadDropdown, unreadCount]);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  return (
    <div className="notif-bell-wrap" ref={ref}>
      <button
        className="nav-icon-btn"
        title="Notifications"
        onClick={() => setOpen(!open)}
      >
        🔔
        {unreadCount > 0 && <span className="badge-count">{unreadCount > 99 ? "99+" : unreadCount}</span>}
      </button>
      {open && (
        <div className="notif-dropdown fade-in">
          <div className="notif-dropdown-header">
            <strong>Notifications</strong>
            {unreadCount > 0 && <span className="notif-dropdown-count">{unreadCount} unread</span>}
          </div>
          {loading ? (
            <div className="notif-dropdown-loading">Loading…</div>
          ) : dropdownAlerts.length === 0 ? (
            <div className="notif-dropdown-empty">No unread alerts</div>
          ) : (
            <ul className="notif-dropdown-list">
              {dropdownAlerts.map((a) => (
                <li key={a.id} className="notif-dropdown-item">
                  <div className={`notif-dot ${alertStripClass(a.class_name)}`} />
                  <div>
                    <div className="notif-item-title">{farmMap[a.farm_id]?.name || `Farm #${a.farm_id}`}</div>
                    <div className="notif-item-sub">
                      <ClassBadge cls={a.class_name} /> {a.confidence.toFixed(0)}% · {timeAgo(a.timestamp)}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <button
            className="notif-view-all"
            onClick={() => { setOpen(false); onViewAll(); if (onRefresh) onRefresh(); }}
          >
            View all alerts →
          </button>
        </div>
      )}
    </div>
  );
}

function AlertsTable({ alerts, farms, onMarkRead, loading, error }) {
  const farmMap = Object.fromEntries((farms || []).map((f) => [f.id, f.name]));

  if (loading) return <CardSkeleton titleWidth="52%" lines={6} />;

  return (
    <div className="card fade-in-delay">
      <div className="card-title">🚨 Recent Alerts</div>
      <ErrorBox message={error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Farm</th>
              <th>Class</th>
              <th>Confidence</th>
              <th>Image</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {alerts.length === 0 ? (
              <tr><td colSpan="6" style={{ textAlign: "center", color: "var(--muted)" }}>No alerts — your plantation looks good!</td></tr>
            ) : alerts.slice(0, 10).map((a) => (
              <tr key={a.id} style={{ opacity: a.is_read ? 0.65 : 1 }}>
                <td>{new Date(a.timestamp).toLocaleString()}</td>
                <td>{farmMap[a.farm_id] || `Farm #${a.farm_id}`}</td>
                <td><ClassBadge cls={a.class_name} /></td>
                <td><strong>{a.confidence.toFixed(1)}%</strong></td>
                <td><AlertThumb alertId={a.id} /></td>
                <td>
                  {!a.is_read ? (
                    <button className="btn btn-sm btn-outline" onClick={() => onMarkRead(a.id)}>Mark read</button>
                  ) : (
                    <span style={{ color: "var(--muted)", fontSize: "0.82rem" }}>Read</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const MAX_FILE_BYTES = 10 * 1024 * 1024;

const CLASS_DISPLAY = {
  healthy: { label: "HEALTHY", css: "analysis-healthy", bar: "var(--secondary)" },
  diseased: { label: "DISEASED", css: "analysis-diseased", bar: "var(--danger)" },
  pest_affected: { label: "PEST AFFECTED", css: "analysis-pest", bar: "var(--warning)" },
  water_stressed: { label: "WATER STRESSED", css: "analysis-water", bar: "var(--water)" },
};

const ANALYSIS_ADVICE = {
  healthy: "Your plant looks healthy! Monitor regularly.",
  diseased: "Disease detected! Recommended: Apply fungicide within 48 hours. Contact your agronomist.",
  pest_affected: "Pest damage detected! Recommended: Apply pesticide. Check surrounding plants.",
  water_stressed: "Water stress detected! Recommended: Water this plant immediately. Check irrigation.",
};

function validateImageFile(f) {
  if (!f) return "No file selected";
  if (!["image/jpeg", "image/jpg", "image/png"].includes(f.type)) {
    return "Only JPG, PNG, and JPEG images are accepted";
  }
  if (f.size > MAX_FILE_BYTES) return "Image must be 10MB or smaller";
  return null;
}

function AnalysisHistoryCard({ detection }) {
  return (
    <div className="history-card">
      <DetectionThumb detectionId={detection.id} />
      <div className="history-card-body">
        <ClassBadge cls={detection.predicted_class} />
        <div className="history-conf">{detection.confidence.toFixed(1)}%</div>
        <div className="history-time">{new Date(detection.timestamp).toLocaleString()}</div>
      </div>
    </div>
  );
}

function AnalysisPage({ farms, farmId, onFarmChange, onAnalyzed }) {
  const { pushToast } = useToast();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);
  const [pendingResult, setPendingResult] = useState(null);
  const [revealSeconds, setRevealSeconds] = useState(0);
  const [saved, setSaved] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const inputRef = useRef(null);
  const lastToastRef = useRef("");

  const selectedFarm = farms.find((f) => String(f.id) === String(farmId));

  const loadHistory = useCallback(async () => {
    if (!farmId) return;
    setHistoryLoading(true);
    try {
      const dets = await api(`/api/detections/farm/${farmId}`);
      setHistory(dets.slice(0, 5));
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, [farmId]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  function pickFile(f) {
    const err = validateImageFile(f);
    if (err) {
      setError(err);
      return;
    }
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setSaved(false);
    setSaveMessage("");
    setError("");
  }

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) pickFile(f);
  }

  function resetForm() {
    setFile(null);
    setPreview(null);
    setResult(null);
    setSaved(false);
    setSaveMessage("");
    setError("");
    if (inputRef.current) inputRef.current.value = "";
  }

  async function analyse() {
    if (!file) {
      setError("Upload a photo first");
      return;
    }
    if (!farmId) {
      setError("Select a farm first");
      return;
    }
    setAnalyzing(true);
    setError("");
    setResult(null);
    setSaved(false);
    setSaveMessage("");
    const fd = new FormData();
    fd.append("file", file);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/detections/analyze`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Analysis failed");
      setPendingResult(data);
      setRevealSeconds(3);
    } catch (err) {
      setError(err.message);
    } finally {
      setAnalyzing(false);
    }
  }

  useEffect(() => {
    if (!pendingResult || revealSeconds <= 0) return;
    const t = window.setInterval(() => {
      setRevealSeconds((s) => s - 1);
    }, 1000);
    return () => window.clearInterval(t);
  }, [pendingResult, revealSeconds]);

  useEffect(() => {
    if (!pendingResult || revealSeconds > 0) return;
    setResult(pendingResult);
    setPendingResult(null);
  }, [pendingResult, revealSeconds]);

  async function saveToFarm() {
    if (!file || !result || !farmId) return;
    const cls = result.prediction?.class || result.prediction?.predicted_class;
    const conf = result.prediction?.confidence;
    setSaving(true);
    setError("");
    const fd = new FormData();
    fd.append("farm_id", farmId);
    fd.append("predicted_class", cls);
    fd.append("confidence", String(conf));
    fd.append("file", file);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/detections/save`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      setSaved(true);
      setSaveMessage(data.alert_created
        ? "Saved — alert logged to your dashboard!"
        : "Saved to farm successfully!");
      loadHistory();
      if (onAnalyzed) onAnalyzed();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const cls = result?.prediction?.class || result?.prediction?.predicted_class;
  const conf = result?.prediction?.confidence ?? 0;
  const display = CLASS_DISPLAY[cls] || CLASS_DISPLAY.healthy;

  useEffect(() => {
    if (!result || analyzing) return;
    const key = `${cls || "unknown"}_${Number(conf || 0).toFixed(3)}_${result.analyzed_at || ""}`;
    if (lastToastRef.current === key) return;
    lastToastRef.current = key;

    if (cls === "healthy") {
      pushToast({ type: "success", message: "Analysis complete — Healthy plant detected" });
    } else if (cls === "diseased") {
      pushToast({ type: "danger", message: "ALERT — Diseased plant detected at Hosahalli Block A" });
    }
  }, [result, analyzing, cls, conf, pushToast]);

  async function copyShareText() {
    const shareText = `${display.label} detected at ${Number(conf || 0).toFixed(1)}% confidence — CropGuard AI`;
    try {
      await navigator.clipboard.writeText(shareText);
      pushToast({ type: "success", message: "Copied to clipboard" });
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = shareText;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        pushToast({ type: "success", message: "Copied to clipboard" });
      } catch {
        pushToast({ type: "danger", message: "Could not copy (browser blocked clipboard)" });
      }
    }
  }

  return (
    <div className="analysis-page fade-in">
      <div className="analysis-header">
        <div>
          <h2>Plant Health Analysis</h2>
          <p>AI-powered disease, pest, and water stress detection</p>
        </div>
        <div className="analysis-farm-select">
          <label>Analysing for:</label>
          <select value={farmId} onChange={(e) => onFarmChange(e.target.value)} disabled={!farms.length}>
            {farms.length === 0 && <option value="">No farms — add one first</option>}
            {farms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </div>
      </div>

      <ErrorBox message={error} />

      {!farms.length && (
        <div className="card" style={{ marginBottom: 20, color: "var(--muted)" }}>
          Create a farm under <strong>My Farms</strong> before running analysis.
        </div>
      )}

      <div className="card analysis-upload-card">
        <div
          className={`analysis-dropzone ${dragOver ? "drag-over" : ""} ${preview ? "has-preview" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => !preview && inputRef.current?.click()}
        >
          {analyzing ? (
            <div className="analysis-loading">
              <div className="leaf-spinner">🌿</div>
              <p>Analysing your plant…</p>
            </div>
          ) : preview ? (
            <div className="analysis-preview-in-box" onClick={(e) => e.stopPropagation()}>
              <img src={preview} alt="Selected plant" />
              <button type="button" className="btn btn-sm btn-outline change-photo" onClick={() => inputRef.current?.click()}>
                Change photo
              </button>
            </div>
          ) : (
            <>
              <div className="analysis-leaf-icon">🍃</div>
              <p className="analysis-upload-title">Click to upload or drag a photo here</p>
              <p className="analysis-upload-hint">Accepted: JPG, PNG, JPEG · Max size: 10MB</p>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/jpg"
            style={{ display: "none" }}
            onChange={(e) => pickFile(e.target.files[0])}
          />
        </div>

        {!analyzing && (
          <button
            className="btn btn-primary btn-analyse-photo"
            onClick={analyse}
            disabled={!file || !farmId || analyzing}
          >
            Analyse This Photo
          </button>
        )}
      </div>

      {pendingResult && !analyzing && revealSeconds > 0 && (
        <div className="analysis-result-panel fade-in">
          <div className="card suspense-card">
            <div className="card-title">⏳ Preparing your result…</div>
            <div className="suspense-count">
              Revealing in <strong>{revealSeconds}</strong>s
            </div>
            <div className="suspense-bar">
              <div className="suspense-bar-fill" style={{ width: `${((3 - revealSeconds) / 3) * 100}%` }} />
            </div>
            <div style={{ marginTop: 16 }}>
              <Skeleton className="sk-line" style={{ width: "85%" }} />
              <Skeleton className="sk-line" style={{ width: "70%", marginTop: 10 }} />
              <Skeleton className="sk-line" style={{ width: "65%", marginTop: 10 }} />
            </div>
          </div>
        </div>
      )}

      {result && !analyzing && (
        <div className="analysis-result-panel fade-in">
          <div className="analysis-result-grid">
            <div className="analysis-result-image">
              <img src={preview} alt="Analysed plant" />
            </div>

            <div className={`analysis-result-card ${display.css}`}>
              <div className="giant-label">{display.label}</div>
              <div className="giant-confidence">{conf.toFixed(1)}%</div>
              <div className="confidence-bar-track">
                <div className="confidence-bar-fill" style={{ width: `${Math.min(conf, 100)}%`, background: display.bar }} />
              </div>
              <div className="analysis-timestamp">
                {result.analyzed_at
                  ? new Date(result.analyzed_at).toLocaleString()
                  : new Date().toLocaleString()}
              </div>
            </div>

            <div className="analysis-action-panel card">
              <h4>Recommendation</h4>
              <p>{ANALYSIS_ADVICE[cls] || ANALYSIS_ADVICE.healthy}</p>
              {selectedFarm && (
                <p className="analysis-farm-note">Farm: <strong>{selectedFarm.name}</strong></p>
              )}
              {saveMessage && <p className="analysis-save-msg">{saveMessage}</p>}
              <div className="analysis-action-btns">
                <button
                  className="btn btn-primary"
                  onClick={saveToFarm}
                  disabled={saving || saved || !farmId}
                >
                  {saved ? "Saved ✓" : saving ? "Saving…" : "Save to Farm"}
                </button>
                <button className="btn btn-outline" type="button" onClick={copyShareText}>
                  Share Result
                </button>
                <button className="btn btn-outline" onClick={resetForm}>Analyse Another</button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="analysis-history-section">
        <h3>Recent Analyses</h3>
        {historyLoading ? (
          <Spinner label="Loading history…" />
        ) : history.length === 0 ? (
          <p className="analysis-history-empty">No analyses yet for this farm.</p>
        ) : (
          <div className="analysis-history-grid">
            {history.map((d) => <AnalysisHistoryCard key={d.id} detection={d} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function QuickAnalysis({ farmId, farms, onAnalyzed }) {
  const { pushToast } = useToast();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const lastToastRef = useRef("");

  function pickFile(f) {
    const err = validateImageFile(f);
    if (err) { setError(err); return; }
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setError("");
  }

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) pickFile(f);
  }

  async function analyse() {
    if (!file || !farmId) {
      setError("Select a farm and upload an image first");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    const token = getToken();
    const analyzeFd = new FormData();
    analyzeFd.append("file", file);
    try {
      const analyzeRes = await fetch(`${API_BASE}/api/detections/analyze`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: analyzeFd,
      });
      const preview = await analyzeRes.json();
      if (!analyzeRes.ok) throw new Error(preview.detail || "Analysis failed");

      const pred = preview.prediction || {};
      const cls = pred.class || pred.predicted_class;
      const saveClass = pred.actual_class || cls;
      const conf = pred.confidence;
      const saveFd = new FormData();
      saveFd.append("farm_id", farmId);
      saveFd.append("predicted_class", saveClass);
      saveFd.append("confidence", String(conf));
      saveFd.append("file", file);

      const saveRes = await fetch(`${API_BASE}/api/detections/save`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: saveFd,
      });
      const data = await saveRes.json();
      if (!saveRes.ok) throw new Error(data.detail || "Save failed");
      setResult({
        ...data,
        prediction: {
          ...(data.prediction || {}),
          class: cls,
          actual_class: saveClass,
          confidence: conf,
          message: pred.message || data.prediction?.message,
        },
      });
      if (onAnalyzed) onAnalyzed();

      const key = `${saveClass || "unknown"}_${Number(conf ?? 0).toFixed(3)}_${data.detection?.id || ""}`;
      if (lastToastRef.current !== key) {
        lastToastRef.current = key;
        if (cls !== "uncertain" && Number(conf ?? 0) >= 75 && saveClass === "healthy") {
          pushToast({ type: "success", message: "Analysis complete — Healthy plant detected" });
        } else if (cls !== "uncertain" && Number(conf ?? 0) >= 75 && saveClass === "diseased") {
          pushToast({ type: "danger", message: "ALERT — Diseased plant detected at Hosahalli Block A" });
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const pred = result?.prediction || {};
  const cls = pred.class || result?.detection?.predicted_class;
  const actualClass = pred.actual_class || cls;
  const conf = pred.confidence ?? result?.detection?.confidence;
  const isUncertain = cls === "uncertain" || (conf != null && conf < 75);
  let resultClass = "result-healthy";
  if (isUncertain) resultClass = "result-uncertain";
  else if (actualClass === "water_stressed") resultClass = "result-water";
  else if (actualClass === "pest_affected") resultClass = "result-pest";
  else if (actualClass && actualClass !== "healthy") resultClass = "result-problem";

  return (
    <div className="card fade-in-delay">
      <div className="card-title">🔬 Quick Analysis</div>
      <ErrorBox message={error} />

      {!farms?.length && (
        <p style={{ color: "var(--muted)", marginBottom: 12 }}>Create a farm first to run analysis.</p>
      )}

      <div
        className={`dropzone ${dragOver ? "drag-over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
      >
        <div className="dz-icon">📤</div>
        <p><strong>Drag & drop</strong> a plant photo here, or click to browse</p>
        <p style={{ marginTop: 6, fontSize: "0.82rem" }}>JPG, PNG — chrysanthemum leaf or plant images</p>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/jpg"
          style={{ display: "none" }}
          onChange={(e) => pickFile(e.target.files[0])}
        />
      </div>

      {preview && (
        <div style={{ marginTop: 16, textAlign: "center" }}>
          <img src={preview} alt="Preview" style={{ maxHeight: 160, borderRadius: 10, border: "1px solid var(--border)" }} />
          <p style={{ fontSize: "0.82rem", color: "var(--muted)", marginTop: 6 }}>{file?.name}</p>
        </div>
      )}

      <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
        <button className="btn btn-primary" style={{ width: "auto", flex: 1 }} onClick={analyse} disabled={loading || !file || !farmId}>
          {loading ? "Analysing…" : "Analyse Now"}
        </button>
      </div>

      {result && (
        <div className={`result-panel ${resultClass}`}>
          {isUncertain ? (
            <>
              <p className="result-uncertain-title">Uncertain — Take a closer photo of the leaf for better accuracy</p>
              {pred.message && (
                <div style={{ fontSize: "0.9rem", color: "var(--muted)", marginBottom: 8 }}>{pred.message}</div>
              )}
              <div className="big-label">
                <ClassBadge cls={actualClass} /> Model guess: {actualClass?.replace(/_/g, " ")}
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: "0.9rem", color: "var(--muted)" }}>{result.message}</div>
              <div className="big-label"><ClassBadge cls={actualClass} /> {actualClass?.replace(/_/g, " ")}</div>
            </>
          )}
          <div className="conf">Confidence: <strong>{conf?.toFixed(1)}%</strong></div>
          {result.alert_created && !isUncertain && (
            <p style={{ marginTop: 12, color: "var(--danger)", fontWeight: 700 }}>⚠ Alert logged to your dashboard</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Farms pages ───────────────────────────────────────────────────────────────
function AddFarmModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [cropType, setCropType] = useState("chrysanthemum");
  const [city, setCity] = useState("");
  const [state, setState] = useState("Karnataka");
  const [area, setArea] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api("/api/farms/", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          crop_type: cropType,
          location: `${city.trim()}, ${state}`,
          area_acres: parseFloat(area) || 0,
          description: description.trim(),
        }),
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add New Farm</h3>
          <button type="button" className="modal-close" onClick={onClose}>×</button>
        </div>
        <ErrorBox message={error} />
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Farm Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Hosahalli Block C" required />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Crop Type</label>
              <select value={cropType} onChange={(e) => setCropType(e.target.value)}>
                {CROP_OPTIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>Area (acres)</label>
              <input type="number" min="0" step="0.1" value={area} onChange={(e) => setArea(e.target.value)} placeholder="2.5" required />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>City</label>
              <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Hosahalli" required />
            </div>
            <div className="form-group">
              <label>State</label>
              <select value={state} onChange={(e) => setState(e.target.value)}>
                {INDIAN_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          <div className="form-group">
            <label>Description <span className="optional">(optional)</span></label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} placeholder="Notes about soil, irrigation, or crop variety…" />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? "Creating…" : "Create Farm"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function FarmsPage({ farms, farmStats, loading, onRefresh, onViewDetails, onAnalyse }) {
  const [showModal, setShowModal] = useState(false);
  const [farmWeather, setFarmWeather] = useState({});

  useEffect(() => {
    if (!farms.length) return;
    Promise.all(
      farms.map(async (f) => {
        try {
          const w = await api(`/api/farms/${f.id}/weather`);
          return [f.id, w];
        } catch {
          return [f.id, null];
        }
      })
    ).then((results) => setFarmWeather(Object.fromEntries(results)));
  }, [farms]);

  if (loading && !farms.length) return <Spinner label="Loading farms…" />;

  return (
    <div className="fade-in">
      <div className="page-header page-header-row">
        <div>
          <h2>My Farms</h2>
          <p>Manage your plantation locations across India</p>
        </div>
        <button className="btn btn-primary btn-add-farm" onClick={() => setShowModal(true)}>
          + Add New Farm
        </button>
      </div>

      {farms.length === 0 ? (
        <div className="card empty-farms">
          <div className="icon">🏡</div>
          <h3>No farms yet</h3>
          <p>Register your first plantation to start AI monitoring.</p>
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>Add New Farm</button>
        </div>
      ) : (
        <div className="farm-grid">
          {farms.map((farm) => {
            const stats = farmStats[farm.id] || {};
            const score = stats.health_score ?? 100;
            return (
              <div className="farm-card fade-in-delay" key={farm.id}>
                <div className="farm-card-top">
                  <h3>{farm.name}</h3>
                  <span className="crop-badge">{formatCrop(farm.crop_type)}</span>
                </div>
                <p className="farm-location">📍 {farm.location}</p>
                <p className="farm-area">{farm.area_acres} acres</p>
                <HealthScoreBadge score={score} />
                {farmWeather[farm.id]?.disease_risk && (
                  <DiseaseRiskBadge risk={farmWeather[farm.id].disease_risk} />
                )}
                <p className="farm-scanned">Last scanned: {formatTimestamp(stats.last_scan)}</p>
                <div className="farm-card-actions">
                  <button className="btn btn-outline" onClick={() => onViewDetails(farm.id)}>View Details</button>
                  <button className="btn btn-primary" onClick={() => onAnalyse(farm.id)}>Analyse</button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showModal && (
        <AddFarmModal
          onClose={() => setShowModal(false)}
          onCreated={onRefresh}
        />
      )}
    </div>
  );
}

function FarmDetailPage({ farmId, onBack, onAnalyse, onRefresh }) {
  const [farm, setFarm] = useState(null);
  const [stats, setStats] = useState(null);
  const [detections, setDetections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [farmData, statsData, dets] = await Promise.all([
        api(`/api/farms/${farmId}`),
        api(`/api/farms/${farmId}/stats`).catch(() => safeApiFallbackStats(farmId)),
        api(`/api/detections/farm/${farmId}`),
      ]);
      setFarm(farmData);
      setStats(statsData);
      setDetections(dets);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [farmId]);

  async function safeApiFallbackStats(fid) {
    const dets = await api(`/api/detections/farm/${fid}`);
    const class_counts = {};
    let problems = 0;
    dets.forEach((d) => {
      class_counts[d.predicted_class] = (class_counts[d.predicted_class] || 0) + 1;
      if (d.predicted_class !== "healthy") problems += 1;
    });
    const total = dets.length;
    const healthy = class_counts.healthy || 0;
    return {
      farm_id: fid,
      total_detections: total,
      problems_found: problems,
      last_scan: dets[0]?.timestamp || null,
      health_score: total ? Math.round((healthy / total) * 100) : 100,
      class_counts,
    };
  }

  useEffect(() => { load(); }, [load]);

  if (loading && !farm) return <Spinner label="Loading farm details…" />;

  if (!farm) {
    return (
      <div className="fade-in">
        <ErrorBox message={error || "Farm not found"} />
        <button className="btn btn-outline back-btn" onClick={onBack}>← Back to My Farms</button>
      </div>
    );
  }

  return (
    <div className="fade-in">
      <button className="btn btn-outline back-btn" onClick={onBack}>← Back to My Farms</button>
      <ErrorBox message={error} />

      <div className="farm-detail-header card">
        <div>
          <h2>{farm.name}</h2>
          <div className="farm-detail-meta">
            <span className="crop-badge">{formatCrop(farm.crop_type)}</span>
            <span>📍 {farm.location}</span>
            <span>{farm.area_acres} acres</span>
            <span>Created {new Date(farm.created_at).toLocaleDateString()}</span>
          </div>
          {farm.description && <p className="farm-description">{farm.description}</p>}
        </div>
        <button className="btn btn-primary" onClick={() => onAnalyse(farm.id)}>Analyse New Photo</button>
      </div>

      <div className="stats-row farm-detail-stats">
        <div className="stat-card stat-blue">
          <div className="stat-icon">📷</div>
          <h4>Total Detections</h4>
          <div className="stat-value">{stats?.total_detections ?? 0}</div>
        </div>
        <div className="stat-card stat-red">
          <div className="stat-icon">⚠️</div>
          <h4>Problems Found</h4>
          <div className="stat-value">{stats?.problems_found ?? 0}</div>
        </div>
        <div className="stat-card stat-gold">
          <div className="stat-icon">🕐</div>
          <h4>Last Scan</h4>
          <div className="stat-value stat-value-sm">{stats?.last_scan ? new Date(stats.last_scan).toLocaleDateString() : "—"}</div>
        </div>
        <div className="stat-card stat-green">
          <div className="stat-icon">💚</div>
          <h4>Health Score</h4>
          <div className="stat-value">{Math.round(stats?.health_score ?? 100)}%</div>
        </div>
      </div>

      <div className="card fade-in-delay">
        <div className="card-title">Detection History</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Predicted Class</th>
                <th>Confidence</th>
                <th>Image</th>
              </tr>
            </thead>
            <tbody>
              {detections.length === 0 ? (
                <tr><td colSpan="4" style={{ textAlign: "center", color: "var(--muted)" }}>No scans yet — analyse your first photo.</td></tr>
              ) : detections.map((d) => (
                <tr key={d.id}>
                  <td>{new Date(d.timestamp).toLocaleString()}</td>
                  <td><ClassBadge cls={d.predicted_class} /></td>
                  <td><strong>{d.confidence.toFixed(1)}%</strong></td>
                  <td><DetectionThumb detectionId={d.id} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function HealthStatusBadge({ status }) {
  const map = {
    healthy: { label: "Healthy", cls: "status-healthy" },
    warning: { label: "Warning", cls: "status-warning" },
    critical: { label: "Critical", cls: "status-critical" },
  };
  const s = map[status] || map.healthy;
  return <span className={`status-badge ${s.cls}`}>{s.label}</span>;
}

function formatClassLabel(cls) {
  return (cls || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function AdminTrendsChart({ trends }) {
  if (!trends?.length) {
    return <p style={{ color: "var(--muted)" }}>No detection data for the past 7 days.</p>;
  }
  const maxTotal = Math.max(...trends.map((d) => d.total), 1);

  return (
    <div className="admin-trends-chart">
      {trends.map((day) => {
        const h = (day.healthy / maxTotal) * 100;
        const di = (day.diseased / maxTotal) * 100;
        const p = (day.pest_affected / maxTotal) * 100;
        const w = (day.water_stressed / maxTotal) * 100;
        const label = new Date(day.date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
        return (
          <div className="trend-day" key={day.date}>
            <div className="trend-bar-stack" title={`${day.total} detections`}>
              {day.water_stressed > 0 && <div className="trend-seg seg-water" style={{ height: `${w}%` }} />}
              {day.pest_affected > 0 && <div className="trend-seg seg-pest" style={{ height: `${p}%` }} />}
              {day.diseased > 0 && <div className="trend-seg seg-diseased" style={{ height: `${di}%` }} />}
              {day.healthy > 0 && <div className="trend-seg seg-healthy" style={{ height: `${h}%` }} />}
              {day.total === 0 && <div className="trend-seg seg-empty" style={{ height: "4%" }} />}
            </div>
            <div className="trend-day-label">{label}</div>
            <div className="trend-day-count">{day.total}</div>
          </div>
        );
      })}
      <div className="trend-legend">
        <span><i className="leg leg-healthy" /> Healthy</span>
        <span><i className="leg leg-diseased" /> Diseased</span>
        <span><i className="leg leg-pest" /> Pest</span>
        <span><i className="leg leg-water" /> Water</span>
      </div>
    </div>
  );
}

function AdminPage() {
  const [stats, setStats] = useState(null);
  const [allFarms, setAllFarms] = useState([]);
  const [allUsers, setAllUsers] = useState([]);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [farmSearch, setFarmSearch] = useState("");
  const [roleChanging, setRoleChanging] = useState(null);

  const loadAdmin = useCallback(async () => {
    try {
      const [statsData, farmsData, usersData, feedData] = await Promise.all([
        api("/api/admin/stats"),
        api("/api/admin/all-farms"),
        api("/api/admin/all-users"),
        api("/api/admin/activity-feed"),
      ]);
      setStats(statsData);
      setAllFarms(farmsData);
      setAllUsers(usersData);
      setActivity(feedData);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadActivity = useCallback(async () => {
    try {
      const feedData = await api("/api/admin/activity-feed");
      setActivity(feedData);
    } catch { /* silent refresh */ }
  }, []);

  useEffect(() => {
    setLoading(true);
    loadAdmin();
  }, [loadAdmin]);

  useEffect(() => {
    const interval = setInterval(loadActivity, 30000);
    return () => clearInterval(interval);
  }, [loadActivity]);

  async function handleChangeRole(u) {
    if (u.role === "admin") return;
    const newRole = u.role === "farmer" ? "manager" : "farmer";
    setRoleChanging(u.id);
    setError("");
    try {
      const updated = await api(`/api/admin/users/${u.id}/role`, {
        method: "PUT",
        body: JSON.stringify({ role: newRole }),
      });
      setAllUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (err) {
      setError(err.message);
    } finally {
      setRoleChanging(null);
    }
  }

  const filteredFarms = allFarms.filter((f) => {
    const q = farmSearch.toLowerCase().trim();
    if (!q) return true;
    return f.name.toLowerCase().includes(q) || f.location.toLowerCase().includes(q);
  });

  if (loading && !stats) return <Spinner label="Loading admin dashboard…" />;

  return (
    <div className="admin-page fade-in">
      <div className="admin-header">
        <h2>CropGuard AI — Platform Overview</h2>
        <p>System-wide monitoring and user management</p>
      </div>

      <ErrorBox message={error} />

      <div className="admin-stats-row">
        <div className="admin-stat-card">
          <div className="admin-stat-icon">🏡</div>
          <div className="admin-stat-label">Registered Farms</div>
          <div className="admin-stat-value">{stats?.total_farms ?? 0}</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">👥</div>
          <div className="admin-stat-label">Total Users</div>
          <div className="admin-stat-value">{stats?.total_users ?? 0}</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">📷</div>
          <div className="admin-stat-label">Total Detections</div>
          <div className="admin-stat-value">{stats?.total_detections ?? 0}</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-icon">📅</div>
          <div className="admin-stat-label">Detections Today</div>
          <div className="admin-stat-value">{stats?.detections_today ?? 0}</div>
        </div>
        <div className="admin-stat-card accent-warn">
          <div className="admin-stat-icon">⚠️</div>
          <div className="admin-stat-label">Most Common Problem</div>
          <div className="admin-stat-value admin-stat-text">
            {stats?.most_common_problem ? formatClassLabel(stats.most_common_problem) : "—"}
          </div>
        </div>
        <div className="admin-stat-card accent-green">
          <div className="admin-stat-icon">💚</div>
          <div className="admin-stat-label">Platform Health</div>
          <div className="admin-stat-value">{Math.round(stats?.platform_health_score ?? 100)}%</div>
        </div>
      </div>

      <div className="admin-grid-2">
        <div className="card">
          <div className="card-title">📈 Detection Trends (7 days)</div>
          <AdminTrendsChart trends={stats?.daily_trends} />
          <div className="admin-chart-insights">
            <div>
              <span className="insight-label">Most Active Farm</span>
              <strong>{stats?.most_active_farm || "—"}</strong>
            </div>
            <div>
              <span className="insight-label">Most Common Disease Today</span>
              <strong>{stats?.most_common_disease_today ? formatClassLabel(stats.most_common_disease_today) : "—"}</strong>
            </div>
          </div>
        </div>

        <div className="card admin-activity-card">
          <div className="card-title">⚡ Recent Activity <span className="live-dot" /> Live</div>
          <ul className="activity-feed">
            {activity.length === 0 ? (
              <li className="activity-empty">No recent detections</li>
            ) : activity.map((item) => (
              <li key={item.id} className="activity-item">
                <span className={`activity-dot ${alertStripClass(item.predicted_class)}`} />
                <div>
                  <div className="activity-msg">{item.message}</div>
                  <div className="activity-time">{timeAgo(item.timestamp)}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="card admin-table-card">
        <div className="admin-table-header">
          <div className="card-title">🏡 All Farms</div>
          <input
            className="admin-search"
            placeholder="Search by farm name or location…"
            value={farmSearch}
            onChange={(e) => setFarmSearch(e.target.value)}
          />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Farm Name</th>
                <th>Owner</th>
                <th>Crop</th>
                <th>Location</th>
                <th>Last Scan</th>
                <th>Health Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredFarms.length === 0 ? (
                <tr><td colSpan="7" style={{ textAlign: "center", color: "var(--muted)" }}>No farms found</td></tr>
              ) : filteredFarms.map((f) => (
                <tr key={f.id}>
                  <td><strong>{f.name}</strong></td>
                  <td>{f.owner_name}</td>
                  <td>{formatCrop(f.crop_type)}</td>
                  <td>{f.location}</td>
                  <td>{f.last_scan ? timeAgo(f.last_scan) : "Never"}</td>
                  <td>
                    <HealthStatusBadge status={f.health_status} />
                    <span className="admin-health-pct">{Math.round(f.health_score)}%</span>
                  </td>
                  <td>
                    <button type="button" className="btn btn-sm btn-outline" title={`${f.owner_name} · ${f.owner_email}`}>
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card admin-table-card">
        <div className="card-title">👥 All Users</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Farms</th>
                <th>Joined</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {allUsers.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.name}</strong></td>
                  <td>{u.email}</td>
                  <td><span className={`role-pill role-${u.role}`}>{u.role}</span></td>
                  <td>{u.farms_count}</td>
                  <td>{new Date(u.created_at).toLocaleDateString()}</td>
                  <td><span className="status-badge status-healthy">{u.status}</span></td>
                  <td>
                    {u.role !== "admin" ? (
                      <button
                        className="btn btn-sm btn-outline"
                        disabled={roleChanging === u.id}
                        onClick={() => handleChangeRole(u)}
                      >
                        {roleChanging === u.id ? "…" : `→ ${u.role === "farmer" ? "Manager" : "Farmer"}`}
                      </button>
                    ) : (
                      <span style={{ color: "var(--muted)", fontSize: "0.82rem" }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function toISODate(d) {
  return d.toISOString().slice(0, 10);
}

function weekDateRange() {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 6);
  return { from: toISODate(from), to: toISODate(to) };
}

function monthDateRange() {
  const to = new Date();
  const from = new Date(to.getFullYear(), to.getMonth(), 1);
  return { from: toISODate(from), to: toISODate(to) };
}

const REPORT_CLASSES = [
  { key: "healthy", label: "Healthy", color: "var(--secondary)", card: "breakdown-healthy" },
  { key: "diseased", label: "Diseased", color: "var(--danger)", card: "breakdown-diseased" },
  { key: "pest_affected", label: "Pest", color: "var(--warning)", card: "breakdown-pest" },
  { key: "water_stressed", label: "Water Stressed", color: "var(--water)", card: "breakdown-water" },
];

function buildReportHtml(report) {
  const s = report.summary;
  const rows = report.detections.map((d) => `
    <tr>
      <td>${new Date(d.timestamp).toLocaleString()}</td>
      <td>${formatClassLabel(d.predicted_class)}</td>
      <td>${d.confidence.toFixed(1)}%</td>
      <td>${d.status}</td>
    </tr>`).join("");

  const breakdown = REPORT_CLASSES.map((c) => {
    const count = s.class_counts[c.key] || 0;
    const pct = s.class_percentages[c.key] || 0;
    return `<li><strong>${c.label}:</strong> ${count} (${pct}%)</li>`;
  }).join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CropGuard Report — ${s.farm_name}</title>
  <style>
    body { font-family: Arial, sans-serif; color: #1a2e1f; margin: 40px; background: #fff; }
    h1 { color: #1a6b3c; margin-bottom: 4px; }
    .meta { color: #5c6b5f; margin-bottom: 24px; }
    .score { font-size: 2.5rem; font-weight: bold; color: #1a6b3c; margin: 16px 0; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th, td { border: 1px solid #dce8dc; padding: 10px; text-align: left; font-size: 14px; }
    th { background: #f4f7f4; }
    .section { margin-bottom: 28px; }
    ul { line-height: 1.8; }
    @media print { body { margin: 20px; } }
  </style>
</head>
<body>
  <h1>Farm Health Report</h1>
  <p class="meta"><strong>${s.farm_name}</strong> · ${formatCrop(s.crop_type)} · ${s.location}</p>
  <p class="meta">Period: ${s.period_from} — ${s.period_to} · Generated: ${new Date(s.generated_at).toLocaleString()}</p>
  <div class="section">
    <h2>Overall Health Score</h2>
    <div class="score">${Math.round(s.health_score)}%</div>
  </div>
  <div class="section">
    <h2>Detection Breakdown</h2>
    <ul>${breakdown}</ul>
    <p>Total detections: ${s.total_detections}</p>
  </div>
  <div class="section">
    <h2>Timeline</h2>
    <table>
      <thead><tr><th>Date</th><th>Class</th><th>Confidence</th><th>Status</th></tr></thead>
      <tbody>${rows || "<tr><td colspan='4'>No detections in period</td></tr>"}</tbody>
    </table>
  </div>
  <div class="section">
    <h2>Recommendations</h2>
    <p>${report.recommendations}</p>
  </div>
  <p class="meta" style="margin-top:40px;">Generated by CropGuard AI</p>
</body>
</html>`;
}

function downloadReportHtml(report) {
  const html = buildReportHtml(report);
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `cropguard-report-${report.summary.farm_name.replace(/\s+/g, "-").toLowerCase()}-${report.summary.period_to}.html`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function ReportBreakdownChart({ summary }) {
  const total = summary?.total_detections || 0;
  return (
    <div className="report-bar-chart">
      {REPORT_CLASSES.map((c) => {
        const pct = summary?.class_percentages?.[c.key] || 0;
        const count = summary?.class_counts?.[c.key] || 0;
        return (
          <div className="report-bar-row" key={c.key}>
            <div className="report-bar-label">{c.label}</div>
            <div className="report-bar-track">
              <div className="report-bar-fill" style={{ width: `${Math.max(pct, count ? 6 : 0)}%`, background: c.color }}>
                {count} ({pct}%)
              </div>
            </div>
          </div>
        );
      })}
      {total === 0 && (
        <p style={{ color: "var(--muted)", fontSize: "0.88rem" }}>No detections in this period.</p>
      )}
    </div>
  );
}

function ReportPreview({ report, onDownload }) {
  const s = report.summary;
  return (
    <div className="report-preview fade-in">
      <div className="report-preview-header card">
        <div>
          <h3>{s.farm_name}</h3>
          <p className="report-meta">
            {formatCrop(s.crop_type)} · {s.location}
          </p>
          <p className="report-meta">
            Report period: <strong>{s.period_from}</strong> — <strong>{s.period_to}</strong>
          </p>
          <p className="report-meta">
            Generated: {new Date(s.generated_at).toLocaleString()}
          </p>
        </div>
        <div className="report-health-big">
          <div className="report-health-label">Health Score</div>
          <div className="report-health-value">{Math.round(s.health_score)}%</div>
        </div>
      </div>

      <div className="report-breakdown-grid">
        {REPORT_CLASSES.map((c) => {
          const count = s.class_counts[c.key] || 0;
          const pct = s.class_percentages[c.key] || 0;
          return (
            <div className={`report-breakdown-card ${c.card}`} key={c.key}>
              <div className="rb-label">{c.label}</div>
              <div className="rb-count">{count}</div>
              <div className="rb-pct">{pct}% of scans</div>
            </div>
          );
        })}
      </div>

      <div className="card">
        <div className="card-title">Class Distribution</div>
        <ReportBreakdownChart summary={s} />
      </div>

      <div className="card">
        <div className="card-title">Detection Timeline</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Class</th>
                <th>Confidence</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {report.detections.length === 0 ? (
                <tr><td colSpan="4" style={{ textAlign: "center", color: "var(--muted)" }}>No detections in this date range</td></tr>
              ) : report.detections.map((d) => (
                <tr key={d.id}>
                  <td>{new Date(d.timestamp).toLocaleString()}</td>
                  <td><ClassBadge cls={d.predicted_class} /></td>
                  <td><strong>{d.confidence.toFixed(1)}%</strong></td>
                  <td>
                    <span className={`status-badge ${d.status === "Active" ? "status-critical" : "status-healthy"}`}>
                      {d.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card report-recommendations">
        <div className="card-title">Recommendations</div>
        <p className="rec-intro">Based on your farm data:</p>
        <p>{report.recommendations}</p>
      </div>

      <button className="btn btn-primary btn-export-report" onClick={() => onDownload(report)}>
        Download Report as HTML
      </button>
    </div>
  );
}

function ReportsPage({ farms, farmId, onFarmChange }) {
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return toISODate(d);
  });
  const [dateTo, setDateTo] = useState(() => toISODate(new Date()));
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function generateReport(from, to) {
    if (!farmId) {
      setError("Select a farm first");
      return;
    }
    setLoading(true);
    setError("");
    setReport(null);
    try {
      const data = await api(`/api/detections/report?farm_id=${farmId}&from=${from}&to=${to}`);
      setReport(data);
      setDateFrom(from);
      setDateTo(to);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleGenerate() {
    generateReport(dateFrom, dateTo);
  }

  function handleQuick(rangeFn, label) {
    const { from, to } = rangeFn();
    generateReport(from, to);
  }

  return (
    <div className="reports-page fade-in">
      <div className="reports-header">
        <div>
          <h2>Farm Health Reports</h2>
          <p>Generate detailed health summaries for any date range</p>
        </div>
      </div>

      <div className="card report-generator">
        <div className="report-controls">
          <div className="report-control-group">
            <label>Farm</label>
            <select value={farmId} onChange={(e) => onFarmChange(e.target.value)} disabled={!farms.length}>
              {farms.length === 0 && <option value="">No farms</option>}
              {farms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </div>
          <div className="report-control-group">
            <label>From</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div className="report-control-group">
            <label>To</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <button className="btn btn-primary btn-generate-report" onClick={handleGenerate} disabled={loading || !farmId}>
            {loading ? "Generating…" : "Generate Report"}
          </button>
        </div>
        <ErrorBox message={error} />
      </div>

      <div className="quick-report-cards">
        <button className="quick-report-card" onClick={() => handleQuick(weekDateRange, "week")} disabled={loading}>
          <div className="qr-icon">📅</div>
          <div className="qr-title">This Week</div>
          <div className="qr-sub">Last 7 days</div>
        </button>
        <button className="quick-report-card" onClick={() => handleQuick(monthDateRange, "month")} disabled={loading}>
          <div className="qr-icon">🗓️</div>
          <div className="qr-title">This Month</div>
          <div className="qr-sub">Month to date</div>
        </button>
      </div>

      {loading && <Spinner label="Generating report…" />}

      {report && !loading && (
        <ReportPreview report={report} onDownload={downloadReportHtml} />
      )}
    </div>
  );
}

// ── PAGE 2: Dashboard shell ───────────────────────────────────────────────────
const SIDEBAR_ITEMS_BASE = [
  { id: "dashboard", icon: "📊", label: "Dashboard" },
  { id: "farms", icon: "🏡", label: "My Farms" },
  { id: "analysis", icon: "🔬", label: "Analysis" },
  { id: "alerts", icon: "🚨", label: "Alerts" },
  { id: "reports", icon: "📋", label: "Reports" },
  { id: "settings", icon: "⚙️", label: "Settings" },
];

const ADMIN_SIDEBAR_ITEM = { id: "admin", icon: "🛡️", label: "Platform Admin" };

function DashboardApp({ user, onLogout }) {
  const [view, setView] = useState("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const [farms, setFarms] = useState([]);
  const [selectedFarmId, setSelectedFarmId] = useState("");
  const [stats, setStats] = useState(null);
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [alertStats, setAlertStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailFarmId, setDetailFarmId] = useState(null);
  const [farmStats, setFarmStats] = useState({});
  const [unreadCount, setUnreadCount] = useState(0);

  const farmId = selectedFarmId || (farms[0]?.id ? String(farms[0].id) : "");

  async function safeApi(path, fallback = null) {
    try {
      return await api(path);
    } catch {
      return fallback;
    }
  }

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const farmList = await api("/api/farms/");
      setFarms(farmList);
      const statsMap = {};
      await Promise.all(
        farmList.map(async (f) => {
          const s = await safeApi(`/api/farms/${f.id}/stats`);
          if (s) statsMap[f.id] = s;
          else {
            const dets = await safeApi(`/api/detections/farm/${f.id}`, []);
            const class_counts = {};
            let problems = 0;
            dets.forEach((d) => {
              class_counts[d.predicted_class] = (class_counts[d.predicted_class] || 0) + 1;
              if (d.predicted_class !== "healthy") problems += 1;
            });
            const total = dets.length;
            statsMap[f.id] = {
              health_score: total ? Math.round(((class_counts.healthy || 0) / total) * 100) : 100,
              last_scan: dets[0]?.timestamp || null,
              problems_found: problems,
              total_detections: total,
            };
          }
        })
      );
      setFarmStats(statsMap);
      const fid = selectedFarmId || (farmList[0]?.id ? String(farmList[0].id) : "");

      const [statsData, alertStatsData, recentData] = await Promise.all([
        api("/api/detections/stats"),
        safeApi("/api/alerts/stats"),
        safeApi("/api/detections/recent"),
      ]);
      setStats(statsData);
      setAlertStats(alertStatsData);

      let recent = recentData;
      if (!recent) {
        const perFarm = await Promise.all(
          farmList.map((f) => safeApi(`/api/detections/farm/${f.id}`, []))
        );
        recent = perFarm.flat().sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
      }
      setRecent(recent);

      if (fid) {
        let summaryData = await safeApi(`/api/detections/summary/${fid}`);
        if (!summaryData) {
          const dets = await safeApi(`/api/detections/farm/${fid}`, []);
          const class_counts = {};
          dets.forEach((d) => {
            class_counts[d.predicted_class] = (class_counts[d.predicted_class] || 0) + 1;
          });
          summaryData = { farm_id: Number(fid), total_detections: dets.length, class_counts };
        }
        setSummary(summaryData);
      }

      const allAlerts = await safeApi("/api/alerts/?filter=all", []);
      setAlerts((allAlerts || []).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)));

      const countData = await safeApi("/api/alerts/unread/count", null);
      if (countData?.count !== undefined) {
        setUnreadCount(countData.count);
      } else {
        setUnreadCount(alertStatsData?.unread ?? statsData?.unread_alerts ?? 0);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedFarmId]);

  const pollUnreadCount = useCallback(async () => {
    const data = await safeApi("/api/alerts/unread/count", null);
    if (data?.count !== undefined) setUnreadCount(data.count);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    pollUnreadCount();
    const interval = setInterval(pollUnreadCount, 60000);
    return () => clearInterval(interval);
  }, [pollUnreadCount]);

  async function handleMarkRead(id) {
    try {
      await markAlertRead(id);
      loadData();
      pollUnreadCount();
    } catch (err) {
      setError(err.message);
    }
  }

  const today = new Date().toISOString().slice(0, 10);
  const detectionsToday = recent.filter((d) => (d.timestamp || "").startsWith(today)).length;
  const unreadAlerts = unreadCount;
  const counts = summary?.class_counts || stats?.class_counts || {};
  const totalDet = Object.values(counts).reduce((a, b) => a + b, 0) || 0;
  const healthScore = totalDet ? Math.round(((counts.healthy || 0) / totalDet) * 100) : 100;

  const initials = (user?.name || "U").split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const isAdmin = user?.role === "admin";
  const sidebarItems = isAdmin
    ? [ADMIN_SIDEBAR_ITEM, ...SIDEBAR_ITEMS_BASE]
    : SIDEBAR_ITEMS_BASE;

  function goToAnalyse(id) {
    setSelectedFarmId(String(id));
    setDetailFarmId(null);
    setView("analysis");
  }

  function renderContent() {
    if (view === "farms" && detailFarmId) {
      return (
        <FarmDetailPage
          farmId={detailFarmId}
          onBack={() => setDetailFarmId(null)}
          onAnalyse={goToAnalyse}
          onRefresh={loadData}
        />
      );
    }
    if (view === "farms") {
      return (
        <FarmsPage
          farms={farms}
          farmStats={farmStats}
          loading={loading}
          onRefresh={loadData}
          onViewDetails={(id) => setDetailFarmId(id)}
          onAnalyse={goToAnalyse}
        />
      );
    }
    if (view === "analysis") {
      return (
        <AnalysisPage
          farms={farms}
          farmId={farmId}
          onFarmChange={setSelectedFarmId}
          onAnalyzed={loadData}
        />
      );
    }
    if (view === "alerts") {
      return (
        <AlertsPage
          farms={farms}
          onMarkRead={() => { loadData(); pollUnreadCount(); }}
          onMarkAllRead={() => { loadData(); pollUnreadCount(); }}
          onRefresh={pollUnreadCount}
        />
      );
    }
    if (view === "admin" && isAdmin) {
      return <AdminPage />;
    }
    if (view === "reports") {
      return (
        <ReportsPage
          farms={farms}
          farmId={farmId}
          onFarmChange={setSelectedFarmId}
        />
      );
    }
    if (view === "settings") {
      return (
        <div className="placeholder-view fade-in">
          <div className="icon">⚙️</div>
          <h3 style={{ color: "var(--primary)" }}>Settings</h3>
          <p>Coming soon in the next CropGuard AI release.</p>
        </div>
      );
    }
    return (
      <div className="fade-in">
        <div className="page-header">
          <h2>Farmer Dashboard</h2>
          <p>
            Real-time chrysanthemum plantation monitoring
            {farms.find((f) => String(f.id) === farmId)?.name
              ? ` — ${farms.find((f) => String(f.id) === farmId).name}`
              : ""}
          </p>
        </div>
        <ErrorBox message={error} />
        <StatsRow
          farms={farms.length}
          detectionsToday={detectionsToday}
          activeAlerts={unreadAlerts}
          healthScore={healthScore}
          loading={loading}
        />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 20 }}>
          <HealthChart summary={summary} loading={loading} />
          <QuickAnalysis farmId={farmId} farms={farms} onAnalyzed={loadData} />
        </div>
        <WeatherWidget
          farmId={farmId}
          farmName={farms.find((f) => String(f.id) === farmId)?.name}
        />
        <AlertsTable alerts={alerts} farms={farms} onMarkRead={handleMarkRead} loading={loading} error="" />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <nav className="navbar">
        <button className="sidebar-toggle" onClick={() => setSidebarOpen(!sidebarOpen)}>☰</button>
        <div className="navbar-brand">
          <span>🌿</span>
          <span className="brand-text">CropGuard <span>AI</span></span>
        </div>
        <select
          className="farm-select"
          value={farmId}
          onChange={(e) => setSelectedFarmId(e.target.value)}
        >
          {farms.length === 0 && <option value="">No farms</option>}
          {farms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <div className="navbar-spacer" />
        <NotificationBell
          unreadCount={unreadCount}
          farms={farms}
          onViewAll={() => setView("alerts")}
          onRefresh={pollUnreadCount}
        />
        <div className="user-menu">
          <div className="avatar">{initials}</div>
          <span className="user-name">{user.name}</span>
          {isAdmin && <span className="admin-badge">Admin</span>}
          <button className="btn btn-ghost" onClick={onLogout}>Logout</button>
        </div>
      </nav>

      <div className="body-row">
        <aside className={`sidebar ${sidebarCollapsed ? "collapsed" : ""} ${sidebarOpen ? "open" : ""}`}>
          <ul className="sidebar-nav">
            {sidebarItems.map((item) => (
              <li key={item.id}>
                <button
                  className={view === item.id ? "active" : ""}
                  onClick={() => { setView(item.id); setDetailFarmId(null); setSidebarOpen(false); }}
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span className="nav-label">{item.label}</span>
                </button>
              </li>
            ))}
          </ul>
          <button className="collapse-btn" onClick={() => setSidebarCollapsed(!sidebarCollapsed)}>
            {sidebarCollapsed ? "→" : "← Collapse"}
          </button>
        </aside>

        <main className="main-content">
          {renderContent()}
        </main>
      </div>
    </div>
  );
}

// ── Root App ──────────────────────────────────────────────────────────────────
function App() {
  const [user, setUser] = useState(getStoredUser());
  const [checking, setChecking] = useState(!!getToken());

  useEffect(() => {
    if (!getToken()) {
      setChecking(false);
      return;
    }
    api("/api/auth/me")
      .then((u) => setUser(u))
      .catch(() => {
        clearAuth();
        setUser(null);
      })
      .finally(() => setChecking(false));
  }, []);

  function handleLogout() {
    clearAuth();
    setUser(null);
  }

  if (checking) {
    return (
      <div className="auth-page">
        <Spinner label="Restoring session…" />
      </div>
    );
  }

  if (!user || !getToken()) {
    return <AuthPage onSuccess={setUser} />;
  }

  return (
    <ToastProvider>
      <DashboardApp user={user} onLogout={handleLogout} />
    </ToastProvider>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
