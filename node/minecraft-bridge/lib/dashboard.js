'use strict';
// The green/dark Tailwind dashboard HTML for the single-port live view.
const { CFG } = require('./config');

function viewDashboardHtml() {
  const USERNAME = CFG.username;
  const HOST = CFG.host;
  const PORT = CFG.port;
  return `<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NovaAI — ${USERNAME}</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={theme:{extend:{colors:{ink:'#0a0f0c',panel:'#0e1712',edge:'#1c2a22',nova:'#34d399',novad:'#10b981'}}}}</script>
<style>
  ::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#1c2a22;border-radius:4px}
  .glow{box-shadow:0 0 0 1px #1c2a22, 0 0 24px -8px rgba(52,211,153,.25)}
  iframe{border:0;width:100%;height:100%;background:#07131d}
  .fade{animation:f .25s ease}@keyframes f{from{opacity:0;transform:translateY(4px)}to{opacity:1}}
</style></head>
<body class="h-screen bg-ink text-emerald-50/90 font-sans overflow-hidden" style="font-family:system-ui,Segoe UI,Arial">
  <header class="h-12 flex items-center gap-3 px-4 border-b border-edge bg-panel">
    <div class="w-2.5 h-2.5 rounded-full bg-nova animate-pulse"></div>
    <div class="font-extrabold tracking-wide text-nova">NovaAI</div>
    <div class="text-sm text-emerald-200/70">live · <span class="text-emerald-100">${USERNAME}</span> @ ${HOST}:${PORT}</div>
    <div id="hud" class="ml-auto text-xs text-emerald-200/70 flex gap-4"></div>
  </header>
  <div class="flex h-[calc(100vh-3rem)]">
    <div class="flex-1 min-w-0 p-3">
      <div class="h-full rounded-xl overflow-hidden glow bg-panel">
        <iframe src="/world/" title="3D world"></iframe>
      </div>
    </div>
    <div class="w-[380px] shrink-0 p-3 pl-0 flex flex-col gap-3">
      <div class="rounded-xl glow bg-panel overflow-hidden h-[44%] flex flex-col">
        <div class="px-3 py-2 text-[12px] font-bold text-nova border-b border-edge">Inventory · Crafting · Furnace</div>
        <div class="flex-1"><iframe src="/inv/" title="Inventory"></iframe></div>
      </div>
      <div class="rounded-xl glow bg-panel overflow-hidden flex-1 flex flex-col">
        <div class="px-3 py-2 text-[12px] font-bold text-nova border-b border-edge flex items-center justify-between">
          <span>🧠 NovaAI's thoughts</span><span class="text-[10px] text-emerald-200/40">what it's deciding</span></div>
        <div id="thoughts" class="flex-1 overflow-y-auto p-2 space-y-1 text-[12px] text-emerald-100/85"></div>
      </div>
      <div class="rounded-xl glow bg-panel overflow-hidden h-[26%] flex flex-col">
        <div class="px-3 py-2 text-[12px] font-bold text-nova border-b border-edge">💬 Server chat</div>
        <div id="chat" class="flex-1 overflow-y-auto p-2 space-y-0.5 text-[12px]"></div>
      </div>
    </div>
  </div>
<script>
  const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  function render(id, items, fmt){
    const el=document.getElementById(id); if(!el) return;
    el.innerHTML = (items&&items.length) ? items.map(fmt).join('') : '<div class="text-emerald-200/30">—</div>';
    el.scrollTop = el.scrollHeight;
  }
  async function poll(){
    try{
      const r = await fetch('/feed'); const d = await r.json();
      const hud=document.getElementById('hud');
      hud.innerHTML = d.connected
        ? \`<span>❤ \${d.health??'?'}/20</span><span>🍗 \${d.food??'?'}/20</span><span>📍 \${d.position?('x'+d.position.x+' y'+d.position.y+' z'+d.position.z):'?'}</span>\`
        : '<span class="text-amber-400">connecting…</span>';
      render('thoughts', d.thoughts, t=>\`<div class="fade px-2 py-1 rounded bg-emerald-500/5 border border-edge/60">\${esc(t)}</div>\`);
      render('chat', d.chat, c=>\`<div class="fade"><span class="text-nova font-semibold">\${esc(c.username)}</span>: <span class="text-emerald-100/80">\${esc(c.message)}</span></div>\`);
    }catch(e){}
    setTimeout(poll, 2000);
  }
  poll();
</script>
</body></html>`;
}

module.exports = { viewDashboardHtml };
