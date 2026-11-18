import React, { useEffect, useState, useCallback } from "react";
import { api, setToken, hasToken, rs } from "./api.js";

const Stat = ({ label, value }) => (<div className="stat"><b>{value}</b><span>{label}</span></div>);
const Field = ({ label, children }) => (<div><label>{label}</label>{children}</div>);
const useLoad = (fn, deps = []) => {
  const [d, setD] = useState(null); const [e, setE] = useState("");
  const load = useCallback(() => fn().then((x) => { setD(x); setE(""); }).catch((x) => setE(x.message)), deps);
  useEffect(() => { load(); }, [load]);
  return [d, e, load];
};

/* ---------- Auth ---------- */
function Auth({ onDone }) {
  const [mode, setMode] = useState("login"); const [f, setF] = useState({ household_size: 3, sanctioned_kw: 1, tariff_id: "karnataka_sample_v1" });
  const [err, setErr] = useState(""); const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async () => {
    try {
      const body = mode === "login" ? { email: f.email, password: f.password }
        : { ...f, household_size: +f.household_size, sanctioned_kw: +f.sanctioned_kw };
      const r = await api(`/auth/${mode === "login" ? "login" : "register"}`, { method: "POST", body });
      setToken(r.token); onDone(r.user);
    } catch (e) { setErr(e.message); }
  };
  return (
    <div className="card auth"><h2>{mode === "login" ? "Sign in" : "Create account"}</h2>
      <div style={{ display: "grid", gap: 10 }}>
        {mode === "register" && <Field label="Name"><input onChange={set("name")} /></Field>}
        <Field label="Email"><input type="email" onChange={set("email")} /></Field>
        <Field label="Password (8+ chars)"><input type="password" onChange={set("password")} /></Field>
        {mode === "register" && <>
          <div className="row"><Field label="Household size"><input type="number" value={f.household_size} onChange={set("household_size")} /></Field>
            <Field label="Sanctioned load (kW)"><input type="number" step="0.5" value={f.sanctioned_kw} onChange={set("sanctioned_kw")} /></Field></div>
          <Field label="Consumer number (stored encrypted, optional)"><input onChange={set("consumer_no")} /></Field></>}
        {err && <div className="err">{err}</div>}
        <button className="btn" onClick={submit}>{mode === "login" ? "Sign in" : "Register"}</button>
        <button className="link" style={{ color: "var(--teal)" }} onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(""); }}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}</button>
      </div></div>);
}

/* ---------- Bills ---------- */
function Breakdown({ b }) {
  const parts = [["Energy", b.energy_charges, "#0f4c4f"], ["Fixed", b.fixed_charges, "#f0a500"], ["Fuel adj.", b.fuel_adjustment, "#6aa6a8"],
    ["Duty/tax", b.electricity_duty, "#9aa9ae"]];
  const sum = parts.reduce((s, p) => s + p[1], 0) || 1;
  return (<div>
    <div className="bar">{parts.map((p) => <i key={p[0]} title={p[0]} style={{ width: `${p[1] / sum * 100}%`, background: p[2] }} />)}</div>
    <table><tbody>
      {b.slab_lines.map((l, i) => <tr key={i}><td>Slab {i + 1}: {l.units} units @ {l.rate}</td><td className="r">{rs(l.amount)}</td></tr>)}
      <tr><td>Fixed charges</td><td className="r">{rs(b.fixed_charges)}</td></tr>
      <tr><td>Fuel / power-purchase adjustment</td><td className="r">{rs(b.fuel_adjustment)}</td></tr>
      {b.subsidy > 0 && <tr><td>Free-unit subsidy</td><td className="r">- {rs(b.subsidy)}</td></tr>}
      <tr><td>Electricity duty</td><td className="r">{rs(b.electricity_duty)}</td></tr>
      <tr><th>Total ({b.effective_rate}/unit effective)</th><th className="r">{rs(b.total)}</th></tr></tbody></table></div>);
}

