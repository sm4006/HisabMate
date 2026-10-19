import { createRoot } from "react-dom/client";
import App from "./app";
import "./styles.css";

createRoot(document.getElementById("root")).render(<App />);

/* const customers = [
  { name: "Ravi General Store", last: "Today", amount: "₹2,450.00", initial: "RG" },
  { name: "Amit Kirana", last: "Yesterday", amount: "₹1,800.00", initial: "AK" },
  { name: "Suresh Traders", last: "12 Oct", amount: "₹1,250.50", initial: "ST" },
  { name: "Meena Stores", last: "10 Oct", amount: "₹980.00", initial: "MS" },
];

const activities = [
  ["Jama — Payment received", "Ravi General Store", "₹500.00", "10:42 AM", "in"],
  ["Udhaar — Credit given", "Amit Kirana", "₹800.00", "09:20 AM", "out"],
  ["Jama — Payment received", "Suresh Traders", "₹1,250.50", "Yesterday", "in"],
];

const nav = [
  ["⌂", "Dashboard"], ["♙", "Customers"], ["⇄", "Transactions"],
  ["▤", "Daily Hisab"], ["✉", "Reminders"], ["▦", "Reports & Export"],
];

function App() {
  const [composerOpen, setComposerOpen] = useState(false);
  const [message, setMessage] = useState("Ravi ko 500 rupaye ka udhaar diya.");
  const [review, setReview] = useState(false);
  const [active, setActive] = useState("Dashboard");
  const proposal = useMemo(() => ({
    customer: message.toLowerCase().includes("ravi") ? "Ravi General Store" : "Review required",
    type: message.toLowerCase().includes("jama") || message.toLowerCase().includes("paid") ? "Jama — Payment received" : "Udhaar — Credit given",
    amount: message.match(/(?:₹\s*)?\d+(?:[,.]\d{1,2})?/)?.[0] || "Amount missing",
  }), [message]);

  const interpret = () => setReview(true);
  const closeComposer = () => { setComposerOpen(false); setReview(false); };

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">॥</span><span>HisabMate</span></div>
      <p className="brand-sub">YOUR DIGITAL BAHI-KHATA</p>
      <div className="book-rule" />
      <nav>{nav.map(([icon, label]) => <button key={label} className={active === label ? "nav-item active" : "nav-item"} onClick={() => setActive(label)}><span>{icon}</span>{label}</button>)}</nav>
      <div className="sidebar-bottom">
        <div className="offline-dot"><span /> Local-first data</div>
        <button className="nav-item"><span>⚙</span> Settings</button>
        <div className="shop"><div className="shop-avatar">SK</div><div><b>Sharma Kirana</b><small>Owner</small></div><span>⌄</span></div>
      </div>
    </aside>

    <main>
      <header className="topbar">
        <div><p className="eyebrow">NAMASTE, SHARMA JI</p><h1>Today’s Hisab</h1></div>
        <div className="top-actions"><div className="date">◷ <span>Friday, 17 October 2026</span></div><button className="icon-btn" aria-label="Notifications">♧</button><button className="record-btn" onClick={() => setComposerOpen(true)}>＋ Record transaction</button></div>
      </header>

      <section className="dashboard-grid">
        <div className="content-column">
          <section className="summary-grid" aria-label="Financial summary">
            <Metric label="CUSTOMER OUTSTANDING" value="₹12,450.00" note="48 active customers" symbol="↗" variant="red" />
            <Metric label="BUSINESS PAYABLE" value="₹2,300.00" note="You owe suppliers" symbol="↙" variant="gold" />
            <Metric label="MONEY RECEIVED TODAY" value="₹3,500.00" note="12 payments recorded" symbol="↓" variant="green" />
            <Metric label="CREDIT GIVEN TODAY" value="₹1,800.00" note="5 credit entries" symbol="↑" variant="maroon" />
          </section>

          <section className="ledger-card customers-card">
            <div className="section-head"><div><p className="eyebrow">CUSTOMER-WISE BAHI</p><h2>Recent customers</h2></div><button className="text-btn">View all customers →</button></div>
            <div className="customer-table"><div className="table-head"><span>Customer</span><span>Last activity</span><span>Outstanding</span></div>{customers.map(c => <div className="customer-row" key={c.name}><div className="person"><span className="initial">{c.initial}</span><b>{c.name}</b></div><span className="muted">{c.last}</span><b className="amount">{c.amount}</b></div>)}</div>
          </section>

          <section className="ledger-card activity-card">
            <div className="section-head"><div><p className="eyebrow">DATE-WISE ENTRIES</p><h2>Recent activity</h2></div><button className="text-btn">Open transaction history →</button></div>
            {activities.map(([title, customer, amount, time, direction]) => <div className="activity" key={title + customer}><span className={`activity-icon ${direction}`}>{direction === "in" ? "↓" : "↑"}</span><div><b>{title}</b><small>{customer}</small></div><div className="activity-amount"><b>{amount}</b><small>{time}</small></div></div>)}
          </section>
        </div>

        <aside className="right-column">
          <section className="hisab-panel"><div className="paper-corner" /><p className="eyebrow">17 OCTOBER · DAILY HISAB</p><h2>Today at a glance</h2><div className="hisab-lines"><div><span>Transactions</span><b>17</b></div><div><span>Jama — money in</span><b className="green-text">₹3,500.00</b></div><div><span>Udhaar — credit out</span><b className="red-text">₹1,800.00</b></div></div><div className="closing"><span>Closing position</span><b>₹1,700.00 <small>in hand</small></b></div><button className="outline-btn">Open today’s hisab <span>→</span></button></section>
          <section className="quick-card"><p className="eyebrow">QUICK ACTIONS</p><div className="quick-grid"><Quick icon="♙" label="Add customer" /><Quick icon="▤" label="Outstanding" /><Quick icon="✉" label="Prepare reminder" /><Quick icon="⇩" label="Export ledger" /></div></section>
          <section className="ledger-card outstanding"><div className="section-head"><div><p className="eyebrow">FOLLOW UP</p><h2>Top outstanding</h2></div><button className="dots">•••</button></div>{customers.slice(0, 3).map((c, i) => <div className="outstanding-row" key={c.name}><span className="rank">0{i + 1}</span><div><b>{c.name}</b><small>Last entry {c.last}</small></div><b>{c.amount}</b></div>)}<button className="reminder-link">Prepare payment reminders →</button></section>
          <section className="ai-status"><span className="status-ring">✦</span><div><b>Local AI status</b><small>Not checked — connect Ollama to interpret entries.</small></div><button>Check status</button></section>
        </aside>
      </section>
    </main>
    {composerOpen && <Composer message={message} setMessage={setMessage} review={review} proposal={proposal} onInterpret={interpret} onClose={closeComposer} />}
  </div>;
}

function Metric({ label, value, note, symbol, variant }) { return <article className={`metric ${variant}`}><div className="metric-top"><span>{label}</span><i>{symbol}</i></div><strong>{value}</strong><small>{note}</small></article>; }
function Quick({ icon, label }) { return <button className="quick"><span>{icon}</span>{label}</button>; }

function Composer({ message, setMessage, review, proposal, onInterpret, onClose }) {
  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="composer-title"><section className="composer"><button className="close" onClick={onClose} aria-label="Close">×</button><p className="eyebrow">AI-ASSISTED ENTRY · LOCAL ONLY</p><h2 id="composer-title">Record a transaction</h2><p className="composer-copy">Write naturally in English or Hinglish. The transaction is never saved until you confirm it after backend validation.</p><label htmlFor="entry">What happened?</label><textarea id="entry" value={message} onChange={e => { setMessage(e.target.value); }} placeholder="e.g. Ravi ko 500 rupaye ka udhaar diya." />
    {!review ? <><div className="examples"><button onClick={() => setMessage("Ravi ne 200 rupaye jama kiye.")}>Ravi ne ₹200 jama kiye</button><button onClick={() => setMessage("Add ₹800 credit for Amit for grocery supplies.")}>₹800 credit for Amit</button></div><button className="record-btn full" onClick={onInterpret}>Interpret for review →</button></> : <div className="review"><div className="review-head"><div><span className="review-dot" /> Awaiting your review</div><button className="text-btn">Edit details</button></div><div className="proposal-grid"><div><small>CUSTOMER</small><b>{proposal.customer}</b></div><div><small>TRANSACTION</small><b>{proposal.type}</b></div><div><small>AMOUNT</small><b>{proposal.amount.startsWith("₹") ? proposal.amount : `₹${proposal.amount}`}</b></div><div><small>DATE</small><b>17 Oct 2026</b></div></div><div className="review-note">This is a visual review only. A backend API has not been connected, so confirming cannot save a ledger entry yet.</div><div className="review-actions"><button className="ghost-btn" onClick={onClose}>Cancel</button><button className="disabled-confirm" disabled title="Requires backend integration">Confirm transaction</button></div></div>}
  </section></div>;
}

createRoot(document.getElementById("root")).render(<App />); */
