import { useEffect, useState } from "react";
import "./heritage.css";
import "./ledger-bg.css";
import "./customer.css";

const people = [
  ["Ravi General Store", "RG", "₹2,450.00", "Today · 10:42 AM"],
  ["Amit Kirana", "AK", "₹1,800.00", "Today · 09:20 AM"],
  ["Suresh Traders", "ST", "₹1,250.50", "Yesterday"],
  ["Meena Stores", "MS", "₹980.00", "10 Oct 2026"],
];
const activity = [
  ["Jama", "Payment received", "Ravi General Store", "₹500.00", "10:42 AM", "in"],
  ["Udhaar", "Credit given", "Amit Kirana", "₹800.00", "09:20 AM", "out"],
  ["Jama", "Payment received", "Suresh Traders", "₹1,250.50", "Yesterday", "in"],
];
const pages = [["dashboard", "⌂", "Dashboard"], ["customers", "♙", "Customers"], ["ledger", "▤", "Customer ledger"], ["daily", "☼", "Daily Hisab"], ["transactions", "⇄", "Transactions"], ["reminders", "✉", "Reminders"], ["reports", "▦", "Reports & export"], ["settings", "⚙", "Settings"]];
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [composer, setComposer] = useState(false);
  const [customers, setCustomers] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [customerModal, setCustomerModal] = useState(false);
  const [selectedCustomerId, setSelectedCustomerId] = useState(null);
  const [composerCustomerId, setComposerCustomerId] = useState(null);
  const title = pages.find(([id]) => id === page)[2];
  const refresh = async () => {
    setLoading(true);
    try {
      const [dashboardResponse, customersResponse] = await Promise.all([
        fetch(`${API_BASE}/dashboard`),
        fetch(`${API_BASE}/customers`),
      ]);
      if (!dashboardResponse.ok || !customersResponse.ok) {
        throw new Error("The local ledger service returned an error.");
      }
      setDashboard(await dashboardResponse.json());
      setCustomers((await customersResponse.json()).customers);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The local ledger is unavailable.");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { refresh(); }, []);
  const peopleData = customers.map(customer => [
    customer.name,
    customer.name.split(/\s+/).map(word => word[0]).join("").slice(0, 2).toUpperCase(),
    customer.balance,
    "Local ledger",
    customer.id,
  ]);
  const activityData = (dashboard?.transactions || []).map(item => [
    item.id,
    item.transaction_type === "payment" ? "Jama" : "Udhaar",
    item.transaction_type === "payment" ? "Payment received" : "Credit given",
    item.customer_name || "Unknown customer",
    item.amount,
    item.created_at,
    item.transaction_type === "payment" ? "in" : "out",
    item.amount_paise,
  ]);
  const openCustomerModal = () => setCustomerModal(true);
  const closeCustomerModal = () => setCustomerModal(false);
  const openCustomerLedger = (customerId) => {
    setSelectedCustomerId(customerId);
    setPage("ledger");
  };
  const openComposer = (customerId = null) => {
    setComposerCustomerId(customerId);
    setComposer(true);
  };
  const createCustomer = async (name) => {
    const response = await fetch(`${API_BASE}/customers`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name}),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "The customer was not created.");
    await refresh();
    setPage("customers");
    return body;
  };
  return <div className="heritage-app">
    <aside className="heritage-side"><div className="brand-seal">श्री</div><div className="heritage-brand"><b>HisabMate</b><span>डिजिटल बही-खाता</span></div><p className="side-label">MAIN FOLIOS</p>{pages.slice(0,6).map(([id,icon,label]) => <Nav key={id} active={id===page} icon={icon} label={label} onClick={()=>setPage(id)}/>)}<p className="side-label tools">TOOLS</p>{pages.slice(6).map(([id,icon,label]) => <Nav key={id} active={id===page} icon={icon} label={label} onClick={()=>setPage(id)}/>)}<div className="side-footer"><span><i /> Local-first ledger</span><div><b>SK</b><p><strong>Sharma Kirana</strong><small>Business owner</small></p><em>⌄</em></div></div></aside>
    <main className="heritage-main"><header className="heritage-header"><div><span className="kicker">HISABMATE / {title.toUpperCase()}</span><h1>{page === "dashboard" ? "Namaste, Sharma ji." : title}</h1></div><div className="header-controls"><div className="calendar">◷ <span><b>Local ledger</b><small>{new Date().toLocaleDateString("en-IN")}</small></span></div><button className="round" aria-label="Notifications">♧</button><button className="red-button" onClick={()=>openComposer()}>＋ Record Hisab</button><button className="round" aria-label="Settings" onClick={()=>setPage("settings")}>⚙</button></div></header>{error && <div className="truth-ribbon"><b>LOCAL LEDGER OFFLINE</b><span>{error}</span></div>}{loading && <div className="truth-ribbon"><b>LOADING</b><span>Reading your local ledger…</span></div>}{!loading && !error && <div className="truth-ribbon"><b>LOCAL DATA</b><span>Balances and entries are read from SQLite.</span></div>}{page === "dashboard" && <Dashboard open={()=>openComposer()} addCustomer={openCustomerModal} openLedger={openCustomerLedger} people={peopleData} activity={activityData} dashboard={dashboard}/>} {page === "customers" && <Customers people={peopleData} addCustomer={openCustomerModal} openLedger={openCustomerLedger}/>} {page === "ledger" && <Ledger customerId={selectedCustomerId} customers={customers} openComposer={()=>openComposer(selectedCustomerId)} onSaved={async () => { await refresh(); }}/>} {page === "daily" && <History daily customers={customers}/>} {page === "transactions" && <History customers={customers}/>} {page === "reminders" && <Reminders/>} {page === "reports" && <Reports/>} {page === "settings" && <Settings/>}</main>{composer && <Composer close={()=>setComposer(false)} customers={customers} initialCustomerId={composerCustomerId} onSaved={async () => { await refresh(); }}/>} {customerModal && <CustomerModal close={closeCustomerModal} onCreated={createCustomer}/>}</div>
}
function Nav({active,icon,label,onClick}) { return <button onClick={onClick} className={`heritage-nav ${active ? "active" : ""}`}><span>{icon}</span>{label}<i>›</i></button> }
function Avatar({initials}) { return <span className="heritage-avatar">{initials}</span> }
function Card({kicker,title,action,children}) { return <section className="heritage-card"><div className="card-top"><div><span className="kicker">{kicker}</span><h2>{title}</h2></div>{action && <button className="text-link">{action}</button>}</div>{children}</section> }
function Metric({label,value,caption,icon,tone}) { return <article className={`heritage-metric ${tone}`}><span>{label}</span><i>{icon}</i><b>{value}</b><small>{caption}</small></article> }
function Transaction({item}) { const [,kind,meaning,name,amount,time,direction] = item; return <div className="transaction"><span className={`arrow ${direction}`}>{direction === "in" ? "↓" : "↑"}</span><div><b>{kind} <small>— {meaning}</small></b><span>{name}</span></div><div><b>{amount}</b><small>{time}</small></div></div> }