function Bills() {
  const [bills, err, reload] = useLoad(() => api("/bills"));
  const [f, setF] = useState({ month: new Date().toISOString().slice(0, 7), units: "", amount_actual: "" });
  const [open, setOpen] = useState(null); const [msg, setMsg] = useState("");
  const add = async () => {
    try { await api("/bills", { method: "POST", body: { month: f.month, units: +f.units, amount_actual: f.amount_actual ? +f.amount_actual : null } }); setMsg(""); reload(); }
    catch (e) { setMsg(e.message); }
  };
  const upload = async (e) => {
    const fd = new FormData(); fd.append("file", e.target.files[0]);
    const r = await api("/bills/import-csv", { method: "POST", form: fd });
    setMsg(`Imported ${r.added}. ${r.errors.join(" | ")}`); reload();
  };
  return (<>
    <div className="card"><h2>Add a bill</h2>
      <div className="row">
        <Field label="Month"><input type="month" value={f.month} onChange={(e) => setF({ ...f, month: e.target.value })} /></Field>
        <Field label="Units consumed"><input type="number" value={f.units} onChange={(e) => setF({ ...f, units: e.target.value })} /></Field>
        <Field label="Amount on your bill (Rs, for audit)"><input type="number" value={f.amount_actual} onChange={(e) => setF({ ...f, amount_actual: e.target.value })} /></Field>
        <button className="btn" onClick={add}>Add</button></div>
      <h3>Or upload CSV (month,units,amount_actual)</h3><input type="file" accept=".csv" onChange={upload} />
      {(msg || err) && <div className="err">{msg || err}</div>}</div>
    <div className="card"><h2>Your bills</h2>
      <table><thead><tr><th>Month</th><th className="r">Units</th><th className="r">Computed</th><th>Audit</th><th /></tr></thead><tbody>
        {(bills || []).slice().reverse().map((b) => (<React.Fragment key={b.id}>
          <tr><td><button className="link" style={{ color: "var(--teal)" }} onClick={() => setOpen(open === b.id ? null : b.id)}>{b.month}</button></td>
            <td className="r">{b.units}</td><td className="r">{rs(b.breakdown.total)}</td>
            <td>{b.audit ? <span className={`tag ${b.audit.flag ? "warning" : ""}`} title={b.audit.message}>{b.audit.flag ? `Off by ${rs(b.audit.difference)}` : "Matches"}</span> : "-"}</td>
            <td><button className="link" onClick={async () => { await api(`/bills/${b.id}`, { method: "DELETE" }); reload(); }}>delete</button></td></tr>
          {open === b.id && <tr><td colSpan="5"><Breakdown b={b.breakdown} />{b.audit?.flag && <p className="err">{b.audit.message}</p>}</td></tr>}
        </React.Fragment>))}</tbody></table></div></>);
}

