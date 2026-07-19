const $ = (s) => document.querySelector(s);

function clock() {
  const d = new Date();
  $("#clock").textContent = d.toTimeString().slice(0, 8) + " Z";
}
setInterval(clock, 1000); clock();

function branchColor(v) {
  if (v >= 85) return "var(--accent)";
  if (v >= 70) return "var(--amber)";
  return "var(--red)";
}
function threatColor(v) {
  if (v >= 70) return "var(--red)";
  if (v >= 40) return "var(--amber)";
  return "var(--accent)";
}

async function refresh() {
  let d;
  try {
    d = await (await fetch("/api/dashboard")).json();
  } catch (e) { return; }

  // posture
  const p = d.threat;
  const pc = $("#postureCode");
  pc.textContent = p.code;
  pc.style.color = p.color;
  $("#thHigh").textContent = p.high_threat_tracks;
  $("#thMed").textContent = p.medium_threat_tracks;
  $("#thTotal").textContent = p.total_tracks;

  // readiness
  $("#overall").textContent = d.readiness.overall + "%";
  $("#branches").innerHTML = Object.entries(d.readiness.by_branch)
    .map(([b, v]) => `
      <div class="bar-row">
        <span>${b}</span>
        <div class="bar-track"><div class="bar-fill"
          style="width:${v}%;background:${branchColor(v)}"></div></div>
        <b>${v}%</b>
      </div>`).join("");

  // assets
  $("#assets tbody").innerHTML = d.assets.map((a) => `
    <tr><td>${a.id}</td><td>${a.name}</td><td>${a.branch}</td>
    <td>${a.type}</td><td>${a.base}</td>
    <td style="color:${branchColor(a.readiness)}">${a.readiness}%</td></tr>`).join("");

  // tracks
  $("#tracks tbody").innerHTML = d.tracks.map((t) => `
    <tr><td>${t.id}</td>
    <td><span class="tag ${t.class}">${t.class}</span></td>
    <td>${t.bearing}°</td><td>${t.range_km}</td><td>${t.alt_m}</td><td>${t.speed_kn}</td>
    <td class="threat-cell" style="color:${threatColor(t.threat)}">${t.threat}</td></tr>`).join("");

  // incidents
  const inc = d.incidents;
  $("#incidents").innerHTML = inc.length
    ? inc.map((i) => `<li><span class="sev ${i.severity}">${i.severity}</span>
        <span>${i.title}</span></li>`).join("")
    : `<li class="empty">No incidents.</li>`;
}
refresh();
setInterval(refresh, 6000);

// --- chat ---
function addMsg(text, cls) {
  const el = document.createElement("div");
  el.className = "msg " + cls;
  el.textContent = text;
  $("#log").appendChild(el);
  $("#log").scrollTop = $("#log").scrollHeight;
  return el;
}

$("#chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#chatInput");
  const msg = input.value.trim();
  if (!msg) return;
  input.value = "";
  addMsg(msg, "user");
  $("#sendBtn").disabled = true;
  const thinking = addMsg("SENTINEL is analysing…", "think");
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg }),
    });
    const data = await r.json();
    thinking.remove();
    if (data.error) addMsg("⚠ " + data.error, "bot");
    else { addMsg(data.reply, "bot"); refresh(); }
  } catch (err) {
    thinking.remove();
    addMsg("⚠ Network error: " + err.message, "bot");
  } finally {
    $("#sendBtn").disabled = false;
    input.focus();
  }
});