function Dashboard({open, addCustomer, openLedger, people, activity, dashboard}) { return <div className="dashboard-v2"><section className="welcome"><div><span className="kicker">TODAY'S KHATA</span><h2>Your books are in <em>{dashboard?.customer_count ? "good order." : "a fresh start."}</em></h2><p>Review today’s movement, follow up on balances, or add a fresh entry to your digital bahi.</p><button className="red-button" onClick={open}>Record a transaction →</button><button className="plain-button">Open daily hisab</button></div><div className="welcome-art"><span>☼</span><b>रोजनामचा</b><i>Jama</i><i>Udhaar</i><i>Balance</i><strong>❋</strong></div></section><div className="metrics"><Metric tone="red" label="CUSTOMER OUTSTANDING" value={dashboard?.outstanding || "₹0.00"} caption={`${dashboard?.customer_count || 0} customer accounts`} icon="↗"/><Metric tone="green" label="MONEY RECEIVED TODAY" value={dashboard?.received_today || "₹0.00"} caption={`${dashboard?.transactions_today || 0} entries today`} icon="↓"/><Metric tone="gold" label="CREDIT GIVEN TODAY" value={dashboard?.credit_today || "₹0.00"} caption="Local ledger total" icon="↑"/><Metric tone="ink" label="BUSINESS PAYABLE" value="₹0.00" caption="Not tracked in this ledger" icon="↙"/></div><div className="content-split"><div><Card kicker="CUSTOMER-WISE BAHI" title="Recent customer folios" action="View all customers →">{people.length === 0 ? <p className="empty-state">No customers yet. Record a customer entry to begin.</p> : <><div className="folio-row folio-head"><span>Customer account</span><span>Last entry</span><span>Balance due</span></div>{people.map(([name,initials,balance,last], index)=><button className="folio-row customer-select" key={people[index][4]} onClick={()=>openLedger(people[index][4])}><div><Avatar initials={initials}/><p><b>{name}</b><small>Local customer account</small></p></div><span>{last}</span><b>{balance}</b></button>)}</>}</Card><Card kicker="DATE-WISE ENTRIES" title="Recent activity">{activity.length === 0 ? <p className="empty-state">No transactions recorded yet.</p> : activity.map(item=><Transaction key={item[0]} item={item}/>)}</Card></div><aside><DailyCard dashboard={dashboard}/><div className="quick-actions"><span className="kicker">QUICK ACTIONS</span><div><button onClick={open}>＋<small>Record entry</small></button><button onClick={addCustomer}>♙<small>Add customer</small></button><button>✉<small>Reminder</small></button><button>⇩<small>Export ledger</small></button></div></div><Card kicker="FOLLOW-UP LIST" title="Top outstanding">{people.slice(0,3).map(([name,,balance,last],i)=><div className="outstanding" key={name}><i>0{i+1}</i><p><b>{name}</b><small>Last activity {last}</small></p><b>{balance}</b></div>)}{people.length > 0 && <button className="text-link bottom-link">Prepare payment reminders →</button>}</Card></aside></div></div> }
function DailyCard({dashboard}) { return <section className="daily-card"><span className="spark">✦</span><span className="kicker">TODAY · ROJNAMCHA</span><h2>Today’s hisab</h2><div><p><span>Total entries</span><b>{dashboard?.transactions_today || 0}</b></p><p><span>Jama <small>money in</small></span><b className="green-money">{dashboard?.received_today || "₹0.00"}</b></p><p><span>Udhaar <small>credit out</small></span><b className="red-money">{dashboard?.credit_today || "₹0.00"}</b></p></div><p className="closing"><span>Net movement</span><b>{formatMovement(dashboard)}</b></p><button>Open today’s page <b>→</b></button></section> }
function formatMovement(dashboard) {
  if (!dashboard) return "₹0.00";
  const paise = dashboard.received_today_paise - dashboard.credit_today_paise;
  const sign = paise < 0 ? "-" : "";
  const absolute = Math.abs(paise);
  return `${sign}₹${Math.floor(absolute / 100).toLocaleString("en-IN")}.${String(absolute % 100).padStart(2, "0")}`;
}
function PageTitle({kicker,title,button}) { return <div className="page-title"><div><span className="kicker">{kicker}</span><h2>{title}</h2></div>{button}</div> }
function Customers({people, addCustomer, openLedger}) { return <section className="page"><PageTitle kicker="CUSTOMER-WISE BAHI" title="Every relationship, clearly accounted for." button={<button className="red-button" onClick={addCustomer}>＋ Add customer</button>}/><div className="filters"><label>⌕ <input placeholder="Search a customer"/></label><button>Outstanding amount ↕</button><button>Recent activity ↕</button><button>All customers ⌄</button></div><Card kicker="DIRECTORY" title={`${people.length} customer accounts`}>{people.length === 0 ? <p className="empty-state">No customers yet.</p> : <><div className="directory labels"><span>Customer</span><span>Who owes whom</span><span>Last transaction</span><span>Outstanding</span></div>{people.map(([name,initials,balance,last,id])=><button className="directory customer-select" key={id} onClick={()=>openLedger(id)}><div><Avatar initials={initials}/><p><b>{name}</b><small>Local customer account</small></p></div><span><i/> Customer owes you</span><span>{last}</span><b>{balance}</b></button>)}</>}</Card></section> }
function CustomerModal({close, onCreated}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [created, setCreated] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    const normalizedName = name.trim();
    if (!normalizedName) {
      setMessage("Customer name is required.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const customer = await onCreated(normalizedName);
      setCreated(customer);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "The customer was not created.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="composer-wrap" role="dialog" aria-modal="true" aria-labelledby="customer-modal-title">
    <section className="composer-v2 customer-modal">
      <button className="close" onClick={close} aria-label="Close">×</button>
      <span className="kicker">CUSTOMER-WISE BAHI</span>
      <h2 id="customer-modal-title">Add a customer</h2>
      {created ? <><p className="customer-success" role="status"><b>{created.name}</b> was added to your local ledger.</p><p className="composer-copy">You can now select this customer when recording a transaction.</p><footer><button className="red-button" onClick={close}>Open customer directory</button></footer></> : <form className="customer-form" onSubmit={submit}>
        <label htmlFor="customer-name">Customer name</label>
        <input id="customer-name" value={name} onChange={event => { setName(event.target.value); setMessage(""); }} placeholder="e.g. Ramesh Kumar" autoFocus required />
        {message && <p className="error-message" role="alert">{message}</p>}
        <div className="customer-actions"><button type="button" className="plain-button" onClick={close}>Cancel</button><button type="submit" className="red-button" disabled={busy}>{busy ? "Saving…" : "Save customer"}</button></div>
      </form>}
    </section>
  </div>;
}
function Ledger({customerId, customers, openComposer, onSaved}) {
  const customer = customers.find(item => item.id === customerId);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!customerId) {
      setTransactions([]);
      setError("Select a customer from the directory to open a ledger.");
      setLoading(false);
      return () => { cancelled = true; };
    }
    setLoading(true);
    setError("");
    fetch(`${API_BASE}/transactions?customer_id=${encodeURIComponent(customerId)}`)
      .then(async response => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || "Unable to read this customer ledger.");
        return body.transactions;
      })
      .then(items => {
        if (!cancelled) setTransactions(items);
      })
      .catch(cause => {
        if (!cancelled) {
          setTransactions([]);
          setError(cause instanceof Error ? cause.message : "Unable to read this customer ledger.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [customerId, retryToken]);

  const retry = () => {
    setRetryToken(token => token + 1);
  };

  if (!customer) return <section className="page"><PageTitle kicker="INDIVIDUAL BAHI" title="Customer ledger"/><p className="empty-state">Choose a customer from the Customers page to view their ledger.</p></section>;
  const runningBalances = [];
  let balance = 0;
  transactions.forEach(item => {
    balance += item.transaction_type === "credit" ? item.amount_paise : -item.amount_paise;
    runningBalances.push(balance);
  });
  return <section className="page"><PageTitle kicker="INDIVIDUAL BAHI" title={customer.name} button={<button className="red-button" onClick={openComposer}>＋ Add entry</button>}/><p className="subcopy">Local customer account · Customer ID {customer.id}</p><div className="statement"><p><span>Opening balance</span><b>Not tracked</b></p><p><span>Current outstanding</span><b className="red-money">{customer.balance}</b></p><p><span>Entries</span><b>{transactions.length}</b></p></div>{loading ? <p className="empty-state">Reading this customer’s ledger…</p> : error ? <div className="ledger-error" role="alert"><b>Unable to load this ledger.</b><span>{error}</span><button className="plain-button" onClick={retry}>Retry</button></div> : transactions.length === 0 ? <Card kicker="CHRONOLOGICAL ACCOUNT" title="Ledger entries"><p className="empty-state">No transactions recorded for {customer.name} yet.</p></Card> : <Card kicker="CHRONOLOGICAL ACCOUNT" title="Ledger entries"><div className="ledger-row ledger-label"><span>Date</span><span>Details</span><span>Amount</span><span>Running balance</span></div>{transactions.map((item, index) => <div className="ledger-row" key={item.id}><span>{formatLedgerDate(item.created_at)}</span><p><b>{item.transaction_type === "payment" ? "Payment received" : "Credit given"}</b><small>{item.transaction_type === "payment" ? "Jama" : "Udhaar"}</small></p><span className={item.transaction_type === "payment" ? "green-money" : "red-money"}>{item.transaction_type === "payment" ? "-" : "+"}{item.amount}</span><b className={runningBalances[index] < 0 ? "green-money" : "red-money"}>{formatPaise(runningBalances[index])}</b></div>)}</Card>}</section>;
}
function formatLedgerDate(value) {
  const parsed = new Date(value.replace(" ", "T") + (value.includes("T") ? "" : "Z"));
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("en-IN", {day: "2-digit", month: "short", year: "numeric"});
}
function History({daily = false, customers}) {
  const [selectedDate, setSelectedDate] = useState(localBusinessDate());
  const [customerId, setCustomerId] = useState("");
  const [transactionType, setTransactionType] = useState("");
  const [search, setSearch] = useState("");
  const [exporting, setExporting] = useState(false);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadHistory = () => {
    setLoading(true);
    setError("");
    const parameters = new URLSearchParams();
    if (selectedDate) parameters.set("date", selectedDate);
    if (customerId) parameters.set("customer_id", customerId);
    if (transactionType) parameters.set("transaction_type", transactionType);
    if (search.trim()) parameters.set("search", search.trim());
    fetch(`${API_BASE}/transactions?${parameters}`)
      .then(async response => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || "Unable to read transaction history.");
        return body;
      })
      .then(setHistory)
      .catch(cause => {
        setHistory(null);
        setError(cause instanceof Error ? cause.message : "Unable to read transaction history.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(loadHistory, [selectedDate, customerId, transactionType, search]);

  const exportCsv = async () => {
    setExporting(true);
    const parameters = new URLSearchParams();
    if (selectedDate) parameters.set("date", selectedDate);
    if (customerId) parameters.set("customer_id", customerId);
    if (transactionType) parameters.set("transaction_type", transactionType);
    if (search.trim()) parameters.set("search", search.trim());
    try {
      const response = await fetch(`${API_BASE}/transactions.csv?${parameters}`);
      if (!response.ok) throw new Error("Unable to export transaction history.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "hisabmate-transactions.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to export transaction history.");
    } finally {
      setExporting(false);
    }
  };

  const items = (history?.transactions || []).map(item => [
    item.id,
    item.transaction_type === "payment" ? "Jama" : "Udhaar",
    item.transaction_type === "payment" ? "Payment received" : "Credit given",
    item.customer_name || "Unknown customer",
    item.amount,
    item.created_at,
    item.transaction_type === "payment" ? "in" : "out",
    item.amount_paise,
  ]);
  return <section className="page"><PageTitle kicker={daily ? "ROJNAMCHA · DAILY ACCOUNT" : "TARIKH-WAR INDERAJ"} title={daily ? "Today’s hisab, at a glance." : "Transaction history"} button={<div className="history-actions"><input className="date-input" type="date" value={selectedDate} onChange={event=>setSelectedDate(event.target.value)} aria-label="Transaction date"/><button className="plain-button" onClick={exportCsv} disabled={exporting}>{exporting ? "Exporting…" : "⇩ Export CSV"}</button></div>}/><div className="filters"><label>⌕ <input placeholder="Search customer or transaction type" value={search} onChange={event=>setSearch(event.target.value)}/></label><select value={customerId} onChange={event=>setCustomerId(event.target.value)} aria-label="Filter by customer"><option value="">All customers</option>{customers.map(customer=><option value={customer.id} key={customer.id}>{customer.name}</option>)}</select><select value={transactionType} onChange={event=>setTransactionType(event.target.value)} aria-label="Filter by transaction type"><option value="">All transaction types</option><option value="payment">Jama · Payment received</option><option value="credit">Udhaar · Credit given</option></select></div>{loading ? <p className="empty-state">Reading the local ledger…</p> : error ? <div className="ledger-error" role="alert"><b>Unable to load transaction history.</b><span>{error}</span><button className="plain-button" onClick={loadHistory}>Retry</button></div> : <><div className="metrics day"><Metric tone="ink" label="TRANSACTIONS" value={history.transaction_count} caption="Entries from local ledger" icon="▤"/><Metric tone="green" label="MONEY RECEIVED" value={history.received} caption="Jama · payments received" icon="↓"/><Metric tone="red" label="CREDIT GIVEN" value={history.credit} caption="Udhaar · credit given" icon="↑"/></div><Card kicker="DATE-WISE TRANSACTIONS" title={`${history.transaction_count} entries · ${selectedDate}`}>{items.length === 0 ? <p className="empty-state">No transactions recorded for this date and filter.</p> : items.map(item=><Transaction key={item[0]} item={item}/>)}</Card></>}</section>;
}
function localBusinessDate() {
  return new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Kolkata"}).format(new Date());
}
function Reminders() { return <section className="page"><PageTitle kicker="TAAQADA · PAYMENT FOLLOW-UP" title="Kind reminders, ready to personalise."/>{people.slice(0,3).map(([name,initials,balance])=><article className="reminder" key={name}><Avatar initials={initials}/><div><b>{name} · <em>{balance} due</em></b><blockquote>“Namaste, aapke account mein {balance} baki hain. Jab suvidha ho, kripya payment kar dein. Dhanyavaad.”</blockquote><small>This draft has not been sent.</small></div><p><button className="plain-button">Edit</button><button className="plain-button">Copy message</button></p></article>)}</section> }
function Reports() { return <section className="page"><PageTitle kicker="REPORTS & LOCAL EXPORT" title="Understand your books, without noise."/><div className="report-grid">{[["Customer outstanding","Who needs a follow-up?"],["Daily transaction summary","What happened on a given day?"],["Customer statement","A shareable account ledger."],["Date-range history","A complete audit-friendly view."]].map(([title,copy])=><article key={title}><i>▦</i><h3>{title}</h3><p>{copy}</p><button className="text-link">Open report →</button></article>)}</div></section> }
function Settings() { return <section className="page"><PageTitle kicker="LOCAL-FIRST SETTINGS" title="Your data, your device."/><div className="settings-list">{[["Local ledger","SQLite connection has not been checked by this UI.","Status unknown"],["Local AI","Connect an Ollama service to interpret a natural-language entry.","Not connected"],["Backups","No backup status is available until a local backup process is configured.","Not configured"],["Privacy","HisabMate is designed to keep ledger data on this device.","Local-first"]].map(([title,copy,badge])=><article key={title}><div><h3>{title}</h3><p>{copy}</p></div><span>{badge}</span><button className="plain-button">Configure</button></article>)}</div></section> }
function Composer({close, customers, initialCustomerId, onSaved}) {
  const [text, setText] = useState("");
  const [proposal, setProposal] = useState(null);
  const [selectedCustomer, setSelectedCustomer] = useState(initialCustomerId ? String(initialCustomerId) : "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const interpret = async () => {
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`${API_BASE}/interpret`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message: text}),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Unable to interpret this entry.");
      setProposal(body);
      const match = customers.find(customer => customer.name.toLowerCase() === (body.customer_name || "").toLowerCase());
      setSelectedCustomer(match ? String(match.id) : "");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Unable to interpret this entry.");
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`${API_BASE}/transactions`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          proposal_id: `${Date.now()}-${text}`,
          confirmed: true,
          intent: proposal.intent,
          customer_id: Number(selectedCustomer),
          amount_paise: proposal.amount_paise,
          missing_information: proposal.missing_information,
          ambiguous: proposal.ambiguous,
          transaction_date: proposal.transaction_date,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "The transaction was not saved.");
      onSaved();
      close();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "The transaction was not saved.");
    } finally {
      setBusy(false);
    }
  };
  const canSave = proposal && !proposal.clarification_required && selectedCustomer && !busy;
  return <div className="composer-wrap"><section className="composer-v2"><button className="close" onClick={close} aria-label="Close">×</button><span className="kicker">AI-ASSISTED ENTRY · REVIEW REQUIRED</span><h2>Write it the way you say it.</h2><p>English or Hinglish works. The final ledger write must be validated by the local backend and confirmed by you.</p>{!proposal ? <><textarea value={text} onChange={e=>setText(e.target.value)} placeholder="e.g. Ravi ko 500 rupaye ka udhaar diya."/><div className="chips"><button onClick={()=>setText("Ramesh ne 200 rupaye jama kiye.")}>Ramesh ne ₹200 jama kiye</button><button onClick={()=>setText("Asha ko ₹800 ka maal diya.")}>₹800 credit for Asha</button></div><button className="red-button full" onClick={interpret} disabled={busy || !text.trim()}>{busy ? "Interpreting…" : "Interpret for review →"}</button></> : <><section className="proposal"><header><b><i/> Awaiting your review</b><button className="text-link" onClick={()=>setProposal(null)}>Edit entry</button></header><div><p><small>CUSTOMER</small><select value={selectedCustomer} onChange={event=>setSelectedCustomer(event.target.value)}><option value="">Select a customer</option>{customers.map(customer=><option value={customer.id} key={customer.id}>{customer.name}</option>)}</select></p><p><small>TRANSACTION</small><b>{proposal.intent === "payment" ? "Jama — Payment received" : "Udhaar — Credit given"}</b></p><p><small>AMOUNT</small><b>{proposal.amount_paise == null ? "Missing" : formatPaise(proposal.amount_paise)}</b></p><p><small>DATE</small><b>{proposal.transaction_date || "Today"}</b></p></div><aside>{proposal.clarification_required ? `Clarification required: ${proposal.missing_information.join(", ")}` : "Review the details, then confirm to save through the local ledger."}</aside></section><footer><button className="plain-button" onClick={close}>Cancel</button><button onClick={save} disabled={!canSave}>{busy ? "Saving…" : "Confirm transaction"}</button></footer></>}{message && <p className="error-message" role="alert">{message}</p>}</section></div>
}
function formatPaise(amount) { const rupees = Math.floor(amount / 100); return `₹${rupees.toLocaleString("en-IN")}.${String(amount % 100).padStart(2, "0")}`; }