/* ---------- Slab tracker ---------- */
function Slab() {
  const [d, err, reload] = useLoad(() => api("/slab-tracker"));
  const [r, setR] = useState({ day: new Date().toISOString().slice(0, 10), units: "" });
  if (!d) return <div className="card">{err || "Loading..."}</div>;
  const nb = d.status_now.next_boundary; const pct = nb ? Math.min(d.units_so_far / nb.at_units * 100, 100) : 100;
  return (<>
    <div className="card"><h2>Where you stand this month</h2>
      <div className="grid"><Stat label="Units so far" value={d.units_so_far} /><Stat label="Projected units" value={d.projection.projected_units} />
        <Stat label="Projected bill" value={rs(d.projected_bill.total)} /><Stat label="Cost of next unit" value={rs(d.status_now.marginal_cost_per_unit)} /></div>
      {nb && <><h3>{nb.units_left} units to: {nb.label}</h3><div className="gauge"><i style={{ left: `${pct}%` }} /></div>
        {d.daily_budget && <p>Safe budget: <b className="num">{d.daily_budget.safe_daily_units}</b> units/day for the remaining {d.projection.days_left} days.</p>}</>}
      {d.nudge && <div className="nudge">{d.nudge}</div>}
      {d.reduction_plan?.plan?.length > 0 && <><h3>Minimum-sacrifice plan to stay under the boundary</h3>
        <ul>{d.reduction_plan.plan.map((p) => <li key={p.name}>Use {p.name} {p.reduce_hours_per_day} h/day less (saves {p.units_saved} units)</li>)}</ul></>}
      {d.entitled_units > 0 && <p className="mono">Free-unit entitlement: {d.entitled_units} units</p>}</div>
    <div className="card"><h2>Log a daily meter reading</h2><div className="row">
      <Field label="Date"><input type="date" value={r.day} onChange={(e) => setR({ ...r, day: e.target.value })} /></Field>
      <Field label="Units used that day"><input type="number" value={r.units} onChange={(e) => setR({ ...r, units: e.target.value })} /></Field>
      <button className="btn" onClick={async () => { await api("/readings", { method: "POST", body: { day: r.day, units: +r.units } }); reload(); }}>Save</button></div></div></>);
}

/* ---------- Appliances ---------- */
function Appliances() {
  const [an, err, reload] = useLoad(() => api("/appliances/analysis"));
  const [presets] = useLoad(() => api("/appliances/presets"));
  const [f, setF] = useState({ name: "", watts: "", hours_per_day: "", qty: 1, duty: 1 });
  const add = async (x) => { await api("/appliances", { method: "POST", body: x }); reload(); };
  return (<>
    <div className="card"><h2>Add appliances</h2>
      <div className="row">
        <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Watts"><input type="number" value={f.watts} onChange={(e) => setF({ ...f, watts: e.target.value })} /></Field>
        <Field label="Hours/day"><input type="number" value={f.hours_per_day} onChange={(e) => setF({ ...f, hours_per_day: e.target.value })} /></Field>
        <Field label="Qty"><input type="number" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} /></Field>
        <button className="btn" onClick={() => add({ ...f, watts: +f.watts, hours_per_day: +f.hours_per_day, qty: +f.qty, duty: +f.duty })}>Add</button></div>
      <h3>Quick add</h3>{(presets || []).map((p) => <button key={p.name} className="btn alt" style={{ margin: 3 }} onClick={() => add({ ...p, qty: 1 })}>{p.name}</button>)}</div>
    {an && an.appliances.length > 0 && <div className="card"><h2>Consumption by appliance</h2>
      <p>Estimated {an.estimated_total} units{an.actual_units ? ` vs metered ${an.actual_units} (unaccounted ${an.unaccounted_units}; estimates scaled x${an.calibration_factor})` : ""}. {an.accuracy_note}</p>
      <table><tbody>{an.appliances.map((a) => (<tr key={a.id}><td>{a.name}{a.qty > 1 ? ` x${a.qty}` : ""}</td>
        <td style={{ width: "40%" }}><div className="bar"><i style={{ width: `${a.share_pct}%`, background: "var(--teal)" }} /></div></td>
        <td className="r">{a.calibrated_kwh} u</td><td className="r">{a.share_pct}%</td>
        <td><button className="link" onClick={async () => { await api(`/appliances/${a.id}`, { method: "DELETE" }); reload(); }}>x</button></td></tr>))}</tbody></table>
      <h3>Savings suggestions (Rs per month, computed on your tariff)</h3>
      <ul>{an.suggestions.map((s, i) => <li key={i}><b>{s.appliance}:</b> {s.tip} - saves {s.units_saved} units, <b>{rs(s.rupees_saved_per_month)}</b></li>)}</ul></div>}
    {err && <div className="err">{err}</div>}</>);
}

