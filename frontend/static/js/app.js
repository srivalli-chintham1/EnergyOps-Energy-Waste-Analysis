let currentPage = 1;
let currentTable = "";
let currentTotal = 0;
const $ = id => document.getElementById(id);
async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}
function pretty(s){return s.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase())}
async function loadSummary(){
  const data = await api("/api/summary");
  $("tableCount").textContent = data.table_count;
  $("recordCount").textContent = data.record_count.toLocaleString();
  const insights = await api("/api/insights");
  $("energyTotal").textContent = insights.total_energy_kwh === undefined ? "Not detected" : Number(insights.total_energy_kwh).toLocaleString();
  $("summaryList").innerHTML = Object.entries(data.tables).map(([k,v]) =>
    `<div class="summary-item"><b>${v.toLocaleString()}</b><span>${pretty(k)}</span></div>`).join("");
  $("notes").innerHTML = (insights.notes || []).map(n=>`<li>${n}</li>`).join("");
}
async function loadTables(){
  const data = await api("/api/tables");
  $("tableSelect").innerHTML = data.tables.map(t=>`<option value="${t}">${pretty(t)}</option>`).join("");
  if(data.tables.length){currentTable=data.tables.includes("daily_plant_summary")?"daily_plant_summary":data.tables[0];$("tableSelect").value=currentTable;await loadTable();}
}
async function loadTable(){
  if(!currentTable)return;
  const data=await api(`/api/table/${encodeURIComponent(currentTable)}?page=${currentPage}`);
  currentTotal=data.total;
  $("tableMeta").textContent=`${pretty(data.name)} · ${data.total.toLocaleString()} records · 25 rows per page`;
  const head=`<thead><tr>${data.columns.map(c=>`<th>${c}</th>`).join("")}</tr></thead>`;
  const body=data.rows.length?`<tbody>${data.rows.map(row=>`<tr>${data.columns.map(c=>`<td title="${String(row[c]??"").replaceAll('"',"&quot;")}">${row[c]??""}</td>`).join("")}</tr>`).join("")}</tbody>`:"<tbody><tr><td>No records found.</td></tr></tbody>";
  $("dataTable").innerHTML=head+body;
  const pages=Math.max(1,Math.ceil(data.total/data.page_size));
  $("pageInfo").textContent=`Page ${currentPage} of ${pages}`;
  $("prevBtn").disabled=currentPage<=1;$("nextBtn").disabled=currentPage>=pages;
}
$("tableSelect").addEventListener("change",async e=>{currentTable=e.target.value;currentPage=1;await loadTable();});
$("prevBtn").addEventListener("click",async()=>{if(currentPage>1){currentPage--;await loadTable();}});
$("nextBtn").addEventListener("click",async()=>{if(currentPage*25<currentTotal){currentPage++;await loadTable();}});
$("reloadBtn").addEventListener("click",async()=>{try{$("reloadBtn").disabled=true;await api("/api/reload",{method:"POST"});currentPage=1;await loadSummary();await loadTables();alert("CSV data reloaded successfully.");}catch(e){alert(e.message);}finally{$("reloadBtn").disabled=false;}});
(async()=>{try{await loadSummary();await loadTables();}catch(e){document.body.insertAdjacentHTML("afterbegin",`<p style="padding:12px;color:#b42318">Application error: ${e.message}</p>`);}})();
