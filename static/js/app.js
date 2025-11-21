// Minimal progressive enhancement for upload & progress UI for non-React fallback
const drop = document.getElementById('dropzone');
if (drop) {
  const input = document.getElementById('fileInput');
  const list = document.getElementById('fileList');
  const bar = document.getElementById('bar');
  const status = document.getElementById('status');

  const upload = async files => {
    const body = new FormData();
    for (const f of files) body.append('files', f);
    const res = await fetch('/upload', { method: 'POST', body });
    const data = await res.json();
    status.textContent = 'Uploaded';
    bar.style.width = '100%';
    localStorage.setItem('job', data.job_id);
  };

  ;['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('ring-2','ring-indigo-500')}));
  ;['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('ring-2','ring-indigo-500')}));
  drop.addEventListener('drop', ev=>{
    const files = ev.dataTransfer.files;
    for (const f of files) list.innerHTML += `<li class='text-sm text-slate-300'>${f.name}</li>`;
    upload(files);
  });
  input?.addEventListener('change', e=> upload(e.target.files));
}