/* ---------- What-if ---------- */
function WhatIf() {
  const [apps] = useLoad(() => api("/appliances")); const [delta, setDelta] = useState({}); const [res, setRes] = useState(null); const [err, setErr] = useState("");
  const run = async () => {
    try { setRes(await api("/whatif", { method: "POST", body: { changes: Object.entries(delta).map(([name, d]) => ({ name, delta_hours_per_day: +d })) } })); setErr(""); }
    catch (e) { setErr(e.message); }
  };
  return (<div className="card"><h2>What-if simulator</h2><p>Change daily hours and see the effect on units, bill and slab.</p>
    {(apps || []).map((a) => (<div key={a.id} className="row" style={{ marginBottom: 6 }}><span>{a.name} ({a.hours_per_day} h/day)</span>
      <input type="range" min={-Math.min(a.hours_per_day, 8)} max="4" step="0.25" value={delta[a.name] ?? 0} onChange={(e) => setDelta({ ...delta, [a.name]: e.target.value })} />
      <span className="mono">{(+(delta[a.name] ?? 0)) > 0 ? "+" : ""}{delta[a.name] ?? 0} h</span></div>))}
    <button className="btn" onClick={run}>Simulate</button>{err && <div className="err">{err}</div>}
    {res && <div className="grid" style={{ marginTop: 14 }}><Stat label="Units before to after" value={`${res.before_units} to ${res.after_units}`} />
      <Stat label="Bill before" value={rs(res.before_bill)} /><Stat label="Bill after" value={rs(res.after_bill)} />
      <Stat label="Change" value={`${res.bill_change > 0 ? "+" : ""}${rs(res.bill_change)}`} /></div>}</div>);
}

/* ---------- Forecast & alerts ---------- */
function Forecast() {
  const [d, err] = useLoad(() => api("/forecast")); const [al, , reloadAl] = useLoad(() => api("/alerts"));
  if (!d) return <div className="card">{err || "Loading..."}</div>;
  const h = d.history.slice(-12), max = Math.max(...h.map((x) => x.units), d.forecast.high) * 1.1, W = 640, H = 180, bw = W / (h.length + 1);
  return (<>
    <div className="card"><h2>Next month forecast</h2>
      <div className="grid"><Stat label="Forecast units" value={d.forecast.units} /><Stat label="Forecast bill" value={rs(d.forecast.bill)} />
        <Stat label="Likely range (80%)" value={`${rs(d.forecast.bill_low)} - ${rs(d.forecast.bill_high)}`} /></div>
      <svg viewBox={`0 0 ${W} ${H + 20}`} style={{ width: "100%", marginTop: 12 }}>
        {h.map((x, i) => <g key={x.month}><rect x={i * bw + 6} y={H - x.units / max * H} width={bw - 10} height={x.units / max * H} fill="#0f4c4f" />
          <text x={i * bw + bw / 2} y={H + 14} fontSize="9" textAnchor="middle">{x.month.slice(5)}</text></g>)}
        <rect x={h.length * bw + 6} y={H - d.forecast.units / max * H} width={bw - 10} height={d.forecast.units / max * H} fill="#f0a500" />
        <line x1={h.length * bw + bw / 2} x2={h.length * bw + bw / 2} y1={H - d.forecast.high / max * H} y2={H - d.forecast.low / max * H} stroke="#12262c" strokeWidth="2" />
        <text x={h.length * bw + bw / 2} y={H + 14} fontSize="9" textAnchor="middle">next</text></svg>
      <p className="mono">Method: {d.forecast.method}</p>
      {d.benchmark && <p>Household benchmark: you use <b>{d.benchmark.your_units}</b> vs typical <b>{d.benchmark.typical_units}</b> for {d.benchmark.household_size} people ({d.benchmark.label}, ~{d.benchmark.percentile_estimate}th percentile). <i>{d.benchmark.note}</i></p>}
      {d.anomaly?.anomaly && <div className="nudge">Last month was unusual: {d.anomaly.pct_vs_mean}% vs your average (z = {d.anomaly.z_score}).</div>}</div>
    <div className="card"><h2>Alerts</h2><button className="btn alt" onClick={async () => { await api("/alerts/refresh", { method: "POST" }); reloadAl(); }}>Check now</button>
      {(al || []).length === 0 && <p>No alerts.</p>}
      {(al || []).map((a) => <p key={a.id}><span className={`tag ${a.severity}`}>{a.kind}</span> {a.message}</p>)}</div></>);
}

