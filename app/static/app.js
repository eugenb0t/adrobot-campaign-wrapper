const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 25;
let campaigns = [], offers = [], page = 1, sortKey = "created_at", sortDir = -1;
let editing = null, pendingDelete = null, filterStatus = "all", toastTimer;
let syncPollTimer = null;
const fmt = (n, digits = 0) => Number(n || 0).toLocaleString("ru-RU", {maximumFractionDigits: digits});
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
async function request(url, options = {}) {
  const response = await fetch(url, {headers: {"Content-Type":"application/json", ...(options.headers || {})}, ...options});
  if (!response.ok) { let detail = `${response.status} ${response.statusText}`; try { detail = (await response.json()).detail || detail; } catch {} throw new Error(detail); }
  return response.status === 204 ? null : response.json();
}
function toast(message) { const node=$("toast"); node.textContent=message; node.classList.add("show"); clearTimeout(toastTimer); toastTimer=setTimeout(()=>node.classList.remove("show"),2600); }
function openDialog(id) { $(id).showModal(); }
function closeDialog(dialog) { if (dialog?.open) dialog.close(); }
function offerLabel(id) { return offers.find(o=>Number(o.id)===Number(id))?.name || `Оффер #${id}`; }
function optionsHtml(items, selected="") { return items.map(o=>`<option value="${esc(o.id)}" ${Number(o.id)===Number(selected)?"selected":""}>${esc(o.name || o.title || `#${o.id}`)}</option>`).join(""); }
async function loadSelects() {
  const offerSelect=$("offerSelect"), addSelect=$("addOfferSelect");
  try {
    offers=await request("/api/offers");
    if (!Array.isArray(offers)) offers=[];
    offerSelect.innerHTML=offers.length?`<option value="">Выберите оффер</option>${optionsHtml(offers)}`:'<option value="">Нет доступных офферов</option>';
    addSelect.innerHTML=optionsHtml(offers);
    $("createSubmit").disabled=!offers.length;
  } catch (error) {
    offers=[]; offerSelect.innerHTML='<option value="">Не удалось загрузить офферы</option>'; addSelect.innerHTML=""; $("createSubmit").disabled=true;
    $("createError").textContent=`Офферы недоступны: ${error.message}. Обновите данные и попробуйте снова.`;
  }
  for (const [path,id,placeholder] of [["domains","domainSelect","По умолчанию"],["groups","groupSelect","Без группы"],["sources","sourceSelect","Без источника"]]) {
    try { const data=await request(`/api/resources/${path}`); if(data?.length) $(id).innerHTML=`<option value="">${placeholder}</option>${optionsHtml(data)}`; } catch { /* Optional Keitaro resource. */ }
  }
}
function visibleCampaigns() {
  const query=$("search").value.trim().toLocaleLowerCase("ru");
  const rows=campaigns.filter(c=>(filterStatus==="all"||c.status===filterStatus)&&(!query||c.name.toLocaleLowerCase("ru").includes(query)||(c.country_code||"").toLocaleLowerCase().includes(query)));
  return rows.sort((a,b)=>{const av=a[sortKey]??"",bv=b[sortKey]??"";return (typeof av==="number"?av-bv:String(av).localeCompare(String(bv),"ru"))*sortDir;});
}
function renderMetrics() {
  const visits=campaigns.reduce((n,c)=>n+Number(c.visits||0),0), conversions=campaigns.reduce((n,c)=>n+Number(c.conversions||0),0), profit=campaigns.reduce((n,c)=>n+Number(c.profit||0),0), cost=campaigns.reduce((n,c)=>n+Number(c.cost||0),0);
  $("navCount").textContent=fmt(campaigns.length); $("totalCampaigns").textContent=fmt(campaigns.length);
  $("activeCount").textContent=`Активных: ${fmt(campaigns.filter(c=>c.status==="active").length)}`;
  $("totalVisits").textContent=fmt(visits); $("totalConversions").textContent=fmt(conversions);
  $("overallCr").textContent=`CR ${visits?fmt(conversions/visits*100,2):"0"}%`;
  $("totalProfit").textContent=`${fmt(profit,2)} $`; $("overallRoi").textContent=`ROI ${cost?fmt(profit/cost*100,1):"0"}%`;
}
function rowHtml(c) {
  const cr=c.visits?Number(c.conversions)/Number(c.visits)*100:0, offerIds=c.offers?.length?c.offers:(c.offer_id?[c.offer_id]:[]);
  const offerText=offerIds.length?offerIds.slice(0,2).map(id=>`<span class="offer-chip">${esc(offerLabel(id))}</span>`).join("")+(offerIds.length>2?`<span class="offer-chip">+${offerIds.length-2} ещё</span>`:""):'<span class="muted-value">Не указаны</span>';
  const name=esc(c.name), id=esc(c.keitaro_id||c.id), status=c.status==="active"?"Активна":"На паузе";
  const offerBtn=offerIds.length?`<button data-action="offers" data-id="${c.id}">Офферы</button>`:"";
  return `<tr><td class="campaign-cell"><div class="campaign-name"><span class="campaign-symbol" aria-hidden="true">↗</span><span><b>${name}</b><small class="campaign-meta">ID ${id}</small></span></div></td><td class="geo geo-cell" data-label="ГЕО">${c.country_code?esc(c.country_code):'<span class="muted-value">—</span>'}</td><td class="offer-cell" data-label="ОФФЕРЫ">${offerText}</td><td class="num number" data-label="ПЕРЕХОДЫ">${fmt(c.visits)}</td><td class="num number" data-label="КОНВЕРСИИ">${fmt(c.conversions)}</td><td class="cr-value" data-label="CR">${fmt(cr,2)}%</td><td class="${c.profit<0?"negative":"profit"}" data-label="ПРИБЫЛЬ">${fmt(c.profit,2)} $</td><td class="status-cell" data-label="СТАТУС"><span class="badge ${esc(c.status)}">${status}</span></td><td class="action-cell"><div class="row-actions"><button data-action="toggle" data-id="${c.id}">${c.status==="active"?"Пауза":"Запустить"}</button>${offerBtn}<button data-action="delete" data-id="${c.id}" aria-label="Удалить ${name}">Удалить</button></div></td></tr>`;
}
function render() {
  renderMetrics(); const filtered=visibleCampaigns(), pages=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE)); page=Math.min(page,pages);
  const slice=filtered.slice((page-1)*PAGE_SIZE,page*PAGE_SIZE); $("campaignRows").innerHTML=slice.map(rowHtml).join("");
  $("campaignRows").parentElement.style.display=filtered.length?"":"none";
  $("tableCount").textContent=fmt(filtered.length); $("showing").textContent=`Показано ${filtered.length?((page-1)*PAGE_SIZE+1):0}–${Math.min(page*PAGE_SIZE,filtered.length)} из ${fmt(filtered.length)}`;
  $("pageLabel").textContent=`${page} / ${pages}`; $("prevPage").disabled=page<=1; $("nextPage").disabled=page>=pages;
  $("empty").hidden=!!filtered.length; $("loadError").hidden=true;
  if(!filtered.length){const searching=$("search").value.trim()||filterStatus!=="all"; $("emptyTitle").textContent=campaigns.length&&searching?"Ничего не найдено":"Пока нет кампаний"; $("emptyText").textContent=campaigns.length&&searching?"Измените запрос или статус фильтра.":"Создайте первую кампанию — она появится здесь."; $("emptyCreate").hidden=campaigns.length>0;}
}
function pollSync() {
  if (syncPollTimer) return;
  syncPollTimer=setTimeout(async()=>{
    syncPollTimer=null;
    try { const health=await request("/api/health"); if(health.sync_in_progress){pollSync();return;} await refresh(); }
    catch { pollSync(); }
  },1200);
}
async function refresh(force=false) {
  $("loading").hidden=false; $("empty").hidden=true; $("loadError").hidden=true; $("campaignRows").parentElement.style.display="none";
  try { campaigns=await request(`/api/campaigns${force?"?refresh=1":""}`); render(); let health;
    try { health=await request("/api/health"); } catch { health={keitaro_configured:true,statistics_available:false}; }
    const label=$("connectionLabel"),dot=$("sideDot"),notice=$("syncNotice");
    if(!health.keitaro_configured){label.textContent="Локальные данные";dot.className="connection-dot";notice.hidden=false;notice.textContent="Локальный режим: изменения сохраняются только в этой базе данных.";}
    else if(health.sync_error){label.textContent="Keitaro недоступен";dot.className="connection-dot offline";notice.hidden=false;notice.textContent=`Не удалось загрузить данные Keitaro: ${health.sync_error}`;}
    else if(health.statistics_available===false){label.textContent="Статистика недоступна";dot.className="connection-dot offline";notice.hidden=false;notice.textContent="Кампании загружены, но отчёт Keitaro не вернул статистику. Нажмите «Обновить», чтобы повторить запрос.";}
    else {label.textContent=health.statistics_available===true?"Keitaro подключён":"Keitaro · статус проверяется";dot.className=`connection-dot ${health.statistics_available===true?"online":""}`;notice.hidden=true;}
    if(health.keitaro_configured&&health.statistics_available===false){["totalVisits","totalConversions","totalProfit","overallCr","overallRoi"].forEach(id=>$(id).textContent="—");}
    $("updatedAt").textContent=health.last_sync_at?`Синхронизировано ${new Date(health.last_sync_at*1000).toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})}`:(health.keitaro_configured?"Синхронизация выполнена":"Локальный список обновлён");
    if(health.sync_in_progress){$("syncNotice").hidden=false;$("syncNotice").textContent="Обновляем список и статистику из Keitaro…";$("updatedAt").textContent="Синхронизация выполняется";$("loading").hidden=campaigns.length>0;pollSync();}
    else if(health.sync_error){$("syncNotice").hidden=false;$("syncNotice").textContent=`Не удалось синхронизировать Keitaro: ${health.sync_error}`;}
    else if(health.keitaro_configured&&health.statistics_available===false){$("syncNotice").hidden=false;$("syncNotice").textContent="Кампании загружены, но отчёт Keitaro не вернул статистику. Нажмите «Обновить», чтобы повторить запрос.";}
  } catch(error) { campaigns=[]; renderMetrics(); $("loadErrorText").textContent=error.message; $("loadError").hidden=false; $("connectionLabel").textContent="Соединение недоступно"; $("sideDot").className="connection-dot offline"; }
  finally { if(!$("syncNotice").textContent.startsWith("Обновляем список")) $("loading").hidden=true; }
}
async function saveCampaign(event) {
  event.preventDefault(); const form=event.currentTarget, data=Object.fromEntries(new FormData(form));
  data.offer_id=Number(data.offer_id); for(const key of ["domain_id","group_id","traffic_source_id"]) data[key]=data[key]?Number(data[key]):null;
  $("createError").textContent=""; $("createSubmit").disabled=true;
  try { await request("/api/campaigns",{method:"POST",body:JSON.stringify(data)}); closeDialog($("createModal")); form.reset(); await refresh(); toast("Кампания создана"); }
  catch(error){$("createError").textContent=error.message;}
  finally{$("createSubmit").disabled=!offers.length;}
}
async function editOffers(id) {
  try {editing=await request(`/api/campaigns/${id}`); const ids=editing.offers?.length?editing.offers:(editing.offer_id?[editing.offer_id]:[]); editing.offer_ids=[...ids];
    $("editorTitle").textContent=editing.name; $("editorError").textContent=""; renderOfferList(); openDialog("editorModal");}
  catch(error){toast(`Не удалось открыть кампанию: ${error.message}`);}
}
function renderOfferList(){ $("offerList").innerHTML=editing.offer_ids.map((id,index)=>`<div class="offer-row"><span>${index+1}. ${esc(offerLabel(id))}</span>${editing.offer_ids.length>1?`<button data-remove-offer="${index}" aria-label="Убрать оффер">Убрать</button>`:""}</div>`).join("")||'<p class="muted-value">Офферы пока не добавлены.</p>'; }
async function saveOffers(){ if(!editing?.offer_ids.length){$("editorError").textContent="Добавьте хотя бы один оффер.";return;} try{await request(`/api/campaigns/${editing.id}/offers`,{method:"PUT",body:JSON.stringify({offer_ids:editing.offer_ids})});closeDialog($("editorModal"));await refresh();toast("Офферы сохранены");}catch(error){$("editorError").textContent=error.message;} }
async function toggleCampaign(id){const c=campaigns.find(x=>x.id===id);if(!c)return;try{await request(`/api/campaigns/${id}`,{method:"PATCH",body:JSON.stringify({status:c.status==="active"?"paused":"active"})});await refresh();toast(c.status==="active"?"Кампания приостановлена":"Кампания запущена");}catch(error){toast(error.message);}}
function confirmDelete(id){pendingDelete=campaigns.find(x=>x.id===id);if(!pendingDelete)return;$("confirmTitle").textContent="Удалить кампанию?";$("confirmText").textContent=`«${pendingDelete.name}» будет удалена из приложения${pendingDelete.keitaro_id?" и Keitaro":""}. Действие нельзя отменить.`;openDialog("confirmModal");}
async function deleteCampaign(){if(!pendingDelete)return;try{await request(`/api/campaigns/${pendingDelete.id}`,{method:"DELETE"});closeDialog($("confirmModal"));await refresh();toast("Кампания удалена");}catch(error){$("confirmText").textContent=error.message;}}
$("search").addEventListener("input",()=>{page=1;render();});
$("statusFilter").addEventListener("change",event=>{filterStatus=event.target.value;page=1;render();});
$("prevPage").addEventListener("click",()=>{page--;render();}); $("nextPage").addEventListener("click",()=>{page++;render();});
$("refreshButton").addEventListener("click",()=>refresh(true)); $("retryButton").addEventListener("click",()=>refresh(true));
$("createOpen").addEventListener("click",()=>{ $("createError").textContent="";openDialog("createModal"); }); $("emptyCreate").addEventListener("click",()=>openDialog("createModal"));
$("createForm").addEventListener("submit",saveCampaign); $("saveOffers").addEventListener("click",saveOffers); $("confirmAction").addEventListener("click",deleteCampaign);
$("addOffer").addEventListener("click",()=>{const id=Number($("addOfferSelect").value);if(id&&!editing.offer_ids.includes(id)){editing.offer_ids.push(id);renderOfferList();}});
document.addEventListener("click",event=>{const close=event.target.closest("[data-close]");if(close){closeDialog(close.closest("dialog"));return;}const remove=event.target.closest("[data-remove-offer]");if(remove){editing.offer_ids.splice(Number(remove.dataset.removeOffer),1);renderOfferList();return;}const action=event.target.closest("[data-action]");if(action){const id=Number(action.dataset.id);if(action.dataset.action==="offers")editOffers(id);if(action.dataset.action==="toggle")toggleCampaign(id);if(action.dataset.action==="delete")confirmDelete(id);}});
document.querySelectorAll("[data-sort]").forEach(button=>button.addEventListener("click",()=>{const key=button.dataset.sort;if(sortKey===key)sortDir*=-1;else{sortKey=key;sortDir=key==="name"?1:-1;}render();}));
document.querySelectorAll("dialog").forEach(dialog=>dialog.addEventListener("click",event=>{if(event.target===dialog)dialog.close();}));
(async()=>{await Promise.all([loadSelects(),refresh()]);})();