/* ---------- Solar ---------- */
function Solar() {
  const [f, setF] = useState({ roof_area_m2: 30, sun_hours: 5, cost_per_kw: 55000, mode: "net_metering", export_rate: 3, battery_kwh: 0, loan_pct: 0, state_subsidy: 0 });
  const [res, setRes] = useState(null); const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const run = async () => {
    try { const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, k === "mode" ? v : +v]));
      if (f.units_per_month) body.units_per_month = +f.units_per_month;
      setRes(await api("/solar", { method: "POST", body })); setErr(""); } catch (e) { setErr(e.message); }
  };
  const r = res?.result;
  return (<>
    <div className="card"><h2>Solar payback planner</h2>
      <div className="row">
        <Field label="Roof area (m2)"><input type="number" value={f.roof_area_m2} onChange={set("roof_area_m2")} /></Field>
        <Field label="Peak sun hours/day"><input type="number" step="0.5" value={f.sun_hours} onChange={set("sun_hours")} /></Field>
        <Field label="Cost per kW (Rs)"><input type="number" value={f.cost_per_kw} onChange={set("cost_per_kw")} /></Field>
        <Field label="Units/month (blank = from bills)"><input type="number" onChange={set("units_per_month")} /></Field>
        <Field label="Metering"><select value={f.mode} onChange={set("mode")}><option value="net_metering">Net metering</option><option value="net_billing">Net billing</option></select></Field>
        <Field label="Export rate (Rs/unit)"><input type="number" step="0.5" value={f.export_rate} onChange={set("export_rate")} /></Field>
        <Field label="Battery (kWh)"><input type="number" value={f.battery_kwh} onChange={set("battery_kwh")} /></Field>
        <Field label="Loan share (0-1)"><input type="number" step="0.1" value={f.loan_pct} onChange={set("loan_pct")} /></Field>
        <Field label="State subsidy (Rs)"><input type="number" value={f.state_subsidy} onChange={set("state_subsidy")} /></Field>
        <button className="btn" onClick={run}>Calculate</button></div>{err && <div className="err">{err}</div>}</div>
    {r && <><div className="card"><h2>Result: {r.system_kw} kW system{r.limited_by_roof ? " (limited by roof)" : ""}</h2>
      <div className="grid"><Stat label="Payback (years)" value={r.payback_years ?? "n/a"} /><Stat label="10-year net savings" value={rs(r.ten_year_net_savings)} />
        <Stat label="Net cost after subsidy" value={rs(r.net_cost)} /><Stat label="Subsidy" value={rs(r.subsidy)} />
        <Stat label="IRR" value={r.irr_percent ? `${r.irr_percent}%` : "n/a"} /><Stat label="CO2 avoided / yr" value={`${r.co2_avoided_tonnes_per_year} t`} />
        {r.monthly_emi > 0 && <Stat label="Monthly EMI" value={rs(r.monthly_emi)} />}{r.backup_hours_essential_load > 0 && <Stat label="Backup hours" value={r.backup_hours_essential_load} />}</div>
      <p style={{ fontSize: 12 }}>{r.assumptions}</p></div>
      <div className="card"><h2>Scenario comparison</h2><table><thead><tr><th>Scenario</th><th className="r">Payback</th><th className="r">Net cost</th><th className="r">10-yr net</th><th className="r">IRR</th></tr></thead>
        <tbody>{res.scenarios.map((s) => <tr key={s.label}><td>{s.label}</td><td className="r">{s.payback_years ?? "n/a"} y</td><td className="r">{rs(s.net_cost)}</td><td className="r">{rs(s.ten_year_net_savings)}</td><td className="r">{s.irr_percent ?? "n/a"}%</td></tr>)}</tbody></table></div></>}</>);
}

/* ---------- Smart meter + tariff lab ---------- */
function Lab() {
  const [sim, setSim] = useState(null); const [cmp, setCmp] = useState(null); const [tariffs] = useLoad(() => api("/tariffs"));
  const [pair, setPair] = useState({ old_id: "karnataka_sample_v1", new_id: "karnataka_sample_v2" }); const [err, setErr] = useState("");
  const S = sim?.power_series_w;
  return (<>
    <div className="card"><h2>Smart-meter simulator + appliance detection (NILM-lite)</h2>
      <p>Generates 30 days of minute-level readings from your appliance list, saves daily totals, then detects which appliances ran today purely from the aggregate power signal.</p>
      <button className="btn" onClick={async () => { try { setSim(await api("/simulate/meter?days=30", { method: "POST" })); setErr(""); } catch (e) { setErr(e.message); } }}>Generate readings</button>
      {err && <div className="err">{err}</div>}
      {S && <><svg viewBox={`0 0 ${S.length} 100`} preserveAspectRatio="none" style={{ width: "100%", height: 120, marginTop: 10 }}>
        <polyline fill="none" stroke="#0f4c4f" strokeWidth="1" points={S.map((v, i) => `${i},${100 - v / Math.max(...S) * 95}`).join(" ")} /></svg>
        <table><thead><tr><th>Detected appliance</th><th className="r">Sessions</th><th className="r">Minutes</th><th className="r">kWh today</th></tr></thead>
          <tbody>{sim.nilm_today.map((n) => <tr key={n.name}><td>{n.name}</td><td className="r">{n.sessions}</td><td className="r">{n.minutes}</td><td className="r">{n.kwh_today}</td></tr>)}</tbody></table></>}</div>
    <div className="card"><h2>Tariff change impact</h2><p>See how your last 12 bills would change under a revised tariff file.</p>
      <div className="row">{["old_id", "new_id"].map((k) => <Field key={k} label={k === "old_id" ? "Current" : "Revised"}><select value={pair[k]} onChange={(e) => setPair({ ...pair, [k]: e.target.value })}>
        {(tariffs || []).map((t) => <option key={t.id} value={t.id}>{t.id} ({t.version})</option>)}</select></Field>)}
        <button className="btn" onClick={async () => { try { setCmp(await api("/tariffs/compare", { method: "POST", body: pair })); setErr(""); } catch (e) { setErr(e.message); } }}>Compare</button></div>
      {cmp && <p>Over {cmp.rows.length} bills: <b>{rs(cmp.total_diff)}</b> difference, about <b>{rs(cmp.annualised_diff)}</b> per year.</p>}</div></>);
}

/* ---------- Shell ---------- */
const TABS = { Bills, "Slab tracker": Slab, Appliances, "What-if": WhatIf, "Forecast & alerts": Forecast, Solar, "Lab": Lab };

export default function App() {
  const [user, setUser] = useState(null); const [tab, setTab] = useState("Bills"); const [ready, setReady] = useState(!hasToken());
  useEffect(() => { if (hasToken()) api("/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setReady(true)); }, []);
  if (!ready) return null;
  const Page = TABS[tab];
  return (<>
    <header><div><h1>Unit Ledger</h1><small>Tariff-aware bill analyzer and solar planner</small></div>
      {user && <div>{user.name} <button className="btn alt" style={{ marginLeft: 8 }} onClick={() => { setToken(null); setUser(null); }}>Sign out</button></div>}</header>
    {!user ? <Auth onDone={setUser} /> : <>
      <nav>{Object.keys(TABS).map((t) => <button key={t} className={t === tab ? "on" : ""} onClick={() => setTab(t)}>{t}</button>)}</nav>
      <main><Page key={tab} /></main></>}
  </>);
}
